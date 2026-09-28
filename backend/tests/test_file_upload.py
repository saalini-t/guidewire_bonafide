"""Real multipart file upload (Phase 1 file-upload upgrade, sections C/D/F/G/L)."""
from app.storage import storage_backend

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0 0 obj\n<<>>\nendobj\n"
TXT_BYTES = b"Recorded statement transcript: the claimant described the collision."


def _upload(client, claim_id, filename, content, content_type="application/octet-stream"):
    return client.post(
        f"/api/claims/{claim_id}/documents/upload",
        files={"file": (filename, content, content_type)},
    )


def test_upload_valid_jpg(client, demo_claim):
    response = _upload(client, demo_claim, "damage.jpg", JPEG_BYTES, "image/jpeg")

    assert response.status_code == 201
    body = response.json()
    assert body["mime_type"] == "image/jpeg"
    assert body["classification_status"] == "PENDING"


def test_upload_valid_jpeg_extension(client, demo_claim):
    response = _upload(client, demo_claim, "damage.jpeg", JPEG_BYTES, "image/jpeg")

    assert response.status_code == 201


def test_upload_valid_png(client, demo_claim):
    response = _upload(client, demo_claim, "damage.png", PNG_BYTES, "image/png")

    assert response.status_code == 201
    assert response.json()["mime_type"] == "image/png"


def test_upload_valid_pdf(client, demo_claim):
    response = _upload(client, demo_claim, "police-report.pdf", PDF_BYTES, "application/pdf")

    assert response.status_code == 201
    assert response.json()["mime_type"] == "application/pdf"


def test_upload_valid_txt(client, demo_claim):
    response = _upload(client, demo_claim, "statement.txt", TXT_BYTES, "text/plain")

    assert response.status_code == 201
    assert response.json()["mime_type"] == "text/plain"


def test_upload_unsupported_extension_rejected(client, demo_claim):
    response = _upload(client, demo_claim, "malware.exe", b"MZ\x90\x00", "application/octet-stream")

    assert response.status_code == 415


def test_upload_disguised_binary_with_txt_extension_rejected(client, demo_claim):
    """A client can lie about the extension too — a real PNG renamed to
    .txt should still be rejected, since .txt content is validated as
    actual UTF-8 text, not just trusted by extension.
    """
    response = _upload(client, demo_claim, "disguised.txt", PNG_BYTES, "text/plain")

    assert response.status_code == 415


def test_upload_mismatched_signature_rejected(client, demo_claim):
    """Extension claims .jpg but the content isn't actually a JPEG — the
    client-declared Content-Type is never trusted alone.
    """
    response = _upload(client, demo_claim, "fake.jpg", b"not actually a jpeg", "image/jpeg")

    assert response.status_code == 415


def test_upload_oversized_file_rejected(client, demo_claim, monkeypatch):
    monkeypatch.setattr("app.services.settings.max_upload_file_size_bytes", 10)

    response = _upload(client, demo_claim, "statement.txt", TXT_BYTES, "text/plain")

    assert response.status_code == 413


def test_upload_path_traversal_filename_is_sanitized(client, demo_claim):
    response = _upload(client, demo_claim, "../../../evil.txt", TXT_BYTES, "text/plain")

    assert response.status_code == 201
    body = response.json()
    # The stored path must never contain a traversal segment, and the file
    # must land under this claim's own directory in the storage root.
    assert ".." not in body["storage_path"]
    assert body["storage_path"].startswith(f"{demo_claim}/")
    stored_bytes = storage_backend.load(body["storage_path"])
    assert stored_bytes == TXT_BYTES


def test_uploaded_file_metadata_persisted(client, demo_claim):
    response = _upload(client, demo_claim, "statement.txt", TXT_BYTES, "text/plain")
    body = response.json()

    assert body["file_size"] == len(TXT_BYTES)
    assert body["file_hash"] is not None and len(body["file_hash"]) == 64  # sha256 hex digest
    # .txt content is decoded into `text` so the same classify_document
    # pipeline used by the text-paste path can analyze it (see
    # app.services.upload_real_file and the evidence-management task).
    assert body["text"] == TXT_BYTES.decode("utf-8")


def test_uploaded_file_exists_in_storage(client, demo_claim):
    response = _upload(client, demo_claim, "statement.txt", TXT_BYTES, "text/plain")
    storage_path = response.json()["storage_path"]

    assert storage_backend.load(storage_path) == TXT_BYTES


def test_get_documents_returns_uploaded_documents(client, demo_claim):
    _upload(client, demo_claim, "photo.jpg", JPEG_BYTES, "image/jpeg")
    _upload(client, demo_claim, "statement.txt", TXT_BYTES, "text/plain")

    response = client.get(f"/api/claims/{demo_claim}/documents")

    assert response.status_code == 200
    filenames = {doc["filename"] for doc in response.json()}
    assert filenames == {"photo.jpg", "statement.txt"}


def test_documents_survive_a_subsequent_fetch(client, demo_claim):
    """Regression coverage for the known limitation this phase fixes:
    documents used to live only in frontend React state and vanished on
    reload. A second independent GET call (simulating a page refresh) must
    still return the document.
    """
    _upload(client, demo_claim, "photo.jpg", JPEG_BYTES, "image/jpeg")

    first = client.get(f"/api/claims/{demo_claim}/documents").json()
    second = client.get(f"/api/claims/{demo_claim}/documents").json()

    assert len(first) == 1
    assert first == second
