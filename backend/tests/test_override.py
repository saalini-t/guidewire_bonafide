"""Covers Day 2 acceptance items P, Q, R."""

_VALID_JUSTIFICATION = "Repair shop deadline requires authorization despite missing appraisal."


def _override_payload(**overrides):
    payload = {
        "user": "supervisor.test",
        "role": "supervisor",
        "justification": _VALID_JUSTIFICATION,
        "action": "RepairAuthorization",
    }
    payload.update(overrides)
    return payload


def test_override_without_justification_is_rejected(client, demo_claim):
    response = client.post(f"/api/claims/{demo_claim}/override", json=_override_payload(justification=""))

    assert response.status_code == 422


def test_override_with_trivially_short_justification_is_rejected(client, demo_claim):
    response = client.post(f"/api/claims/{demo_claim}/override", json=_override_payload(justification="ok"))

    assert response.status_code == 422


def test_override_without_user_or_role_is_rejected(client, demo_claim):
    assert client.post(f"/api/claims/{demo_claim}/override", json=_override_payload(user="")).status_code == 422
    assert client.post(f"/api/claims/{demo_claim}/override", json=_override_payload(role="")).status_code == 422


def test_override_with_valid_fields_succeeds(client, demo_claim):
    response = client.post(f"/api/claims/{demo_claim}/override", json=_override_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["claim_id"] == demo_claim
    assert body["log"]["event_type"] == "OVERRIDE_APPLIED"
    assert body["log"]["justification"] == _VALID_JUSTIFICATION
    assert body["log"]["user"] == "supervisor.test"

    claim = client.get(f"/api/claims/{demo_claim}").json()
    assert claim["repair_status"] == "AUTHORIZED"
    assert claim["upcoming_business_event"] is None


def test_override_creates_override_applied_log_with_detail(client, demo_claim):
    client.post(f"/api/claims/{demo_claim}/override", json=_override_payload())

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    overrides = [entry for entry in logs if entry["event_type"] == "OVERRIDE_APPLIED"]

    assert len(overrides) == 1
    assert overrides[0]["detail"]["role"] == "supervisor"
    assert overrides[0]["detail"]["action"] == "RepairAuthorization"
    assert overrides[0]["detail"]["risk_level_at_override"] == "MEDIUM"
    assert overrides[0]["detail"]["at_risk_evidence"] == ["Repair Estimate"]
