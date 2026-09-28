"""Ollama vision provider. Mirrors app.providers.ollama.OllamaProvider's
robustness pattern exactly: every failure mode (not configured, connection
refused, timeout, non-JSON output, out-of-taxonomy/out-of-range fields)
raises VisionProviderUnavailableError — never invents a result.
"""
import json

import httpx
from pydantic import ValidationError

from app.config import settings
from app.providers.vision_base import (
    ImageAnalysisOutcome,
    VisionFailureReason,
    VisionProvider,
    VisionProviderUnavailableError,
)
from app.taxonomy import DAMAGE_REGIONS, IMAGE_QUALITY_VALUES, RELEVANCE_VALUES

_PROMPT = (
    "You are analyzing a single photograph submitted as insurance claim evidence for a "
    "vehicle damage claim. Identify ONLY visually observable facts in the image. "
    "Do NOT infer accident cause, fault, who is responsible, repair cost, hidden or "
    "internal damage, or any legal conclusion — only describe what is visible.\n\n"
    f"damage_regions must be a subset of: {DAMAGE_REGIONS} (empty list if no damage visible).\n"
    f"image_quality must be exactly one of: {IMAGE_QUALITY_VALUES}.\n"
    f"relevance must be exactly one of: {RELEVANCE_VALUES} (whether this image is relevant "
    "vehicle-damage evidence at all).\n\n"
    "Respond with strict JSON only, no other text, in exactly this shape:\n"
    '{"vehicle_present": <bool>, "damage_observed": <bool>, "damage_regions": [<string>, ...], '
    '"image_quality": "<string>", "relevance": "<string>", "confidence": <number 0.0-1.0>, '
    '"explanation": "<short factual description, one or two sentences>"}'
)


class OllamaVisionProvider(VisionProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        self.base_url = base_url if base_url is not None else settings.ollama_base_url
        self.model = model or settings.vision_model
        self.timeout = timeout or settings.vision_timeout_seconds

    def analyze_image(self, image_base64: str, mime_type: str) -> ImageAnalysisOutcome:
        if not self.base_url:
            raise VisionProviderUnavailableError(
                "no vision provider configured", reason=VisionFailureReason.NOT_CONFIGURED
            )
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": _PROMPT,
                    "images": [image_base64],
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise VisionProviderUnavailableError(str(exc), reason=VisionFailureReason.TIMEOUT) from exc
        except httpx.ConnectError as exc:
            raise VisionProviderUnavailableError(str(exc), reason=VisionFailureReason.CONNECTION_ERROR) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                reason = VisionFailureReason.AUTH_ERROR
            elif status == 404:
                # Ollama returns 404 for "model not found, pull it first".
                reason = VisionFailureReason.UNSUPPORTED_MODEL
            else:
                reason = VisionFailureReason.INTERNAL_ERROR
            raise VisionProviderUnavailableError(f"HTTP {status}", reason=reason) from exc
        except httpx.HTTPError as exc:
            raise VisionProviderUnavailableError(str(exc), reason=VisionFailureReason.INTERNAL_ERROR) from exc

        # A 2xx response that isn't shaped the way we expect (Ollama sent
        # something, just not valid JSON / not the "response" field) is a
        # malformed response, not a transport-level internal error.
        try:
            raw = response.json()["response"]
            data = json.loads(raw)
        except (KeyError, json.JSONDecodeError, ValueError) as exc:
            raise VisionProviderUnavailableError(
                f"malformed response from vision provider: {exc}", reason=VisionFailureReason.MALFORMED_RESPONSE
            ) from exc

        # Local import avoids a circular import (schemas.py doesn't depend
        # on this module); validates shape/ranges/enums before trusting it.
        from app.schemas import ImageAnalysisResponse

        try:
            validated = ImageAnalysisResponse(
                vehicle_present=data["vehicle_present"],
                damage_observed=data["damage_observed"],
                damage_regions=data["damage_regions"],
                image_quality=data["image_quality"],
                relevance=data["relevance"],
                confidence=data["confidence"],
                explanation=data.get("explanation", ""),
                provider=self.name,
                model=self.model,
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise VisionProviderUnavailableError(
                f"malformed vision response: {exc}", reason=VisionFailureReason.MALFORMED_RESPONSE
            ) from exc

        return ImageAnalysisOutcome(
            vehicle_present=validated.vehicle_present,
            damage_observed=validated.damage_observed,
            damage_regions=validated.damage_regions,
            image_quality=validated.image_quality,
            relevance=validated.relevance,
            confidence=validated.confidence,
            explanation=validated.explanation,
        )
