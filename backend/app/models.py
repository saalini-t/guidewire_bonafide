import datetime as dt

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
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


def _enum(python_enum, **kw):
    """Enum column stored as VARCHAR + CHECK constraint (native_enum=False)
    rather than a Postgres ENUM type, so adding a new taxonomy value later
    is a code change, not an ALTER TYPE migration.
    """
    return Enum(python_enum, native_enum=False, validate_strings=True, **kw)


class Claim(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(primary_key=True)
    policy_id: Mapped[str]
    claim_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")
    loss_date: Mapped[dt.date] = mapped_column(Date)
    repair_status: Mapped[str] = mapped_column(default="NOT_APPLICABLE")
    upcoming_business_event: Mapped[ExpiryTrigger | None] = mapped_column(_enum(ExpiryTrigger), nullable=True)
    claimant: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    holds: Mapped[list["PreservationHold"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    logs: Mapped[list["PreservationLog"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="PreservationLog.timestamp"
    )


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"))
    evidence_type: Mapped[EvidenceType] = mapped_column(_enum(EvidenceType))
    required: Mapped[bool] = mapped_column(default=True)
    satisfied: Mapped[bool] = mapped_column(default=False)
    satisfied_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    satisfying_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    expiry_trigger: Mapped[ExpiryTrigger] = mapped_column(_enum(ExpiryTrigger))
    expired: Mapped[bool] = mapped_column(default=False)
    risk_level: Mapped[RiskLevel | None] = mapped_column(_enum(RiskLevel), nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="evidence_items", foreign_keys=[claim_id])
    satisfying_document: Mapped["Document | None"] = relationship(foreign_keys=[satisfying_document_id])


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"))
    filename: Mapped[str]
    storage_path: Mapped[str]
    # Nullable: a real uploaded file (jpg/png/pdf) has no extracted text yet
    # in this phase — OCR/vision text extraction is future work. The
    # existing text-paste path still always sets this.
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    classification: Mapped[DocumentClass | None] = mapped_column(_enum(DocumentClass), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    litigation_signal: Mapped[LitigationSignal | None] = mapped_column(_enum(LitigationSignal), nullable=True)
    litigation_confidence: Mapped[float | None] = mapped_column(nullable=True)
    classification_status: Mapped[ClassificationStatus] = mapped_column(
        _enum(ClassificationStatus), default=ClassificationStatus.PENDING
    )
    ai_provider: Mapped[str | None] = mapped_column(nullable=True)
    # Real-file metadata (Phase 1 file-upload upgrade). None for documents
    # created via the text-paste path.
    mime_type: Mapped[str | None] = mapped_column(nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    file_hash: Mapped[str | None] = mapped_column(nullable=True)
    # Phase 2A: independent of classification_status (text). NOT_APPLICABLE
    # for non-image documents; set to PENDING at upload time for jpg/png.
    image_analysis_status: Mapped[ImageAnalysisStatus] = mapped_column(
        _enum(ImageAnalysisStatus), default=ImageAnalysisStatus.NOT_APPLICABLE
    )
    # Deterministic (regex-only) extraction results for a real PDF/TXT
    # upload — e.g. estimated_repair_cost, incident_date. Never LLM-derived
    # and never guessed: a field is either matched in the text or left
    # null. None for text-paste and image documents.
    findings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Soft delete/tombstone (see app.services.delete_document). A deleted
    # document is excluded from normal listing but the row (and its audit
    # trail) is never actually removed.
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="documents", foreign_keys=[claim_id])
    image_analysis: Mapped["ImageAnalysis | None"] = relationship(
        back_populates="document", uselist=False, cascade="all, delete-orphan"
    )


class PreservationHold(Base):
    __tablename__ = "preservation_holds"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"))
    # Nullable: manually-proposed holds (POST .../holds) have no triggering
    # document. Set when a litigation signal in a specific document
    # proposes the hold — lets deletion safety reliably find "is this
    # document referenced by an active/proposed hold" (see
    # app.services.delete_document) without parsing trigger_reason text.
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[HoldStatus] = mapped_column(_enum(HoldStatus), default=HoldStatus.PROPOSED)
    trigger_reason: Mapped[str] = mapped_column(Text)
    trigger_source: Mapped[str]
    trigger_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    released_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(nullable=True)
    release_justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="holds")


class ImageAnalysis(Base):
    """One row per analyzed image document (1:1 via document_id). Kept as
    its own table rather than more Document columns — these ~9 fields are
    specific to vision analysis and only ever exist for image documents.
    """

    __tablename__ = "image_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), unique=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"))
    evidence_type: Mapped[EvidenceType] = mapped_column(_enum(EvidenceType))
    vehicle_present: Mapped[bool]
    damage_observed: Mapped[bool]
    damage_regions: Mapped[list] = mapped_column(JSONB)
    image_quality: Mapped[ImageQuality] = mapped_column(_enum(ImageQuality))
    relevance: Mapped[ImageRelevance] = mapped_column(_enum(ImageRelevance))
    confidence: Mapped[float]
    explanation: Mapped[str] = mapped_column(Text)
    provider: Mapped[str]
    model: Mapped[str | None] = mapped_column(nullable=True)
    analyzed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="image_analysis")


class PreservationLog(Base):
    __tablename__ = "preservation_logs"
    __allow_unmapped__ = False

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"))
    event_type: Mapped[PreservationEventType] = mapped_column(_enum(PreservationEventType))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[str] = mapped_column("user")
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="logs")
