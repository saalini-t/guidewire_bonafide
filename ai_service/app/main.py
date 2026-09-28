import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.providers.vision_base import VisionProviderUnavailableError

logger = logging.getLogger("bona_fide.ai_service")
from app.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    HealthResponse,
    ImageAnalysisRequest,
    ImageAnalysisResponse,
    LitigationRequest,
    LitigationResponse,
)
from app.services import classification, vision

app = FastAPI(
    title="Bona Fide AI Service",
    description=(
        "Stateless document classification and litigation-signal detection. "
        "Owns no claim state, no database, no preservation logic — it only "
        "analyzes input text and returns a structured result. Falls back to "
        "a deterministic keyword provider whenever Ollama is not configured "
        "or unreachable; the `provider` field always names which one "
        "actually produced the result."
    ),
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ollama_configured=bool(settings.ollama_base_url),
        vision_configured=settings.vision_provider == "ollama" and bool(settings.ollama_base_url),
    )


@app.post("/classify-document", response_model=ClassifyResponse)
def classify_document(payload: ClassifyRequest) -> ClassifyResponse:
    return classification.classify_document(payload.text)


@app.post("/detect-litigation-signal", response_model=LitigationResponse)
def detect_litigation_signal(payload: LitigationRequest) -> LitigationResponse:
    return classification.detect_litigation_signal(payload.text)


@app.post("/analyze-image", response_model=ImageAnalysisResponse)
def analyze_image(payload: ImageAnalysisRequest) -> ImageAnalysisResponse:
    """Identifies only visually observable facts (vehicle presence, visible
    damage and its approximate location, image quality, relevance) — never
    accident cause, fault, repair cost, or legal conclusions. Raises 503 if
    no vision provider is configured or reachable; there is no deterministic
    fallback for images the way there is for text.
    """
    return vision.analyze_image(payload.image_base64, payload.mime_type)


@app.exception_handler(VisionProviderUnavailableError)
def _vision_unavailable(request: Request, exc: VisionProviderUnavailableError):
    # The full exception text (which may include upstream HTTP details) is
    # logged server-side only, for developers with log access. The HTTP
    # response stays generic + a sanitized reason code — never image bytes,
    # never a raw exception message that could vary by provider/version.
    logger.warning("vision analysis unavailable (reason=%s): %s", exc.reason.value, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Vision analysis is currently unavailable.", "reason": exc.reason.value},
    )
