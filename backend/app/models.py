import datetime as dt

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
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
    text: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    classification: Mapped[DocumentClass | None] = mapped_column(_enum(DocumentClass), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    litigation_signal: Mapped[LitigationSignal | None] = mapped_column(_enum(LitigationSignal), nullable=True)
    litigation_confidence: Mapped[float | None] = mapped_column(nullable=True)
    classification_status: Mapped[ClassificationStatus] = mapped_column(
        _enum(ClassificationStatus), default=ClassificationStatus.PENDING
    )
    ai_provider: Mapped[str | None] = mapped_column(nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="documents", foreign_keys=[claim_id])


class PreservationHold(Base):
    __tablename__ = "preservation_holds"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"))
    status: Mapped[HoldStatus] = mapped_column(_enum(HoldStatus), default=HoldStatus.PROPOSED)
    trigger_reason: Mapped[str] = mapped_column(Text)
    trigger_source: Mapped[str]
    trigger_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    released_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(nullable=True)
    release_justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="holds")


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
