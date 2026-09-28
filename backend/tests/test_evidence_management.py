"""Complete evidence management / multi-document AI analysis: WebP support,
real PDF/TXT analysis (via the same classify_document pipeline as text-paste,
now reachable through the general POST .../analyze endpoint), a
duplicate-request PROCESSING guard, sequential bulk "analyze all pending",
and preservation-aware document deletion (blocked by an active hold or a
satisfied required evidence item). Fake ai_client results are used
throughout (see test_image_analysis.py's identical rationale) so this suite
never requires a live Ollama model.
"""
from app.ai_client import AIClassificationResult, AIImageAnalysisResult, AILitigationResult
from app.db import session_scope
from app.enums import ClassificationStatus, ImageAnalysisStatus
from app.models import Document

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBPVP8 " + b"\x00" * 16
# Not a structurally valid PDF — exercises the "no extractable text" path
# the same way test_file_upload.py's PDF_BYTES does.
BROKEN_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0 0 obj\n<<>>\nendobj\n"
REPAIR_ESTIMATE_TEXT = (
    "Attached is the repair estimate from the body shop, covering parts and labor "
    "for the rear bumper repair. Total estimated cost of repair: $2,350.00."
)


class FakeAIClient:
    """Stands in for app.services.ai_client with all three methods this
    suite needs (image, classification, litigation).
    """

    def __init__(self, *, image=None, classification=None, litigation=None):
        self._image = image
        self._classification = classification or AIClassificationResult(available=False)
        self._litigation = litigation or AILitigationResult(available=False)

    def analyze_image(self, image_base64, mime_type, timeout=None):
        return self._image

    def classify_document(self, text):
        return self._classification

    def detect_litigation_signal(self, text):
        return self._litigation


def _upload(client, claim_id, filename, content, content_type):
    response = client.post(
        f"/api/claims/{claim_id}/documents/upload",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_valid_webp(client, demo_claim):
    response = client.post(
        f"/api/claims/{demo_claim}/documents/upload",
        files={"file": ("damage.webp", WEBP_BYTES, "image/webp")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mime_type"] == "image/webp"
    assert body["image_analysis_status"] == "PENDING"


def test_pdf_with_no_extractable_text_marked_failed_at_upload(client, demo_claim):
    document = _upload(client, demo_claim, "scanned.pdf", BROKEN_PDF_BYTES, "application/pdf")

    assert document["classification_status"] == "FAILED"
    assert document["text"] is None

    # No text to classify -> the general analyze endpoint refuses (415),
    # never silently fabricates a result.
    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze")
    assert response.status_code == 415


def test_txt_real_file_general_analyze_runs_classification_and_findings(client, demo_claim, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client",
        FakeAIClient(classification=AIClassificationResult(available=True, classification="Repair Estimate", confidence=0.95, provider="deterministic")),
    )
    document = _upload(client, demo_claim, "estimate.txt", REPAIR_ESTIMATE_TEXT.encode("utf-8"), "text/plain")
    assert document["text"] == REPAIR_ESTIMATE_TEXT
    assert document["classification_status"] == "PENDING"

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "Repair Estimate"
    assert body["classification_status"] == "CLASSIFIED"
    # Deterministic regex extraction, not an LLM — a genuine dollar-figure
    # match, never a fabricated one.
    assert body["findings"]["estimated_repair_cost"] == "$2,350.00"

    evidence = client.get(f"/api/claims/{demo_claim}/evidence").json()
    repair_estimate = next(e for e in evidence if e["evidence_type"] == "Repair Estimate")
    assert repair_estimate["satisfied"] is True


def test_general_analyze_dispatches_to_vision_pipeline_for_images(client, demo_claim, monkeypatch):
    image_result = AIImageAnalysisResult(
        available=True,
        vehicle_present=True,
        damage_observed=True,
        damage_regions=["hood"],
        image_quality="clear",
        relevance="relevant",
        confidence=0.9,
        explanation="A vehicle with hood damage.",
        provider="deterministic",
        model=None,
    )
    monkeypatch.setattr("app.services.ai_client", FakeAIClient(image=image_result))
    document = _upload(client, demo_claim, "damage.jpg", JPEG_BYTES, "image/jpeg")

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["image_analysis_status"] == "ANALYZED"
    assert body["image_analysis"]["vehicle_present"] is True


def test_duplicate_analyze_request_is_rejected_with_409(client, demo_claim):
    document = _upload(client, demo_claim, "estimate.txt", REPAIR_ESTIMATE_TEXT.encode("utf-8"), "text/plain")
    with session_scope() as session:
        doc = session.get(Document, document["id"])
        doc.classification_status = ClassificationStatus.PROCESSING

    response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze")

    assert response.status_code == 409


def test_analyze_all_pending_processes_every_eligible_document_and_isolates_failures(client, demo_claim, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client",
        FakeAIClient(classification=AIClassificationResult(available=True, classification="Repair Estimate", confidence=0.95, provider="deterministic")),
    )
    txt_doc = _upload(client, demo_claim, "estimate.txt", REPAIR_ESTIMATE_TEXT.encode("utf-8"), "text/plain")
    # No FakeAIClient.analyze_image result configured (defaults to None) —
    # exercises that one document's failure doesn't stop the batch.
    jpg_doc = _upload(client, demo_claim, "damage.jpg", JPEG_BYTES, "image/jpeg")

    response = client.post(f"/api/claims/{demo_claim}/documents/analyze-all")

    assert response.status_code == 200
    results = {item["document_id"]: item for item in response.json()}
    assert results[txt_doc["id"]]["outcome"] == "analyzed"
    assert results[jpg_doc["id"]]["outcome"] == "failed"

    txt_after = client.get(f"/api/claims/{demo_claim}/documents").json()
    txt_status = next(d for d in txt_after if d["id"] == txt_doc["id"])
    assert txt_status["classification_status"] == "CLASSIFIED"


def test_delete_document_removes_it_from_listing_and_audits(client, demo_claim):
    document = _upload(client, demo_claim, "note.txt", b"An unrelated note.", "text/plain")

    response = client.request(
        "DELETE",
        f"/api/claims/{demo_claim}/documents/{document['id']}",
        json={"user": "adjuster1", "role": "Adjuster", "reason": "duplicate upload"},
    )
    assert response.status_code == 204

    remaining = client.get(f"/api/claims/{demo_claim}/documents").json()
    assert all(d["id"] != document["id"] for d in remaining)

    logs = client.get(f"/api/claims/{demo_claim}/preservation-log").json()
    assert "DOCUMENT_DELETED" in [entry["event_type"] for entry in logs]


def test_delete_document_blocked_when_referenced_by_active_hold(client, demo_claim, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client",
        FakeAIClient(
            classification=AIClassificationResult(available=True, classification="Other", confidence=0.9, provider="deterministic"),
            litigation=AILitigationResult(available=True, signal="attorney_representation", confidence=0.9, provider="deterministic"),
        ),
    )
    document = _upload(client, demo_claim, "letter.txt", b"We represent the claimant.", "text/plain")
    classify_response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze")
    assert classify_response.status_code == 200

    delete_response = client.request(
        "DELETE",
        f"/api/claims/{demo_claim}/documents/{document['id']}",
        json={"user": "adjuster1", "role": "Adjuster", "reason": "attempted cleanup"},
    )

    assert delete_response.status_code == 409


def test_delete_nonexistent_document_returns_404(client, demo_claim):
    response = client.request(
        "DELETE",
        f"/api/claims/{demo_claim}/documents/999999",
        json={"user": "adjuster1", "role": "Adjuster", "reason": "cleanup"},
    )

    assert response.status_code == 404


def test_ocr_fallback_degrades_gracefully_when_pytesseract_not_installed(client, demo_claim):
    """pytesseract/Tesseract are optional (see requirements.txt) — a scanned
    PDF must still be handled cleanly (marked FAILED, never a 500) when
    neither is installed, exactly like before OCR support existed.
    """
    document = _upload(client, demo_claim, "scanned.pdf", BROKEN_PDF_BYTES, "application/pdf")

    assert document["classification_status"] == "FAILED"
    assert document["text"] is None


def test_delete_document_blocked_when_it_satisfies_required_evidence(client, demo_claim, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client",
        FakeAIClient(classification=AIClassificationResult(available=True, classification="Repair Estimate", confidence=0.95, provider="deterministic")),
    )
    document = _upload(client, demo_claim, "estimate.txt", REPAIR_ESTIMATE_TEXT.encode("utf-8"), "text/plain")
    classify_response = client.post(f"/api/claims/{demo_claim}/documents/{document['id']}/analyze")
    assert classify_response.json()["classification_status"] == "CLASSIFIED"

    delete_response = client.request(
        "DELETE",
        f"/api/claims/{demo_claim}/documents/{document['id']}",
        json={"user": "adjuster1", "role": "Adjuster", "reason": "attempted cleanup"},
    )

    assert delete_response.status_code == 409
