from pydantic import BaseModel, Field


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
