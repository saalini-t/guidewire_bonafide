"""Thin data-access functions. No business logic, no transaction management
(the caller controls commit/rollback via app.db.session_scope or a FastAPI
request-scoped session) — see docs/ARCHITECTURE.md Transactional Design.
"""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.enums import ExpiryTrigger, HoldStatus, ImageQuality, ImageRelevance, PreservationEventType
from app.exceptions import HoldNotFoundError, InvalidHoldTransitionError
from app.models import Claim, Document, EvidenceItem, ImageAnalysis, PreservationHold, PreservationLog


def create_claim(
    session: Session,
    *,
    claim_id: str,
    policy_id: str,
    claim_type: str,
    loss_date: dt.date,
    claimant: str,
    description: str,
    status: str = "OPEN",
    repair_status: str = "NOT_APPLICABLE",
    upcoming_business_event: ExpiryTrigger | None = None,
) -> Claim:
    claim = Claim(
        claim_id=claim_id,
        policy_id=policy_id,
        claim_type=claim_type,
        status=status,
        loss_date=loss_date,
        repair_status=repair_status,
        upcoming_business_event=upcoming_business_event,
        claimant=claimant,
        description=description,
    )
    session.add(claim)
    session.flush()
    return claim


def get_claim(session: Session, claim_id: str) -> Claim | None:
    return session.get(Claim, claim_id)


def list_claims(session: Session) -> list[Claim]:
    return list(session.scalars(select(Claim).order_by(Claim.claim_id)))


def add_evidence_item(
    session: Session,
    *,
    claim_id: str,
    evidence_type,
    expiry_trigger: ExpiryTrigger,
    required: bool = True,
    satisfied: bool = False,
    satisfied_date: dt.datetime | None = None,
) -> EvidenceItem:
    item = EvidenceItem(
        claim_id=claim_id,
        evidence_type=evidence_type,
        required=required,
        satisfied=satisfied,
        satisfied_date=satisfied_date,
        expiry_trigger=expiry_trigger,
    )
    session.add(item)
    session.flush()
    return item


def list_evidence_items(session: Session, claim_id: str) -> list[EvidenceItem]:
    return list(
        session.scalars(
            select(EvidenceItem).where(EvidenceItem.claim_id == claim_id).order_by(EvidenceItem.id)
        )
    )


def create_document(
    session: Session,
    *,
    claim_id: str,
    filename: str,
    storage_path: str,
    text: str | None = None,
    mime_type: str | None = None,
    file_size: int | None = None,
    file_hash: str | None = None,
) -> Document:
    document = Document(
        claim_id=claim_id,
        filename=filename,
        storage_path=storage_path,
        text=text,
        mime_type=mime_type,
        file_size=file_size,
        file_hash=file_hash,
        # A brand-new document can never already have an analysis — set
        # explicitly (rather than leaving the relationship untouched) so
        # SQLAlchemy treats it as already-loaded-and-empty. Without this,
        # serializing the returned object after the session closes (which
        # is exactly when API routes build DocumentResponse) triggers a
        # lazy-load attempt and raises DetachedInstanceError.
        image_analysis=None,
    )
    session.add(document)
    session.flush()
    return document


def get_document(session: Session, document_id: int) -> Document | None:
    # Eager-load image_analysis: DocumentResponse serialization happens
    # after this function's session_scope() has already closed
    # (expire_on_commit=False keeps loaded attributes readable, but an
    # unloaded relationship would raise DetachedInstanceError on access).
    return session.get(Document, document_id, options=[selectinload(Document.image_analysis)])


def list_documents(session: Session, claim_id: str) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .where(Document.claim_id == claim_id, Document.deleted_at.is_(None))
            .order_by(Document.uploaded_at)
            .options(selectinload(Document.image_analysis))
        )
    )


def create_image_analysis(
    session: Session,
    *,
    document_id: int,
    claim_id: str,
    evidence_type,
    vehicle_present: bool,
    damage_observed: bool,
    damage_regions: list[str],
    image_quality: ImageQuality,
    relevance: ImageRelevance,
    confidence: float,
    explanation: str,
    provider: str,
    model: str | None,
) -> ImageAnalysis:
    analysis = ImageAnalysis(
        document_id=document_id,
        claim_id=claim_id,
        evidence_type=evidence_type,
        vehicle_present=vehicle_present,
        damage_observed=damage_observed,
        damage_regions=damage_regions,
        image_quality=image_quality,
        relevance=relevance,
        confidence=confidence,
        explanation=explanation,
        provider=provider,
        model=model,
    )
    session.add(analysis)
    session.flush()
    return analysis


def create_hold(
    session: Session,
    *,
    claim_id: str,
    trigger_reason: str,
    trigger_source: str,
    status: HoldStatus = HoldStatus.PROPOSED,
    confidence: float | None = None,
    document_id: int | None = None,
) -> PreservationHold:
    hold = PreservationHold(
        claim_id=claim_id,
        document_id=document_id,
        status=status,
        trigger_reason=trigger_reason,
        trigger_source=trigger_source,
        confidence=confidence,
    )
    session.add(hold)
    session.flush()
    return hold


def list_holds(session: Session, claim_id: str) -> list[PreservationHold]:
    return list(
        session.scalars(
            select(PreservationHold).where(PreservationHold.claim_id == claim_id).order_by(PreservationHold.id)
        )
    )


def get_hold(session: Session, hold_id: int) -> PreservationHold | None:
    return session.get(PreservationHold, hold_id)


def confirm_hold(session: Session, hold_id: int, *, user: str) -> PreservationHold:
    """The ONLY function that may transition a hold to ACTIVE. Any starting
    status other than PROPOSED is rejected (ACTIVE->ACTIVE, RELEASED->ACTIVE,
    etc.) — there is deliberately no general-purpose "set hold status"
    function that would let anything else (including AI-driven code) reach
    ACTIVE directly.
    """
    hold = session.get(PreservationHold, hold_id)
    if hold is None:
        raise HoldNotFoundError(hold_id)
    if hold.status != HoldStatus.PROPOSED:
        raise InvalidHoldTransitionError(hold_id, hold.status.value)

    hold.status = HoldStatus.ACTIVE
    add_log(
        session,
        claim_id=hold.claim_id,
        event_type=PreservationEventType.HOLD_CONFIRMED,
        user=user,
        detail={"hold_id": hold.id},
    )
    session.flush()
    return hold


def add_log(
    session: Session,
    *,
    claim_id: str,
    event_type: PreservationEventType,
    user: str,
    justification: str | None = None,
    detail: dict | None = None,
) -> PreservationLog:
    """Append-only. There is deliberately no update_log or delete_log
    function — the API layer must not expose an update/delete endpoint for
    preservation_logs.
    """
    log = PreservationLog(
        claim_id=claim_id,
        event_type=event_type,
        user=user,
        justification=justification,
        detail=detail,
    )
    session.add(log)
    session.flush()
    return log


def list_logs(session: Session, claim_id: str) -> list[PreservationLog]:
    return list(
        session.scalars(
            select(PreservationLog).where(PreservationLog.claim_id == claim_id).order_by(PreservationLog.timestamp)
        )
    )
