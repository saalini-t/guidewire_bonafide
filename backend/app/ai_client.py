"""HTTP client for the standalone Bona Fide AI service. Short timeout, no
retries, fails open on every error class (connection refused, timeout,
non-2xx, malformed/missing JSON fields) — callers always get a result
object back, never an exception. `available=False` means "treat as
unclassified / manual review," never "pretend this came from an LLM."
"""
from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass(frozen=True)
class AIClassificationResult:
    available: bool
    classification: str | None = None
    confidence: float | None = None
    provider: str | None = None


@dataclass(frozen=True)
class AILitigationResult:
    available: bool
    signal: str | None = None
    confidence: float | None = None
    provider: str | None = None


class AIServiceClient:
    def __init__(self, base_url: str, timeout: float, client: httpx.Client | None = None):
        self.timeout = timeout
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def classify_document(self, text: str) -> AIClassificationResult:
        try:
            response = self._client.post("/classify-document", json={"text": text}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return AIClassificationResult(
                available=True,
                classification=str(data["classification"]),
                confidence=float(data["confidence"]),
                provider=str(data["provider"]),
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return AIClassificationResult(available=False)

    def detect_litigation_signal(self, text: str) -> AILitigationResult:
        try:
            response = self._client.post("/detect-litigation-signal", json={"text": text}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return AILitigationResult(
                available=True,
                signal=str(data["signal"]),
                confidence=float(data["confidence"]),
                provider=str(data["provider"]),
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return AILitigationResult(available=False)


ai_client = AIServiceClient(base_url=settings.ai_service_url, timeout=settings.ai_service_timeout_seconds)
