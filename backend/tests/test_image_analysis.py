"""Phase 2A: real image understanding (vision analysis of uploaded
photographs). Success-path tests use a fake ai_client (mocked vision
result) — no paid API access or even a real vision model is required to
run this suite, matching the existing pattern for text classification's
transaction-boundary tests (see test_transaction_boundary.py).
"""
from app.ai_client import AIImageAnalysisResult
from app.db import session_scope
from app.models import Claim

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


class FakeAIClient:
    """Stands in for app.services.ai_client — only analyze_image is
    exercised by these tests.
    """

    def __init__(self, result: AIImageAnalysisResult):
        self._result = result

    def analyze_image(self, image_base64, mime_type, timeout=None):
        return self._result


HIGH_CONFIDENCE_RESULT = AIImageAnalysisResult(
    available=True,
    vehicle_present=True,
    damage_observed=True,
    damage_regions=["front_bumper", "hood"],
    image_quality="clear",
    relevance="relevant",
    confidence=0.93,
    explanation="A vehicle with visible front-end damage is shown.",
    provider="ollama",
    model="llava",
)

LOW_CONFIDENCE_RESULT = AIImageAnalysisResult(
    available=True,
    vehicle_present=True,
    damage_observed=False,
    damage_regions=[],
    image_quality="blurry",
    relevance="uncertain",
    confidence=0.4,
    explanation="Image is blurry; hard to tell if damage is present.",
    provider="ollama",
    model="llava",
)

UNAVAILABLE_RESULT = AIImageAnalysisResult(available=False, error_reason="not_configured")


def _upload_image(client, claim_id, filename="damage.jpg"):
    response = client.post(
        f"/api/claims/{claim_id}/documents/upload",
        files={"file": (filename, JPEG_BYTES, "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def test_uploaded_image_starts_with_pending_image_analysis_status(client, demo_claim):
    document = _upload_image(client, demo_claim)

    assert document["image_analysis_status"] == "PENDING"
    assert document["image_analysis"] is None


def test_uploaded_pdf_has_not_applicable_image_analysis_status(client, demo_claim):
    response = client.post(
        f"/api/claims/{demo_claim}/documents/upload",
        files={"file": ("report.pdf", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", "application/pdf")},
    )

    assert response.json()["image_analysis_status"] == "NOT_APPLICABLE"


def test_analyze_valid_jpg_succeeds_with_high_confidence(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim, "damage.jpg")

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert response.status_code == 200
    body = response.json()
    assert body["image_analysis_status"] == "ANALYZED"
    analysis = body["image_analysis"]
    assert analysis["vehicle_present"] is True
    assert analysis["damage_observed"] is True
    assert set(analysis["damage_regions"]) == {"front_bumper", "hood"}
    assert analysis["image_quality"] == "clear"
    assert analysis["relevance"] == "relevant"
    assert analysis["confidence"] == 0.93
    assert analysis["evidence_type"] == "Vehicle Photographs"


def test_analyze_valid_png_succeeds(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    upload = client.post(
        f"/api/claims/{demo_claim}/documents/upload",
        files={"file": ("damage.png", png_bytes, "image/png")},
    )
    document = upload.json()

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert response.status_code == 200
    assert response.json()["image_analysis_status"] == "ANALYZED"


def test_analyze_records_correct_provider_and_model_metadata(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    analysis = response.json()["image_analysis"]
    assert analysis["provider"] == "ollama"
    assert analysis["model"] == "llava"


def test_analyze_low_confidence_result_is_manual_review(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(LOW_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert response.status_code == 200
    assert response.json()["image_analysis_status"] == "MANUAL_REVIEW"


def test_analyze_when_vision_provider_unavailable_marks_manual_review_and_keeps_file(
    client, demo_claim, monkeypatch
):
    """Covers the core backend's handling of "unavailable" (a genuine HTTP
    round-trip failure against the real ai_service is separately covered by
    test_analyze_image_real_round_trip_unavailable below, and the AI
    service's own malformed/timeout/unreachable handling is covered in
    ai_service/tests/test_vision.py).
    """
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(UNAVAILABLE_RESULT))
    document = _upload_image(client, demo_claim)

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert response.status_code == 200
    body = response.json()
    assert body["image_analysis_status"] == "MANUAL_REVIEW"
    assert body["image_analysis"] is None
    # The original file is untouched and still retrievable.
    file_response = client.get(f"/api/claims/{demo_claim}/documents/{document['id']}/file")
    assert file_response.status_code == 200

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    image_event = next(entry for entry in logs if entry["event_type"] == "IMAGE_ANALYZED")
    assert image_event["detail"]["reason"] == "not_configured"
    assert file_response.content == JPEG_BYTES


def test_analyze_image_real_round_trip_unavailable(client, demo_claim, monkeypatch):
    """A genuine HTTP transport failure (nothing listens on this port) —
    the real AIServiceClient.analyze_image path, not a simulated result.
    Deliberately does NOT use the shared `ai_service_url` fixture: that
    subprocess's VISION_PROVIDER is whatever this machine's ai_service/.env
    says (which is no longer a fixed "none" default once a developer
    actually configures real Ollama vision here — see docs/LIMITATIONS.md),
    so asserting a specific reason from it would be environment-dependent.
    Pointing at an unreachable port keeps this test fast and deterministic
    regardless of ambient vision configuration.
    """
    from app.ai_client import AIServiceClient

    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url="http://127.0.0.1:59994", timeout=1.0))
    document = _upload_image(client, demo_claim)

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert response.status_code == 200
    body = response.json()
    assert body["image_analysis_status"] == "MANUAL_REVIEW"

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    image_event = next(entry for entry in logs if entry["event_type"] == "IMAGE_ANALYZED")
    # A real connection failure at the transport level, distinct from the
    # AI service honestly reporting its own provider's failure reason.
    assert image_event["detail"]["reason"] == "ai_service_unreachable"


def test_analyze_image_never_satisfies_evidence_regardless_of_relevance(client, demo_claim, monkeypatch):
    """Documented rule (requirement #14): image analysis never
    auto-satisfies required evidence in Phase 2A, no matter how confident
    or relevant the result is.
    """
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)

    client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    evidence = client.get(f"/api/claims/{demo_claim}/evidence").json()
    repair_estimate = next(e for e in evidence if e["evidence_type"] == "Repair Estimate")
    assert repair_estimate["satisfied"] is False
    assert repair_estimate["satisfying_document_id"] is None


def test_analyze_image_never_creates_hold_or_changes_claim_state(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)

    claim_before = client.get(f"/api/claims/{demo_claim}").json()
    client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")
    claim_after = client.get(f"/api/claims/{demo_claim}").json()

    holds = client.get(f"/api/claims/{demo_claim}/holds").json()
    assert holds == []
    assert claim_after["status"] == claim_before["status"]
    assert claim_after["repair_status"] == claim_before["repair_status"]
    assert claim_after["upcoming_business_event"] == claim_before["upcoming_business_event"]


def test_analyze_image_does_not_change_deterministic_analysis(client, demo_claim, monkeypatch):
    """The preservation engine's risk calculation must be identical before
    and after an image analysis, since image analysis never touches
    evidence/claim state (requirement #15).
    """
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)

    analysis_before = client.get(f"/api/claims/{demo_claim}/analysis").json()
    client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")
    analysis_after = client.get(f"/api/claims/{demo_claim}/analysis").json()

    assert analysis_before == analysis_after


def test_image_analysis_survives_a_subsequent_fetch(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)
    client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    first = client.get(f"/api/claims/{demo_claim}/documents").json()
    second = client.get(f"/api/claims/{demo_claim}/documents").json()

    assert first == second
    assert first[0]["image_analysis"]["confidence"] == 0.93


def test_reanalyzing_an_image_updates_rather_than_crashes(client, demo_claim, monkeypatch):
    """Regression test: image_analyses.document_id is unique, so retrying
    analysis (e.g. after an earlier MANUAL_REVIEW/unavailable outcome, or
    just re-running it) must update the existing row, not attempt a second
    insert and crash with an IntegrityError.
    """
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(UNAVAILABLE_RESULT))
    document = _upload_image(client, demo_claim)
    first = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")
    assert first.status_code == 200
    assert first.json()["image_analysis_status"] == "MANUAL_REVIEW"

    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    second = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert second.status_code == 200
    body = second.json()
    assert body["image_analysis_status"] == "ANALYZED"
    assert body["image_analysis"]["confidence"] == 0.93

    # Only one row exists for this document — confirmed by fetching again
    # and seeing the same single, updated analysis rather than an error.
    refetched = client.get(f"/api/claims/{demo_claim}/documents").json()
    assert len(refetched) == 1
    assert refetched[0]["image_analysis"]["confidence"] == 0.93


def test_analyze_non_image_document_rejected(client, demo_claim):
    upload = client.post(
        f"/api/claims/{demo_claim}/documents",
        json={"filename": "note.txt", "text": "a pasted text document"},
    )
    document = upload.json()

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    assert response.status_code == 415


def test_get_document_file_serves_original_bytes_with_correct_mime_type(client, demo_claim):
    document = _upload_image(client, demo_claim)

    response = client.get(f"/api/claims/{demo_claim}/documents/{document['id']}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == JPEG_BYTES


def test_image_analysis_audit_log_never_contains_image_bytes(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(HIGH_CONFIDENCE_RESULT))
    document = _upload_image(client, demo_claim)
    client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze-image")

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    image_events = [entry for entry in logs if entry["event_type"] == "IMAGE_ANALYZED"]

    assert len(image_events) == 1
    serialized_detail = str(image_events[0]["detail"])
    assert JPEG_BYTES.hex() not in serialized_detail
    import base64

    assert base64.b64encode(JPEG_BYTES).decode("ascii") not in serialized_detail


def test_existing_text_classification_path_is_unaffected_by_image_analysis_changes(client, demo_claim, ai_service_url, monkeypatch):
    """Regression guard: adding the image pipeline must not have disturbed
    the existing text classification/evidence-satisfaction flow.
    """
    from app.ai_client import AIServiceClient

    monkeypatch.setattr("app.services.ai_client", AIServiceClient(base_url=ai_service_url, timeout=2.0))
    upload = client.post(
        f"/api/claims/{demo_claim}/documents",
        json={
            "filename": "estimate.txt",
            "text": "Attached is the repair estimate from the body shop, covering parts and labor for the rear bumper repair.",
        },
    )
    document = upload.json()
    assert document["image_analysis_status"] == "NOT_APPLICABLE"

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["classification"] == "Repair Estimate"
    assert body["document"]["classification_status"] == "CLASSIFIED"

    evidence = client.get(f"/api/claims/{demo_claim}/evidence").json()
    repair_estimate = next(e for e in evidence if e["evidence_type"] == "Repair Estimate")
    assert repair_estimate["satisfied"] is True
