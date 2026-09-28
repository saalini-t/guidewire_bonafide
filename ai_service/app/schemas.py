from pydantic import BaseModel, Field, field_validator

from app.taxonomy import DAMAGE_REGIONS, IMAGE_QUALITY_VALUES, RELEVANCE_VALUES


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1)


class ClassifyResponse(BaseModel):
    classification: str
    confidence: float
    provider: str


class LitigationRequest(BaseModel):
    text: str = Field(min_length=1)


class LitigationResponse(BaseModel):
    signal: str
    confidence: float
    provider: str


class HealthResponse(BaseModel):
    status: str
    ollama_configured: bool
    vision_configured: bool = False


class ImageAnalysisRequest(BaseModel):
    image_base64: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)


class ImageAnalysisResponse(BaseModel):
    """Validated at the source, before this ever leaves the AI service —
    the core backend's ai_client re-validates independently too (never
    trust one layer of validation across a process/trust boundary), but a
    malformed vision-model reply must not even get this far.
    """

    vehicle_present: bool
    damage_observed: bool
    damage_regions: list[str]
    image_quality: str
    relevance: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    provider: str
    model: str | None = None

    @field_validator("damage_regions")
    @classmethod
    def _known_regions(cls, value: list[str]) -> list[str]:
        unknown = [r for r in value if r not in DAMAGE_REGIONS]
        if unknown:
            raise ValueError(f"unknown damage region(s): {unknown}")
        return value

    @field_validator("image_quality")
    @classmethod
    def _known_quality(cls, value: str) -> str:
        if value not in IMAGE_QUALITY_VALUES:
            raise ValueError(f"unknown image_quality: {value!r}")
        return value

    @field_validator("relevance")
    @classmethod
    def _known_relevance(cls, value: str) -> str:
        if value not in RELEVANCE_VALUES:
            raise ValueError(f"unknown relevance: {value!r}")
        return value

    @field_validator("explanation")
    @classmethod
    def _bounded_explanation(cls, value: str) -> str:
        # Concise by contract — also caps how much model-generated text ever
        # reaches storage/logs.
        return value[:300]
