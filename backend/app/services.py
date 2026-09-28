"""Business logic layer. Routes in app.api stay thin and call these
functions; these functions own transaction boundaries via
app.db.session_scope and coordinate repositories + the AI client + storage
backend. AI calls always happen between two separate session_scope() blocks
— never inside one (see docs/ARCHITECTURE.md, Transactional Design).
"""
import base64
import datetime as dt
import hashlib
import logging
import random
from typing import NamedTuple

from sqlalchemy import select

from app.ai_client import AIClassificationResult, AIImageAnalysisResult, AILitigationResult, ai_client
from app.config import settings
from app.db import session_scope
from app.document_extraction import MIN_EXTRACTABLE_TEXT_CHARS, extract_findings, extract_pdf_text, ocr_pdf_text
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
)
from app.evidence_taxonomy import evidence_taxonomy_for
from app.exceptions import (
    ClaimNotFoundError,
    DocumentAlreadyProcessingError,
    DocumentNotFoundError,
    DocumentProtectedByHoldError,
    DocumentProtectedBySatisfiedEvidenceError,
    FileTooLargeError,
    HoldNotFoundError,
    UnsupportedFileTypeError,
)
from app.file_validation import validate_upload
from app.models import Claim, Document, EvidenceItem, PreservationHold, PreservationLog
from app.preservation_engine import PreservationAnalysis, analyze_preservation
from app.repositories import add_evidence_item, add_log, confirm_hold as _confirm_hold
from app.repositories import (
    create_claim as _create_claim,
    create_document,
    create_hold,
    create_image_analysis,
    get_claim,
    get_document,
    get_hold,
    list_claims,
    list_documents,
    list_evidence_items,
    list_holds,
    list_logs,
)
from app.storage import storage_backend

logger = logging.getLogger("bona_fide.core")

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
# PDF/TXT real-file uploads are analyzed via the exact same classify_document
# pipeline as the text-paste path, once their text has been extracted.
TEXT_ANALYSIS_MIME_TYPES = {"application/pdf", "text/plain"}

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


def _get_document_or_404(session, claim_id: str, document_id: int) -> Document:
    document = get_document(session, document_id)
    if document is None or document.claim_id != claim_id or document.deleted_at is not None:
        raise DocumentNotFoundError(document_id)
    return document


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


# ---------- Claim Creation ----------

def _generate_claim_id(session) -> str:
    """Deterministic application logic, not an LLM — random 5-digit IDs in
    a range that never collides with the seeded demo claims (10000-29999),
    checked against the DB and retried on the (extremely unlikely) chance
    of a collision.
    """
    for _ in range(10):
        candidate = f"CLM-{random.randint(30000, 99999)}"
        if get_claim(session, candidate) is None:
            return candidate
    return f"CLM-{int(dt.datetime.now(dt.timezone.utc).timestamp())}"


def create_claim_with_evidence(
    *, claimant: str, policy_id: str, claim_type: str, loss_date: dt.date, description: str, repair_status: str
) -> Claim:
    """Real claim creation: deterministic business logic only, no AI. The
    evidence taxonomy and expiry triggers are the exact same ones the
    preservation engine already consumes (app.evidence_taxonomy) — every
    required item starts unsatisfied, since nothing has been collected yet.
    """
    taxonomy = evidence_taxonomy_for(claim_type)
    # A claim with repair still pending has RepairAuthorization as its
    # upcoming business event, matching the pattern already used by every
    # seeded PENDING claim; COMPLETE/NOT_APPLICABLE claims have none yet.
    upcoming_business_event = ExpiryTrigger.REPAIR_AUTHORIZATION if repair_status == "PENDING" else None

    with session_scope() as session:
        claim_id = _generate_claim_id(session)
        claim = _create_claim(
            session,
            claim_id=claim_id,
            policy_id=policy_id,
            claim_type=claim_type,
            loss_date=loss_date,
            claimant=claimant,
            description=description,
            repair_status=repair_status,
            upcoming_business_event=upcoming_business_event,
        )
        for evidence_type, trigger in taxonomy.items():
            add_evidence_item(
                session,
                claim_id=claim.claim_id,
                evidence_type=evidence_type,
                expiry_trigger=trigger,
                required=True,
                satisfied=False,
            )
        add_log(
            session,
            claim_id=claim.claim_id,
            event_type=PreservationEventType.CLAIM_CREATED,
            user=SYSTEM_ACTOR,
            detail={"claim_type": claim_type, "repair_status": repair_status},
        )
        return claim


# ---------- Documents ----------

def fetch_documents(claim_id: str) -> list[Document]:
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        return list_documents(session, claim_id)


def upload_real_file(claim_id: str, *, filename: str, content: bytes) -> Document:
    """Real file upload (Phase 1 of the file-infrastructure upgrade). Only
    stores and records the file — no AI processing happens here yet (that's
    future OCR/vision work); classification_status stays PENDING.
    """
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)

    if len(content) > settings.max_upload_file_size_bytes:
        raise FileTooLargeError(len(content), settings.max_upload_file_size_bytes)

    mime_type = validate_upload(filename, content)
    file_hash = hashlib.sha256(content).hexdigest()

    # Local filesystem write, not a network call — safe to do before the
    # persistence transaction (see upload_document below for the same
    # pattern with the text-paste path).
    storage_path = storage_backend.save(claim_id, filename, content)

    # PDF/TXT text extraction is local CPU work (no AI call) — also safe
    # to do before the persistence transaction. A scanned PDF with no
    # embedded text layer falls back to OCR (if pytesseract + Tesseract are
    # installed); if that also yields nothing, the document is marked
    # FAILED immediately rather than left stuck at PENDING with no route
    # to success.
    text = None
    extraction_failed = False
    if mime_type == "application/pdf":
        text = extract_pdf_text(content)
        if len(text) < MIN_EXTRACTABLE_TEXT_CHARS:
            text = ocr_pdf_text(content)
        if len(text) < MIN_EXTRACTABLE_TEXT_CHARS:
            text = None
            extraction_failed = True
    elif mime_type == "text/plain":
        text = content.decode("utf-8")

    with session_scope() as session:
        document = create_document(
            session,
            claim_id=claim_id,
            filename=filename,
            storage_path=storage_path,
            text=text,
            mime_type=mime_type,
            file_size=len(content),
            file_hash=file_hash,
        )
        if mime_type in IMAGE_MIME_TYPES:
            document.image_analysis_status = ImageAnalysisStatus.PENDING
        elif extraction_failed:
            document.classification_status = ClassificationStatus.FAILED
        add_log(
            session,
            claim_id=claim_id,
            event_type=PreservationEventType.DOCUMENT_UPLOADED,
            user=SYSTEM_ACTOR,
            detail={"document_id": document.id, "filename": filename, "mime_type": mime_type, "file_size": len(content)},
        )
        return document


def fetch_document_file(claim_id: str, document_id: int) -> tuple[bytes, str, str]:
    """Returns (content, mime_type, filename) so the API layer can stream
    the original uploaded file back (e.g. for <img src=...> display).
    """
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        document = _get_document_or_404(session, claim_id, document_id)
        storage_path = document.storage_path
        mime_type = document.mime_type or "application/octet-stream"
        filename = document.filename
    return storage_backend.load(storage_path), mime_type, filename


def analyze_image(claim_id: str, document_id: int) -> Document:
    """Vision analysis for an already-uploaded image document. Never called
    as part of upload_real_file — a separate, explicit action, same
    division as classify_document for text (upload persists first; AI
    processing is a distinct, retriable step, and the AI round trip never
    happens inside a DB transaction).
    """
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        document = _get_document_or_404(session, claim_id, document_id)
        if document.mime_type not in IMAGE_MIME_TYPES:
            raise UnsupportedFileTypeError(
                f"Document {document_id} is not an image (mime_type={document.mime_type!r}); "
                "image analysis only supports JPEG/PNG/WebP."
            )
        if document.image_analysis_status == ImageAnalysisStatus.PROCESSING:
            raise DocumentAlreadyProcessingError(document_id)
        document.image_analysis_status = ImageAnalysisStatus.PROCESSING
        storage_path = document.storage_path
        mime_type = document.mime_type

    # Local disk read + the AI HTTP call both happen with no DB transaction
    # open (see docs/ARCHITECTURE.md Transactional Design). Image bytes are
    # never logged — only structured findings are (see _apply_image_analysis).
    try:
        image_bytes = storage_backend.load(storage_path)
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        result = ai_client.analyze_image(image_base64, mime_type)
    except Exception:
        logger.exception("unexpected error during image analysis for document %s", document_id)
        with session_scope() as session:
            document = _get_document_or_404(session, claim_id, document_id)
            document.image_analysis_status = ImageAnalysisStatus.FAILED
            return document

    with session_scope() as session:
        document = get_document(session, document_id)
        _apply_image_analysis(session, document, result)
        return document


def _apply_image_analysis(session, document: Document, result: AIImageAnalysisResult) -> None:
    if not result.available:
        document.image_analysis_status = ImageAnalysisStatus.MANUAL_REVIEW
        add_log(
            session,
            claim_id=document.claim_id,
            event_type=PreservationEventType.IMAGE_ANALYZED,
            user=SYSTEM_ACTOR,
            detail={
                "document_id": document.id,
                "outcome": "vision_provider_unavailable",
                # Sanitized diagnostic category (e.g. "not_configured",
                # "timeout", "connection_error", "auth_error",
                # "unsupported_model", "malformed_response",
                # "ai_service_unreachable") — never a raw exception message,
                # API key, or image content. Lets a developer distinguish
                # "nothing is configured" from "it's configured but broken"
                # without digging through server logs.
                "reason": result.error_reason or "unknown",
                "status": ImageAnalysisStatus.MANUAL_REVIEW.value,
            },
        )
        return

    # The AI service already validates its own output (see
    # ai_service/app/schemas.py ImageAnalysisResponse), but this is a trust
    # boundary — re-validate independently rather than assuming the other
    # process behaved. Any unknown enum value is treated exactly like a
    # provider failure: manual review, never a fabricated/partial result.
    try:
        image_quality = ImageQuality(result.image_quality)
        relevance = ImageRelevance(result.relevance)
        damage_regions = [DamageRegion(region).value for region in (result.damage_regions or [])]
    except ValueError:
        document.image_analysis_status = ImageAnalysisStatus.MANUAL_REVIEW
        add_log(
            session,
            claim_id=document.claim_id,
            event_type=PreservationEventType.IMAGE_ANALYZED,
            user=SYSTEM_ACTOR,
            detail={"document_id": document.id, "outcome": "malformed_vision_response", "status": ImageAnalysisStatus.MANUAL_REVIEW.value},
        )
        return

    status = (
        ImageAnalysisStatus.ANALYZED
        if result.confidence >= settings.image_analysis_confidence_threshold
        else ImageAnalysisStatus.MANUAL_REVIEW
    )
    document.image_analysis_status = status

    # image_analyses.document_id is unique — re-analysis (e.g. retrying
    # after an earlier MANUAL_REVIEW/unavailable outcome) must update the
    # existing row rather than crash on a duplicate-key insert.
    existing = document.image_analysis
    if existing is not None:
        existing.evidence_type = EvidenceType.VEHICLE_PHOTOGRAPHS
        existing.vehicle_present = result.vehicle_present
        existing.damage_observed = result.damage_observed
        existing.damage_regions = damage_regions
        existing.image_quality = image_quality
        existing.relevance = relevance
        existing.confidence = result.confidence
        existing.explanation = result.explanation
        existing.provider = result.provider
        existing.model = result.model
        existing.analyzed_at = dt.datetime.now(dt.timezone.utc)
    else:
        # document.image_analysis was already eager-loaded (as empty) by
        # the get_document() call earlier in analyze_image() — SQLAlchemy
        # does not retroactively notice a new related row inserted via
        # create_image_analysis(), so the in-memory relationship must be
        # assigned explicitly or the response would still serialize
        # image_analysis as null despite the row now existing.
        document.image_analysis = create_image_analysis(
            session,
            document_id=document.id,
            claim_id=document.claim_id,
            evidence_type=EvidenceType.VEHICLE_PHOTOGRAPHS,
            vehicle_present=result.vehicle_present,
            damage_observed=result.damage_observed,
            damage_regions=damage_regions,
            image_quality=image_quality,
            relevance=relevance,
            confidence=result.confidence,
            explanation=result.explanation,
            provider=result.provider,
            model=result.model,
        )

    # Audit detail is structured metadata only — never the image bytes, and
    # deliberately not the free-text explanation either (kept in
    # image_analyses/the API response, not duplicated into the log).
    add_log(
        session,
        claim_id=document.claim_id,
        event_type=PreservationEventType.IMAGE_ANALYZED,
        user=SYSTEM_ACTOR,
        detail={
            "document_id": document.id,
            "status": status.value,
            "vehicle_present": result.vehicle_present,
            "damage_observed": result.damage_observed,
            "damage_regions": damage_regions,
            "image_quality": image_quality.value,
            "relevance": relevance.value,
            "confidence": result.confidence,
            "provider": result.provider,
            "model": result.model,
        },
    )

    # Rule (Phase 2A, documented per requirement #14): image analysis NEVER
    # automatically satisfies required evidence, regardless of confidence or
    # relevance. A human reviews the structured findings and acts
    # separately — there is no auto-satisfaction path here, unlike text
    # classification's _maybe_satisfy_evidence. This also means: no hold,
    # no override, no claim-state change of any kind results from image
    # analysis (requirements #15/#16) — this function only ever touches
    # Document.image_analysis_status and the new ImageAnalysis row.


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
        document = _get_document_or_404(session, claim_id, document_id)
        if document.text is None:
            raise UnsupportedFileTypeError(f"Document {document_id} has no extractable text to classify")
        if document.classification_status == ClassificationStatus.PROCESSING:
            raise DocumentAlreadyProcessingError(document_id)
        document.classification_status = ClassificationStatus.PROCESSING
        text = document.text

    # No DB transaction open across these two AI calls.
    try:
        classification_result = ai_client.classify_document(text)
        litigation_result = ai_client.detect_litigation_signal(text)
    except Exception:
        logger.exception("unexpected error during classification for document %s", document_id)
        with session_scope() as session:
            document = _get_document_or_404(session, claim_id, document_id)
            document.classification_status = ClassificationStatus.FAILED
            return ClassifyOutcome(document=document, hold=None)

    with session_scope() as session:
        document = get_document(session, document_id)
        claim = _get_claim_or_404(session, claim_id)

        _apply_classification(session, document, classification_result)
        hold = _apply_litigation(session, claim, document, litigation_result)
        if document.text:
            document.findings = extract_findings(document.text)

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

    # Re-analysis (e.g. retrying a document) must not propose a second hold
    # for the same document if one is already PROPOSED/ACTIVE — the human
    # review step for the existing hold is still the authoritative one.
    existing_hold = session.scalars(
        select(PreservationHold).where(
            PreservationHold.document_id == document.id,
            PreservationHold.status.in_([HoldStatus.PROPOSED, HoldStatus.ACTIVE]),
        )
    ).first()
    if existing_hold is not None:
        return None

    hold = create_hold(
        session,
        claim_id=claim.claim_id,
        document_id=document.id,
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


def analyze_document(claim_id: str, document_id: int) -> Document:
    """General analysis entry point: dispatches to the vision pipeline for
    images or the classify_document pipeline for PDF/TXT, by mime_type.
    Text-paste documents (mime_type is None) are not real files and are not
    reachable through this endpoint — use classify_document directly.
    """
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        document = _get_document_or_404(session, claim_id, document_id)
        mime_type = document.mime_type

    if mime_type in IMAGE_MIME_TYPES:
        return analyze_image(claim_id, document_id)
    if mime_type in TEXT_ANALYSIS_MIME_TYPES:
        return classify_document(claim_id, document_id).document
    raise UnsupportedFileTypeError(f"Document {document_id} (mime_type={mime_type!r}) has no analysis pipeline")


class BulkAnalysisItem(NamedTuple):
    document_id: int
    outcome: str  # "analyzed" | "skipped" | "failed"
    reason: str | None = None


def analyze_all_pending(claim_id: str) -> list[BulkAnalysisItem]:
    """Sequentially analyzes every real-file document that is eligible
    (uploaded but not yet successfully analyzed) — no background workers,
    matching this app's fully-synchronous request/response architecture.
    One document's failure is isolated and never stops the batch.
    """
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        eligible_ids = [
            document.id
            for document in list_documents(session, claim_id)
            if document.mime_type in IMAGE_MIME_TYPES
            and document.image_analysis_status in (ImageAnalysisStatus.PENDING, ImageAnalysisStatus.MANUAL_REVIEW, ImageAnalysisStatus.FAILED)
            or document.mime_type in TEXT_ANALYSIS_MIME_TYPES
            and document.text is not None
            and document.classification_status in (ClassificationStatus.PENDING, ClassificationStatus.MANUAL_REVIEW, ClassificationStatus.FAILED)
        ]

    results = []
    for document_id in eligible_ids:
        try:
            analyze_document(claim_id, document_id)
            results.append(BulkAnalysisItem(document_id=document_id, outcome="analyzed"))
        except DocumentAlreadyProcessingError:
            results.append(BulkAnalysisItem(document_id=document_id, outcome="skipped", reason="already processing"))
        except Exception as exc:  # isolate one bad document from the rest of the batch
            logger.exception("bulk analysis failed for document %s", document_id)
            results.append(BulkAnalysisItem(document_id=document_id, outcome="failed", reason=str(exc)[:200]))
    return results


def delete_document(claim_id: str, document_id: int, *, user: str, reason: str) -> None:
    """Soft-delete (tombstone) a document. Blocked — regardless of what the
    frontend sends — if the document is referenced by an active/proposed
    preservation hold, or if it currently satisfies a required, satisfied
    evidence item. The storage file is best-effort removed; the DB row and
    its audit trail are never actually deleted.
    """
    with session_scope() as session:
        _get_claim_or_404(session, claim_id)
        document = _get_document_or_404(session, claim_id, document_id)

        active_hold = session.scalars(
            select(PreservationHold).where(
                PreservationHold.document_id == document.id,
                PreservationHold.status.in_([HoldStatus.PROPOSED, HoldStatus.ACTIVE]),
            )
        ).first()
        if active_hold is not None:
            raise DocumentProtectedByHoldError(document_id, active_hold.id)

        satisfied_evidence = session.scalars(
            select(EvidenceItem).where(
                EvidenceItem.satisfying_document_id == document.id,
                EvidenceItem.satisfied.is_(True),
            )
        ).first()
        if satisfied_evidence is not None:
            raise DocumentProtectedBySatisfiedEvidenceError(document_id, satisfied_evidence.evidence_type.value)

        storage_path, filename, mime_type = document.storage_path, document.filename, document.mime_type

    storage_backend.delete(storage_path)

    with session_scope() as session:
        document = _get_document_or_404(session, claim_id, document_id)
        document.deleted_at = dt.datetime.now(dt.timezone.utc)
        document.deleted_by = user
        document.deletion_reason = reason
        add_log(
            session,
            claim_id=claim_id,
            event_type=PreservationEventType.DOCUMENT_DELETED,
            user=user,
            justification=reason,
            detail={"document_id": document_id, "filename": filename, "mime_type": mime_type},
        )


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
