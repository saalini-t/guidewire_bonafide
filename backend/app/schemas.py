"""API request/response schemas. SQLAlchemy models are never returned
directly from an endpoint — every response schema uses
`model_config = ConfigDict(from_attributes=True)` so FastAPI can build it
straight from an ORM instance.
"""
import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import (
    ClassificationStatus,
    DamageRegion,
    DocumentClass,
    EvidenceType,
    ExpiryTrigger,
    HoldStatus,
    ImageAnalysisStatus,
    ImageQuality,
    ImageRelevance,
    LitigationSignal,
    PreservationEventType,
    RiskLevel,
)
from app.evidence_taxonomy import EVIDENCE_TAXONOMY_BY_CLAIM_TYPE

# Initial repair-status values a newly created claim may start in.
# AUTHORIZED/CLOSED are reached later via the override workflow, not chosen
# at creation time.
INITIAL_REPAIR_STATUSES = {"PENDING", "COMPLETE", "NOT_APPLICABLE"}

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


class ClaimCreateRequest(BaseModel):
    claimant: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    loss_date: dt.date
    description: str = Field(min_length=1)
    repair_status: str = "PENDING"

    @field_validator("claim_type")
    @classmethod
    def _known_claim_type(cls, value: str) -> str:
        if value not in EVIDENCE_TAXONOMY_BY_CLAIM_TYPE:
            supported = ", ".join(sorted(EVIDENCE_TAXONOMY_BY_CLAIM_TYPE))
            raise ValueError(f"Unsupported claim type {value!r}. Supported: {supported}")
        return value

    @field_validator("repair_status")
    @classmethod
    def _known_repair_status(cls, value: str) -> str:
        if value not in INITIAL_REPAIR_STATUSES:
            raise ValueError(f"repair_status must be one of {sorted(INITIAL_REPAIR_STATUSES)}")
        return value


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


class ImageAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    evidence_type: EvidenceType
    vehicle_present: bool
    damage_observed: bool
    damage_regions: list[DamageRegion]
    image_quality: ImageQuality
    relevance: ImageRelevance
    confidence: float
    explanation: str
    provider: str
    model: str | None
    analyzed_at: dt.datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    filename: str
    storage_path: str
    text: str | None
    uploaded_at: dt.datetime
    classification: DocumentClass | None
    confidence: float | None
    litigation_signal: LitigationSignal | None
    litigation_confidence: float | None
    classification_status: ClassificationStatus
    ai_provider: str | None
    mime_type: str | None
    file_size: int | None
    file_hash: str | None
    image_analysis_status: ImageAnalysisStatus
    image_analysis: ImageAnalysisResponse | None = None
    findings: dict | None = None


class PreservationHoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    document_id: int | None
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


class DocumentDeleteRequest(BaseModel):
    """MVP does not implement real authentication; `user`/`role` are
    identity/role capture recorded verbatim for the audit trail, same as
    OverrideRequest.
    """

    user: str = Field(min_length=1)
    role: str = Field(min_length=1)
    reason: str = Field(min_length=3)


class BulkAnalysisItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    outcome: str
    reason: str | None = None
