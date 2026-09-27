"""Business logic layer. Routes in app.api stay thin and call these
functions; these functions own transaction boundaries via
app.db.session_scope and coordinate repositories + the AI client + storage
backend. AI calls always happen between two separate session_scope() blocks
— never inside one (see docs/ARCHITECTURE.md, Transactional Design).
"""
import datetime as dt
from typing import NamedTuple

from app.ai_client import AIClassificationResult, AILitigationResult, ai_client
from app.config import settings
from app.db import session_scope
from app.enums import (
    ClassificationStatus,
    DocumentClass,
    ExpiryTrigger,
    HoldStatus,
    LitigationSignal,
    PreservationEventType,
)
from app.exceptions import ClaimNotFoundError, DocumentNotFoundError, HoldNotFoundError
from app.models import Claim, Document, PreservationHold, PreservationLog
from app.preservation_engine import PreservationAnalysis, analyze_preservation
from app.repositories import add_log, confirm_hold as _confirm_hold
from app.repositories import (
    create_document,
    create_hold,
    get_claim,
    get_document,
    get_hold,
    list_claims,
    list_evidence_items,
    list_holds,
    list_logs,
)
from app.storage import storage_backend

# Recorded as `user` on log events the system generates on its own
# (document upload, AI classification) as opposed to a human-initiated
# action (hold confirmation, override) where the real caller-supplied user
# is used instead.
SYSTEM_ACTOR = "system"


def _get_claim_or_404(session, claim_id: str) -> Claim:
    claim = get_claim(session, claim_id)
    if claim is None:
        raise ClaimNotFoundError(claim_id)
    return claim


# ---------- Claims ----------

def fetch_claims() -> list[Claim]:
    with session_scope() as session:
        return list_claims(session)


def fetch_claim(claim_id: str) -> Claim:
    with session_scope() as session:
        return _get_claim_or_404(session, claim_id)


def fetch_evidence(claim_id: str) -> list:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        return list_evidence_items(session, claim_id)


def fetch_analysis(claim_id: str) -> PreservationAnalysis:
    with session_scope() as session:
        claim = _get_claim_or_404(session, claim_id)
        evidence = list_evidence_items(session, claim_id)
        return analyze_preservation(claim, evidence)


def run_analysis(claim_id: str) -> PreservationAnalysis:
    """Same calculation as fetch_analysis, but also records an ANALYSIS_RUN
    audit event — this is the POST (has a side effect) vs. GET (read-only)
    distinction in the API.
    """
    with session_scope() as session:
        claim = _get_claim_or_404(session, claim_id)
        evidence = list_evidence_items(session, claim_id)
        result = analyze_preservation(claim, evidence)
        add_log(
            session,
            claim_id=claim_id,
            event_type=PreservationEventType.ANALYSIS_RUN,
            user=SYSTEM_ACTOR,
            detail={
                "risk_level": result.risk_level.value,
                "missing_evidence": [e.value for e in result.missing_evidence],
                "at_risk_evidence": [e.value for e in result.at_risk_evidence],
            },
        )
        return result


def fetch_logs(claim_id: str) -> list[PreservationLog]:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        return list_logs(session, claim_id)


def fetch_timeline(claim_id: str) -> list[PreservationLog]:
    """The audit timeline IS the preservation log, in chronological order —
    kept as a separate function since it's a distinct API endpoint that may
    need its own shaping later.
    """
    return fetch_logs(claim_id)


# ---------- Documents ----------

def upload_document(claim_id: str, filename: str, text: str) -> Document:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)

    # Local filesystem write is not a network call, so doing it before the
    # persistence transaction keeps that transaction to a single insert.
    storage_path = storage_backend.save(claim_id, filename, text.encode("utf-8"))

    with session_scope() as session:
        document = create_document(session, claim_id=claim_id, filename=filename, storage_path=storage_path, text=text)
        add_log(
            session,
            claim_id=claim_id,
            event_type=PreservationEventType.DOCUMENT_UPLOADED,
            user=SYSTEM_ACTOR,
            detail={"document_id": document.id, "filename": filename},
        )
        return document


class ClassifyOutcome(NamedTuple):
    document: Document
    hold: PreservationHold | None


def classify_document(claim_id: str, document_id: int) -> ClassifyOutcome:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        document = get_document(session, document_id)
        if document is None or document.claim_id != claim_id:
            raise DocumentNotFoundError(document_id)
        text = document.text

    # No DB transaction open across these two AI calls.
    classification_result = ai_client.classify_document(text)
    litigation_result = ai_client.detect_litigation_signal(text)

    with session_scope() as session:
        document = get_document(session, document_id)
        claim = _get_claim_or_404(session, claim_id)

        _apply_classification(session, document, classification_result)
        hold = _apply_litigation(session, claim, document, litigation_result)

        return ClassifyOutcome(document=document, hold=hold)


def _apply_classification(session, document: Document, result: AIClassificationResult) -> None:
    if not result.available:
        document.classification_status = ClassificationStatus.MANUAL_REVIEW
        document.ai_provider = None
        add_log(
            session,
            claim_id=document.claim_id,
            event_type=PreservationEventType.DOCUMENT_CLASSIFIED,
            user=SYSTEM_ACTOR,
            detail={
                "document_id": document.id,
                "outcome": "ai_unavailable",
                "status": ClassificationStatus.MANUAL_REVIEW.value,
            },
        )
        return

    document.classification = DocumentClass(result.classification)
    document.confidence = result.confidence
    document.ai_provider = result.provider

    if result.confidence >= settings.ai_confidence_threshold:
        document.classification_status = ClassificationStatus.CLASSIFIED
        _maybe_satisfy_evidence(session, document)
    else:
        document.classification_status = ClassificationStatus.MANUAL_REVIEW

    add_log(
        session,
        claim_id=document.claim_id,
        event_type=PreservationEventType.DOCUMENT_CLASSIFIED,
        user=SYSTEM_ACTOR,
        detail={
            "document_id": document.id,
            "classification": result.classification,
            "confidence": result.confidence,
            "provider": result.provider,
            "status": document.classification_status.value,
        },
    )


def _maybe_satisfy_evidence(session, document: Document) -> None:
    """Only ever called for CLASSIFIED (>= threshold) documents — never for
    MANUAL_REVIEW or AI-unavailable outcomes.
    """
    candidates = [
        item
        for item in list_evidence_items(session, document.claim_id)
        if item.required and not item.satisfied and item.evidence_type.value == document.classification.value
    ]
    if not candidates:
        return
    evidence = candidates[0]
    evidence.satisfied = True
    evidence.satisfied_date = dt.datetime.now(dt.timezone.utc)
    evidence.satisfying_document_id = document.id
    add_log(
        session,
        claim_id=document.claim_id,
        event_type=PreservationEventType.EVIDENCE_SATISFIED,
        user=SYSTEM_ACTOR,
        detail={"evidence_type": evidence.evidence_type.value, "document_id": document.id},
    )


def _apply_litigation(session, claim: Claim, document: Document, result: AILitigationResult) -> PreservationHold | None:
    if not result.available:
        return None  # leave litigation fields as None rather than fabricate a result

    document.litigation_signal = LitigationSignal(result.signal)
    document.litigation_confidence = result.confidence

    add_log(
        session,
        claim_id=claim.claim_id,
        event_type=PreservationEventType.LITIGATION_SIGNAL_DETECTED,
        user=SYSTEM_ACTOR,
        detail={
            "document_id": document.id,
            "signal": result.signal,
            "confidence": result.confidence,
            "provider": result.provider,
        },
    )

    if result.signal == LitigationSignal.NONE.value or result.confidence < settings.litigation_confidence_threshold:
        return None

    hold = create_hold(
        session,
        claim_id=claim.claim_id,
        trigger_reason=f"Litigation signal detected in document {document.id}: {result.signal}",
        trigger_source=f"litigation_signal:{result.signal}",
        confidence=result.confidence,
        status=HoldStatus.PROPOSED,
    )
    add_log(
        session,
        claim_id=claim.claim_id,
        event_type=PreservationEventType.HOLD_PROPOSED,
        user=SYSTEM_ACTOR,
        detail={"hold_id": hold.id, "document_id": document.id, "signal": result.signal, "confidence": result.confidence},
    )
    return hold


# ---------- Holds ----------

def fetch_holds(claim_id: str) -> list[PreservationHold]:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        return list_holds(session, claim_id)


def propose_hold(
    claim_id: str, *, trigger_reason: str, trigger_source: str, user: str, confidence: float | None = None
) -> PreservationHold:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        hold = create_hold(
            session,
            claim_id=claim_id,
            trigger_reason=trigger_reason,
            trigger_source=trigger_source,
            confidence=confidence,
            status=HoldStatus.PROPOSED,
        )
        add_log(
            session,
            claim_id=claim_id,
            event_type=PreservationEventType.HOLD_PROPOSED,
            user=user,
            detail={"hold_id": hold.id, "trigger_source": trigger_source},
        )
        return hold


def confirm_hold(claim_id: str, hold_id: int, user: str) -> PreservationHold:
    with session_scope() as session:
        hold = get_hold(session, hold_id)
        if hold is None or hold.claim_id != claim_id:
            raise HoldNotFoundError(hold_id)
        return _confirm_hold(session, hold_id, user=user)


# ---------- Override ----------

def apply_override(
    claim_id: str, *, user: str, role: str, justification: str, action: ExpiryTrigger, detail: dict | None = None
) -> tuple[Claim, PreservationLog]:
    with session_scope() as session:
        claim = _get_claim_or_404(session, claim_id)
        evidence = list_evidence_items(session, claim_id)
        analysis = analyze_preservation(claim, evidence)

        if action == ExpiryTrigger.REPAIR_AUTHORIZATION:
            claim.repair_status = "AUTHORIZED"
        elif action == ExpiryTrigger.CLAIM_CLOSURE:
            claim.status = "CLOSED"

        if claim.upcoming_business_event == action:
            claim.upcoming_business_event = None

        log_detail = {
            "role": role,
            "action": action.value,
            "risk_level_at_override": analysis.risk_level.value,
            "at_risk_evidence": [e.value for e in analysis.at_risk_evidence],
        }
        if detail:
            log_detail["context"] = detail

        log = add_log(
            session,
            claim_id=claim_id,
            event_type=PreservationEventType.OVERRIDE_APPLIED,
            user=user,
            justification=justification,
            detail=log_detail,
        )
        return claim, log
