"""Provider selection. Tries Ollama first if configured; any failure falls
back to DeterministicProvider transparently. The `provider` field on every
response tells the truth about which one actually produced the result —
never claim a deterministic result came from Ollama.
"""
from app.config import settings
from app.providers.deterministic import DeterministicProvider
from app.providers.ollama import OllamaProvider, OllamaUnavailableError
from app.schemas import ClassifyResponse, LitigationResponse

_deterministic_provider = DeterministicProvider()


def classify_document(text: str) -> ClassifyResponse:
    if settings.ollama_base_url:
        try:
            outcome = OllamaProvider().classify_document(text)
            return ClassifyResponse(classification=outcome.classification, confidence=outcome.confidence, provider="ollama")
        except OllamaUnavailableError:
            pass
    outcome = _deterministic_provider.classify_document(text)
    return ClassifyResponse(classification=outcome.classification, confidence=outcome.confidence, provider="deterministic")


def detect_litigation_signal(text: str) -> LitigationResponse:
    if settings.ollama_base_url:
        try:
            outcome = OllamaProvider().detect_litigation_signal(text)
            return LitigationResponse(signal=outcome.signal, confidence=outcome.confidence, provider="ollama")
        except OllamaUnavailableError:
            pass
    outcome = _deterministic_provider.detect_litigation_signal(text)
    return LitigationResponse(signal=outcome.signal, confidence=outcome.confidence, provider="deterministic")
