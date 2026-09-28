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


@dataclass(frozen=True)
class AIImageAnalysisResult:
    available: bool
    vehicle_present: bool | None = None
    damage_observed: bool | None = None
    damage_regions: list[str] | None = None
    image_quality: str | None = None
    relevance: str | None = None
    confidence: float | None = None
    explanation: str | None = None
    provider: str | None = None
    model: str | None = None
    # Sanitized diagnostic category only (never a raw exception message,
    # never a secret) — e.g. "not_configured", "timeout", "connection_error",
    # "auth_error", "unsupported_model", "malformed_response". Distinguishes
    # "the vision provider told us why it failed" from "ai_service_unreachable"
    # (we couldn't even get a response from the AI service itself).
    error_reason: str | None = None


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

    def analyze_image(self, image_base64: str, mime_type: str, timeout: float | None = None) -> AIImageAnalysisResult:
        """A separate (longer) timeout than classify/litigation — vision
        inference is slower, and reusing the fast text timeout would report
        "unavailable" on a working-but-slower call. The AI service returns
        503 whenever no vision provider is configured or the configured one
        fails/returns something malformed (no deterministic fallback exists
        for images) — that is just another case `httpx.HTTPError`
        (`raise_for_status`) already covers here, same as every other
        failure mode.
        """
        try:
            response = self._client.post(
                "/analyze-image",
                json={"image_base64": image_base64, "mime_type": mime_type},
                timeout=timeout if timeout is not None else settings.image_analysis_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return AIImageAnalysisResult(
                available=True,
                vehicle_present=bool(data["vehicle_present"]),
                damage_observed=bool(data["damage_observed"]),
                damage_regions=list(data["damage_regions"]),
                image_quality=str(data["image_quality"]),
                relevance=str(data["relevance"]),
                confidence=float(data["confidence"]),
                explanation=str(data["explanation"]),
                provider=str(data["provider"]),
                model=data.get("model"),
            )
        except httpx.HTTPStatusError as exc:
            # The AI service itself responded (e.g. our 503) with a
            # sanitized reason code describing why its vision provider
            # failed — pass it through verbatim rather than collapsing
            # every cause into one generic string.
            reason = None
            try:
                reason = exc.response.json().get("reason")
            except (ValueError, AttributeError):
                pass
            return AIImageAnalysisResult(available=False, error_reason=reason or "ai_service_error")
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            # Couldn't even get a parseable response from the AI service
            # itself (connection refused, timeout, malformed body) —
            # distinct from the AI service honestly reporting its own
            # provider's failure reason above.
            return AIImageAnalysisResult(available=False, error_reason="ai_service_unreachable")


ai_client = AIServiceClient(base_url=settings.ai_service_url, timeout=settings.ai_service_timeout_seconds)
