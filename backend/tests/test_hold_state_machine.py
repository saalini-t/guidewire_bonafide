"""Covers Day 2 acceptance items L, M, N, O."""
from app.db import session_scope
from app.enums import HoldStatus
from app.models import PreservationHold


def _create_hold(client, claim_id):
    response = client.post(
        f"/api/claims/{claim_id}/holds",
        json={"trigger_reason": "Manual test hold", "trigger_source": "manual:test", "user": "adjuster.test"},
    )
    assert response.status_code == 201
    return response.json()


def test_confirm_hold_proposed_to_active_succeeds(client, demo_claim):
    hold = _create_hold(client, demo_claim)

    response = client.post(f"/api/claims/{demo_claim}/holds/{hold['id']}/confirm", json={"user": "adjuster.test"})

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"


def test_confirm_hold_active_to_active_is_rejected(client, demo_claim):
    hold = _create_hold(client, demo_claim)
    first = client.post(f"/api/claims/{demo_claim}/holds/{hold['id']}/confirm", json={"user": "adjuster.test"})
    assert first.status_code == 200

    second = client.post(f"/api/claims/{demo_claim}/holds/{hold['id']}/confirm", json={"user": "adjuster.test"})

    assert second.status_code == 409


def test_confirm_hold_released_to_active_is_rejected(client, demo_claim):
    hold = _create_hold(client, demo_claim)
    # No release endpoint exists yet (out of Day 2 scope) — set RELEASED
    # directly to construct the precondition for this guard test.
    with session_scope() as session:
        h = session.get(PreservationHold, hold["id"])
        h.status = HoldStatus.RELEASED

    response = client.post(f"/api/claims/{demo_claim}/holds/{hold['id']}/confirm", json={"user": "adjuster.test"})

    assert response.status_code == 409


def test_confirm_hold_missing_hold_returns_404(client, demo_claim):
    response = client.post(f"/api/claims/{demo_claim}/holds/999999/confirm", json={"user": "adjuster.test"})

    assert response.status_code == 404


def test_hold_confirmation_creates_hold_confirmed_log_atomically(client, demo_claim):
    hold = _create_hold(client, demo_claim)

    response = client.post(f"/api/claims/{demo_claim}/holds/{hold['id']}/confirm", json={"user": "adjuster.test"})
    assert response.status_code == 200

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    confirmed = [entry for entry in logs if entry["event_type"] == "HOLD_CONFIRMED"]
    assert len(confirmed) == 1
    assert confirmed[0]["user"] == "adjuster.test"
    assert confirmed[0]["detail"]["hold_id"] == hold["id"]
