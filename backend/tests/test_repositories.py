import datetime as dt

from app.enums import ExpiryTrigger, HoldStatus, PreservationEventType, EvidenceType
from app.repositories import (
    add_evidence_item,
    add_log,
    create_claim,
    create_hold,
    get_claim,
    list_claims,
    list_evidence_items,
    list_holds,
    list_logs,
)


def _make_claim(session, claim_id="CLM-TEST"):
    return create_claim(
        session,
        claim_id=claim_id,
        policy_id="POL-1",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 1, 1),
        claimant="Test Claimant",
        description="synthetic test claim",
    )


def test_create_and_get_claim(db_session):
    claim = _make_claim(db_session)

    fetched = get_claim(db_session, "CLM-TEST")

    assert fetched is not None
    assert fetched.claim_id == "CLM-TEST"
    assert fetched.status == "OPEN"


def test_get_claim_missing_returns_none(db_session):
    assert get_claim(db_session, "CLM-DOES-NOT-EXIST") is None


def test_list_claims_orders_by_id(db_session):
    # The real bonafide database already has permanently seeded demo claims
    # (see app.seed_data) by the time this test runs, so assert ordering
    # among just the claims this test created, not an empty table.
    _make_claim(db_session, "CLM-ZZZ-TEST-B")
    _make_claim(db_session, "CLM-ZZZ-TEST-A")

    claims = list_claims(db_session)
    own_ids = [c.claim_id for c in claims if c.claim_id.startswith("CLM-ZZZ-TEST-")]

    assert own_ids == ["CLM-ZZZ-TEST-A", "CLM-ZZZ-TEST-B"]


def test_add_and_list_evidence_items(db_session):
    claim = _make_claim(db_session)
    add_evidence_item(
        db_session,
        claim_id=claim.claim_id,
        evidence_type=EvidenceType.VEHICLE_PHOTOGRAPHS,
        expiry_trigger=ExpiryTrigger.REPAIR_AUTHORIZATION,
        satisfied=False,
    )

    items = list_evidence_items(db_session, claim.claim_id)

    assert len(items) == 1
    assert items[0].evidence_type == EvidenceType.VEHICLE_PHOTOGRAPHS
    assert items[0].satisfied is False


def test_create_and_list_holds(db_session):
    claim = _make_claim(db_session)
    create_hold(
        db_session,
        claim_id=claim.claim_id,
        trigger_reason="Attorney letter received",
        trigger_source="litigation_signal:attorney_representation",
        confidence=0.9,
    )

    holds = list_holds(db_session, claim.claim_id)

    assert len(holds) == 1
    assert holds[0].status == HoldStatus.PROPOSED


def test_add_log_is_append_only_by_api_surface(db_session):
    claim = _make_claim(db_session)
    add_log(db_session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user="tester")

    logs = list_logs(db_session, claim.claim_id)

    assert len(logs) == 1
    assert logs[0].event_type == PreservationEventType.CLAIM_CREATED
    # No update_log / delete_log functions exist in the repository module —
    # preservation_logs is append-only by construction, not just convention.
    import app.repositories as repo_module

    assert not hasattr(repo_module, "update_log")
    assert not hasattr(repo_module, "delete_log")
