"""API request/response schemas. SQLAlchemy models are never returned
directly from an endpoint — every response schema uses
`model_config = ConfigDict(from_attributes=True)` so FastAPI can build it
straight from an ORM instance.
"""
import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import (
    ClassificationStatus,
    DocumentClass,
    EvidenceType,
    ExpiryTrigger,
    HoldStatus,
    LitigationSignal,
    PreservationEventType,
    RiskLevel,
)

# Minimum length for a justification to count as "meaningful" rather than
# just non-empty (e.g. "ok" or "." pass a bare non-empty check but shouldn't
# pass this one). See docs/HITL requirements: overrides require a
# non-empty AND meaningful justification.
MIN_JUSTIFICATION_LENGTH = 10


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_id: str
    policy_id: str
    claim_type: str
    status: str
    loss_date: dt.date
    repair_status: str
    upcoming_business_event: ExpiryTrigger | None
    claimant: str
    description: str
    created_at: dt.datetime
    updated_at: dt.datetime


class EvidenceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    evidence_type: EvidenceType
    required: bool
    satisfied: bool
    satisfied_date: dt.datetime | None
    satisfying_document_id: int | None
    expiry_trigger: ExpiryTrigger
    expired: bool
    risk_level: RiskLevel | None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    filename: str
    storage_path: str
    text: str
    uploaded_at: dt.datetime
    classification: DocumentClass | None
    confidence: float | None
    litigation_signal: LitigationSignal | None
    litigation_confidence: float | None
    classification_status: ClassificationStatus
    ai_provider: str | None


class PreservationHoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    status: HoldStatus
    trigger_reason: str
    trigger_source: str
    trigger_date: dt.datetime
    confidence: float | None
    released_date: dt.datetime | None
    released_by: str | None
    release_justification: str | None


class PreservationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    event_type: PreservationEventType
    timestamp: dt.datetime
    user: str
    justification: str | None
    detail: dict | None


class PreservationAnalysisResponse(BaseModel):
    """Response for GET/POST .../analysis|analyze. Built directly from
    app.preservation_engine.PreservationAnalysis (a plain dataclass) via
    from_attributes — no manual mapping needed.
    """

    model_config = ConfigDict(from_attributes=True)

    claim_id: str
    risk_level: RiskLevel
    upcoming_event: ExpiryTrigger | None
    missing_evidence: list[EvidenceType]
    at_risk_evidence: list[EvidenceType]
    explanation: str
    recommendation: str


class DocumentUploadRequest(BaseModel):
    filename: str = "pasted-document.txt"
    text: str = Field(min_length=1)


class ClassifyDocumentResponse(BaseModel):
    document: DocumentResponse
    manual_review_required: bool
    litigation_hold_created: PreservationHoldResponse | None = None


class HoldCreateRequest(BaseModel):
    """Manual hold creation (e.g. an adjuster proposing a hold directly,
    independent of any AI signal). Always creates status=PROPOSED —
    there is no field here that can request ACTIVE.
    """

    trigger_reason: str = Field(min_length=1)
    trigger_source: str = Field(min_length=1)
    user: str = Field(min_length=1)
    confidence: float | None = None


class HoldConfirmRequest(BaseModel):
    user: str = Field(min_length=1)


class OverrideRequest(BaseModel):
    """MVP does not implement real authentication. `user` and `role` are
    identity/role CAPTURE, supplied by the caller and recorded verbatim for
    audit purposes — they are not verified credentials.
    """

    user: str = Field(min_length=1)
    role: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    action: ExpiryTrigger
    detail: dict | None = None

    @field_validator("user", "role", "justification")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("justification")
    @classmethod
    def _meaningful(cls, value: str) -> str:
        if len(value.strip()) < MIN_JUSTIFICATION_LENGTH:
            raise ValueError(f"justification must be at least {MIN_JUSTIFICATION_LENGTH} characters")
        return value


class OverrideResponse(BaseModel):
    claim_id: str
    log: PreservationLogResponse
