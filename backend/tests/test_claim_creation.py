"""Real claim creation (Phase 1 file-upload upgrade, section A/B)."""
from app.db import session_scope
from app.models import Claim


def _valid_payload(**overrides):
    payload = {
        "claimant": "Alex Rivera",
        "policy_id": "POL-90210",
        "claim_type": "PersonalAuto",
        "loss_date": "2026-09-01",
        "description": "Rear-end collision at an intersection.",
        "repair_status": "PENDING",
    }
    payload.update(overrides)
    return payload


def _cleanup(claim_id: str) -> None:
    with session_scope() as session:
        claim = session.get(Claim, claim_id)
        if claim is not None:
            session.delete(claim)


def test_create_claim_succeeds(client):
    response = client.post("/api/claims", json=_valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["claim_id"].startswith("CLM-")
    assert body["claimant"] == "Alex Rivera"
    assert body["policy_id"] == "POL-90210"
    assert body["claim_type"] == "PersonalAuto"
    assert body["status"] == "OPEN"
    assert body["repair_status"] == "PENDING"
    assert body["upcoming_business_event"] == "RepairAuthorization"

    _cleanup(body["claim_id"])


def test_create_claim_with_complete_repair_status_has_no_upcoming_event(client):
    response = client.post("/api/claims", json=_valid_payload(repair_status="COMPLETE"))

    assert response.status_code == 201
    body = response.json()
    assert body["upcoming_business_event"] is None

    _cleanup(body["claim_id"])


def test_create_claim_missing_required_field_rejected(client):
    payload = _valid_payload()
    del payload["claimant"]

    response = client.post("/api/claims", json=payload)

    assert response.status_code == 422


def test_create_claim_unsupported_claim_type_rejected(client):
    response = client.post("/api/claims", json=_valid_payload(claim_type="Homeowners"))

    assert response.status_code == 422


def test_create_claim_unsupported_repair_status_rejected(client):
    response = client.post("/api/claims", json=_valid_payload(repair_status="AUTHORIZED"))

    assert response.status_code == 422


def test_create_claim_generates_personal_auto_evidence_requirements(client):
    response = client.post("/api/claims", json=_valid_payload())
    claim_id = response.json()["claim_id"]

    evidence = client.get(f"/api/claims/{claim_id}/evidence").json()

    assert {item["evidence_type"] for item in evidence} == {
        "Vehicle Photographs",
        "Police Report",
        "Repair Appraisal",
        "Vehicle Inspection",
        "Recorded Statement",
        "Repair Estimate",
    }
    assert all(item["required"] is True for item in evidence)
    assert all(item["satisfied"] is False for item in evidence)

    _cleanup(claim_id)


def test_create_claim_generates_high_risk_analysis_when_repair_pending(client):
    """A brand-new claim with nothing collected yet and repair pending is
    genuinely at HIGH preservation risk — the existing engine, unmodified,
    should say so.
    """
    response = client.post("/api/claims", json=_valid_payload())
    claim_id = response.json()["claim_id"]

    analysis = client.get(f"/api/claims/{claim_id}/analysis").json()

    assert analysis["risk_level"] == "HIGH"

    _cleanup(claim_id)


def test_create_claim_creates_claim_created_audit_event(client):
    response = client.post("/api/claims", json=_valid_payload())
    claim_id = response.json()["claim_id"]

    logs = client.get(f"/api/claims/{claim_id}/preservation-log").json()

    assert [entry["event_type"] for entry in logs] == ["CLAIM_CREATED"]

    _cleanup(claim_id)


def test_create_claim_appears_in_claims_list(client):
    response = client.post("/api/claims", json=_valid_payload())
    claim_id = response.json()["claim_id"]

    all_claims = client.get("/api/claims").json()

    assert claim_id in {c["claim_id"] for c in all_claims}

    _cleanup(claim_id)
