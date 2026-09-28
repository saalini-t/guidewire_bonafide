"""Provider selection for image analysis. There is no deterministic
fallback here (unlike app.services.classification) — if no vision provider
is configured, or the configured one fails, this raises
VisionProviderUnavailableError and the caller (the FastAPI route) turns
that into a 503. The core backend's ai_client already treats a non-2xx
response as "unavailable" and marks the document for manual review — this
reuses that existing, tested contract rather than inventing a new one.
"""
from app.config import settings
from app.providers.ollama_vision import OllamaVisionProvider
from app.providers.vision_base import VisionFailureReason, VisionProviderUnavailableError
from app.schemas import ImageAnalysisResponse


def analyze_image(image_base64: str, mime_type: str) -> ImageAnalysisResponse:
    if settings.vision_provider != "ollama":
        raise VisionProviderUnavailableError(
            f"no vision provider configured (vision_provider={settings.vision_provider!r})",
            reason=VisionFailureReason.NOT_CONFIGURED,
        )

    outcome = OllamaVisionProvider().analyze_image(image_base64, mime_type)
    return ImageAnalysisResponse(
        vehicle_present=outcome.vehicle_present,
        damage_observed=outcome.damage_observed,
        damage_regions=outcome.damage_regions,
        image_quality=outcome.image_quality,
        relevance=outcome.relevance,
        confidence=outcome.confidence,
        explanation=outcome.explanation,
        provider="ollama",
        model=settings.vision_model,
    )
