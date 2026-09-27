from fastapi import FastAPI

from app.config import settings
from app.schemas import ClassifyRequest, ClassifyResponse, HealthResponse, LitigationRequest, LitigationResponse
from app.services import classification

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
    return HealthResponse(status="ok", ollama_configured=bool(settings.ollama_base_url))


@app.post("/classify-document", response_model=ClassifyResponse)
def classify_document(payload: ClassifyRequest) -> ClassifyResponse:
    return classification.classify_document(payload.text)


@app.post("/detect-litigation-signal", response_model=LitigationResponse)
def detect_litigation_signal(payload: LitigationRequest) -> LitigationResponse:
    return classification.detect_litigation_signal(payload.text)
