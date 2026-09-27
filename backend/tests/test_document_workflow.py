"""Covers Day 2 acceptance items D, E, F, G, I, J, K.

Tests that need a genuine successful AI round trip use the real standalone
AI service (the `ai_service_url` fixture, a real subprocess) — nothing here
mocks the classification/litigation logic itself. Tests for AI-unavailable
behavior point at a port nothing listens on, which is a real connection
failure, not a simulated one.
"""
from app.ai_client import AIServiceClient


def _upload(client, claim_id, text, filename="document.txt"):
    response = client.post(f"/api/claims/{claim_id}/documents", json={"filename": filename, "text": text})
    assert response.status_code == 201
    return response.json()


def test_document_upload_persists_document(client, demo_claim):
    document = _upload(client, demo_claim, "A short synthetic note about the claim.")

    assert document["claim_id"] == demo_claim
    assert document["classification_status"] == "PENDING"
    assert document["classification"] is None
    assert document["ai_provider"] is None

    fetched = client.get(f"/api/claims/{demo_claim}/evidence")
    assert fetched.status_code == 200  # claim/document round trip is intact


def test_high_confidence_classification_accepts_result_and_satisfies_evidence(client, demo_claim, ai_service_url, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url=ai_service_url, timeout=2.0))
    document = _upload(
        client,
        demo_claim,
        "Attached is the repair estimate from the body shop, covering parts and labor for the rear bumper repair.",
    )

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["classification"] == "Repair Estimate"
    assert body["document"]["confidence"] >= 0.85
    assert body["document"]["classification_status"] == "CLASSIFIED"
    assert body["document"]["ai_provider"] == "deterministic"
    assert body["manual_review_required"] is False

    evidence = client.get(f"/api/claims/{demo_claim}/evidence").json()
    repair_estimate = next(e for e in evidence if e["evidence_type"] == "Repair Estimate")
    assert repair_estimate["satisfied"] is True
    assert repair_estimate["satisfying_document_id"] == document["id"]


def test_low_confidence_classification_is_manual_review_and_does_not_satisfy_evidence(
    client, demo_claim, ai_service_url, monkeypatch
):
    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url=ai_service_url, timeout=2.0))
    # Exactly one Repair Estimate keyword -> deterministic confidence 0.70, below the 0.85 threshold.
    document = _upload(client, demo_claim, "Here is a rough repair estimate for your review, subject to change.")

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["classification"] == "Repair Estimate"
    assert body["document"]["confidence"] < 0.85
    assert body["document"]["classification_status"] == "MANUAL_REVIEW"
    assert body["manual_review_required"] is True

    evidence = client.get(f"/api/claims/{demo_claim}/evidence").json()
    repair_estimate = next(e for e in evidence if e["evidence_type"] == "Repair Estimate")
    assert repair_estimate["satisfied"] is False
    assert repair_estimate["satisfying_document_id"] is None


def test_ai_service_unavailable_does_not_fail_upload_or_classification(client, demo_claim, monkeypatch):
    # Nothing listens on this port — a real connection failure.
    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url="http://127.0.0.1:59997", timeout=0.5))
    document = _upload(client, demo_claim, "A document that will never reach the AI service.")

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["classification_status"] == "MANUAL_REVIEW"
    assert body["document"]["ai_provider"] is None  # never falsely attributed to an LLM
    assert body["manual_review_required"] is True
    assert body["litigation_hold_created"] is None

    # The document itself is still there, fully persisted.
    still_there = client.get(f"/api/claims/{demo_claim}/evidence")
    assert still_there.status_code == 200


def test_litigation_signal_creates_proposed_hold_never_active(client, demo_claim, ai_service_url, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url=ai_service_url, timeout=2.0))
    text = (
        "The Law Offices of Smith & Associates represents the claimant. Please route further "
        "communication to our legal counsel, attorney for the claimant."
    )
    document = _upload(client, demo_claim, text, filename="attorney-letter.txt")

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["litigation_signal"] == "attorney_representation"
    assert body["document"]["litigation_confidence"] >= 0.85

    hold = body["litigation_hold_created"]
    assert hold is not None
    # This is the direct proof that AI can never create an ACTIVE hold: the
    # only status a hold can ever be created with is PROPOSED (see
    # app.services._apply_litigation, which always passes status=PROPOSED,
    # and app.repositories.confirm_hold, the only function that can move a
    # hold to ACTIVE).
    assert hold["status"] == "PROPOSED"

    holds_response = client.get(f"/api/claims/{demo_claim}/holds")
    assert [h["status"] for h in holds_response.json()] == ["PROPOSED"]

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    assert "HOLD_PROPOSED" in [entry["event_type"] for entry in logs]


def test_natural_attorney_preservation_letter_creates_proposed_hold_end_to_end(
    client, demo_claim, ai_service_url, monkeypatch
):
    """End-to-end regression test for a real bug found in live Day 3
    testing: a naturally-phrased attorney evidence-preservation letter
    (not built from the exact canned keyword phrases used in the test
    above) previously fell through with litigation_signal="none" and no
    hold at all, because the deterministic provider's keyword list only
    matched "represents" (third-person) and missed this letter's actual
    "We represent..." phrasing. Fixed in
    ai_service/app/providers/deterministic.py.
    """
    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url=ai_service_url, timeout=2.0))
    text = (
        "We represent the claimant in connection with this insurance matter.\n\n"
        "Please preserve all relevant records, documents, photographs,\n"
        "communications, estimates, reports, and other evidence relating\n"
        "to this claim.\n\n"
        "This correspondence concerns the claimant's legal representation\n"
        "and preservation of relevant evidence."
    )
    document = _upload(client, demo_claim, text, filename="attorney_representation.txt")

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    # The letter merely mentions "photographs" as one item in a list of
    # evidence categories to preserve — it must not be misclassified as an
    # actual vehicle-photo submission.
    assert body["document"]["classification"] != "Vehicle Photographs"
    assert body["document"]["litigation_signal"] == "attorney_representation"
    assert body["document"]["litigation_confidence"] >= 0.85

    hold = body["litigation_hold_created"]
    assert hold is not None
    assert hold["status"] == "PROPOSED"  # never ACTIVE — see the test above
