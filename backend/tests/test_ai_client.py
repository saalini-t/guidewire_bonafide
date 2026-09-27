"""Unit tests for AIServiceClient's fail-open behavior — no real AI service
needed, just httpx.MockTransport / a genuinely unreachable address.
"""
import httpx

from app.ai_client import AIServiceClient


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ai-test")


def test_classify_document_succeeds_on_valid_response():
    def handler(request):
        return httpx.Response(200, json={"classification": "Repair Estimate", "confidence": 0.9, "provider": "deterministic"})

    client = AIServiceClient(base_url="http://ai-test", timeout=1.0, client=_mock_client(handler))

    result = client.classify_document("some text")

    assert result.available is True
    assert result.classification == "Repair Estimate"
    assert result.confidence == 0.9
    assert result.provider == "deterministic"


def test_detect_litigation_signal_succeeds_on_valid_response():
    def handler(request):
        return httpx.Response(200, json={"signal": "attorney_representation", "confidence": 0.9, "provider": "ollama"})

    client = AIServiceClient(base_url="http://ai-test", timeout=1.0, client=_mock_client(handler))

    result = client.detect_litigation_signal("some text")

    assert result.available is True
    assert result.signal == "attorney_representation"
    assert result.provider == "ollama"


def test_classify_document_fails_open_on_malformed_json_shape():
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    client = AIServiceClient(base_url="http://ai-test", timeout=1.0, client=_mock_client(handler))

    result = client.classify_document("some text")

    assert result.available is False
    assert result.classification is None
    assert result.provider is None


def test_classify_document_fails_open_on_non_200_status():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = AIServiceClient(base_url="http://ai-test", timeout=1.0, client=_mock_client(handler))

    result = client.classify_document("some text")

    assert result.available is False


def test_classify_document_fails_open_on_connection_error():
    # Nothing listens on this port — a real connection failure, not a mock.
    client = AIServiceClient(base_url="http://127.0.0.1:59998", timeout=0.5)

    result = client.classify_document("some text")

    assert result.available is False


def test_detect_litigation_signal_fails_open_on_connection_error():
    client = AIServiceClient(base_url="http://127.0.0.1:59998", timeout=0.5)

    result = client.detect_litigation_signal("some text")

    assert result.available is False
