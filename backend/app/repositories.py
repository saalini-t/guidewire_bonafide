"""Thin data-access functions. No business logic, no transaction management
(the caller controls commit/rollback via app.db.session_scope or a FastAPI
request-scoped session) — see docs/ARCHITECTURE.md Transactional Design.
"""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ExpiryTrigger, HoldStatus, PreservationEventType
from app.exceptions import HoldNotFoundError, InvalidHoldTransitionError
from app.models import Claim, Document, EvidenceItem, PreservationHold, PreservationLog


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
    text: str,
) -> Document:
    document = Document(claim_id=claim_id, filename=filename, storage_path=storage_path, text=text)
    session.add(document)
    session.flush()
    return document


def get_document(session: Session, document_id: int) -> Document | None:
    return session.get(Document, document_id)


def create_hold(
    session: Session,
    *,
    claim_id: str,
    trigger_reason: str,
    trigger_source: str,
    status: HoldStatus = HoldStatus.PROPOSED,
    confidence: float | None = None,
) -> PreservationHold:
    hold = PreservationHold(
        claim_id=claim_id,
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
