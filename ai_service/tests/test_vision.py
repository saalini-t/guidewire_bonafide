"""Image analysis (Phase 2A). VISION_PROVIDER defaults to "none" in this
environment's .env, so /analyze-image normally returns 503 — tests that
need a successful analysis monkeypatch settings + the Ollama HTTP call
rather than requiring a real vision model.
"""
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TINY_IMAGE_BASE64 = base64.b64encode(b"\xff\xd8\xff\xe0fake-jpeg-bytes").decode("ascii")

VALID_MODEL_RESPONSE = {
    "vehicle_present": True,
    "damage_observed": True,
    "damage_regions": ["front_bumper", "hood"],
    "image_quality": "clear",
    "relevance": "relevant",
    "confidence": 0.92,
    "explanation": "A vehicle with visible front-end damage is shown.",
}


def _mock_ollama_generate(monkeypatch, response_payload_text: str | None, status_code: int = 200):
    def fake_post(url, json=None, timeout=None):
        if status_code != 200:
            request = httpx.Request("POST", url)
            response = httpx.Response(status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)
        return httpx.Response(200, json={"response": response_payload_text}, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.providers.ollama_vision.httpx.post", fake_post)


def test_analyze_image_returns_503_when_no_vision_provider_configured(monkeypatch):
    # Explicit, not ambient: this environment's .env may have real Ollama
    # vision configured by a developer (see docs/LIMITATIONS.md) — force
    # "not configured" here rather than assuming the on-disk default.
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "none")

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 503
    body = response.json()
    assert body["reason"] == "not_configured"
    # The user-facing message stays generic — the raw exception text is
    # logged server-side only, never returned over HTTP.
    assert "vision_provider" not in body["detail"]


def test_analyze_image_succeeds_with_valid_mocked_vision_response(monkeypatch):
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://fake-ollama:11434")
    _mock_ollama_generate(monkeypatch, json.dumps(VALID_MODEL_RESPONSE))

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_present"] is True
    assert body["damage_observed"] is True
    assert set(body["damage_regions"]) == {"front_bumper", "hood"}
    assert body["image_quality"] == "clear"
    assert body["relevance"] == "relevant"
    assert body["confidence"] == 0.92
    assert body["provider"] == "ollama"
    assert body["model"] == "llava"


def test_analyze_image_low_confidence_still_returns_200_caller_decides_review(monkeypatch):
    """The AI service reports what it found; the confidence-threshold ->
    manual-review decision is the core backend's job (see
    backend/app/services.py), same division of responsibility as text
    classification.
    """
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://fake-ollama:11434")
    low_confidence = {**VALID_MODEL_RESPONSE, "confidence": 0.4}
    _mock_ollama_generate(monkeypatch, json.dumps(low_confidence))

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 200
    assert response.json()["confidence"] == 0.4


@pytest.mark.parametrize(
    "broken_payload",
    [
        json.dumps({**VALID_MODEL_RESPONSE, "confidence": 1.5}),  # out of range
        json.dumps({**VALID_MODEL_RESPONSE, "image_quality": "pristine"}),  # unknown enum value
        json.dumps({**VALID_MODEL_RESPONSE, "damage_regions": ["engine_block"]}),  # unknown region
        "not even json",
        json.dumps({"vehicle_present": True}),  # missing required fields
    ],
)
def test_analyze_image_returns_503_on_malformed_model_response(monkeypatch, broken_payload):
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://fake-ollama:11434")
    _mock_ollama_generate(monkeypatch, broken_payload)

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 503
    assert response.json()["reason"] == "malformed_response"


def test_analyze_image_returns_503_when_ollama_unreachable(monkeypatch):
    """A real connection failure (nothing listens on this port), not a
    mock — distinguishes app.providers.vision_base.VisionFailureReason
    .CONNECTION_ERROR from .TIMEOUT.
    """
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://127.0.0.1:59995")

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 503
    assert response.json()["reason"] == "connection_error"


def test_analyze_image_returns_503_on_timeout(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://fake-ollama:11434")
    monkeypatch.setattr("app.providers.ollama_vision.httpx.post", fake_post)

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 503
    assert response.json()["reason"] == "timeout"


def test_analyze_image_returns_503_with_unsupported_model_reason_on_404(monkeypatch):
    """Ollama returns 404 when the configured model hasn't been pulled."""
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://fake-ollama:11434")
    _mock_ollama_generate(monkeypatch, None, status_code=404)

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 503
    assert response.json()["reason"] == "unsupported_model"


def test_analyze_image_returns_503_with_auth_error_reason_on_401(monkeypatch):
    monkeypatch.setattr("app.services.vision.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.providers.ollama_vision.settings.ollama_base_url", "http://fake-ollama:11434")
    _mock_ollama_generate(monkeypatch, None, status_code=401)

    response = client.post("/analyze-image", json={"image_base64": TINY_IMAGE_BASE64, "mime_type": "image/jpeg"})

    assert response.status_code == 503
    assert response.json()["reason"] == "auth_error"


def test_analyze_image_rejects_empty_body():
    response = client.post("/analyze-image", json={"image_base64": "", "mime_type": "image/jpeg"})

    assert response.status_code == 422


def test_health_reports_vision_configured_flag(monkeypatch):
    monkeypatch.setattr("app.main.settings.vision_provider", "ollama")
    monkeypatch.setattr("app.main.settings.ollama_base_url", "http://fake-ollama:11434")

    response = client.get("/health")

    assert response.json()["vision_configured"] is True
