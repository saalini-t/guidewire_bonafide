"""Thin API routes. All business logic lives in app.services; all
not-found/invalid-transition errors are translated to HTTP responses by
the exception handlers registered in app.main, so routes never need
try/except.
"""
from fastapi import APIRouter, status

from app import services
from app.enums import ClassificationStatus
from app.schemas import (
    ClaimResponse,
    ClassifyDocumentResponse,
    DocumentResponse,
    DocumentUploadRequest,
    EvidenceItemResponse,
    HoldConfirmRequest,
    HoldCreateRequest,
    OverrideRequest,
    OverrideResponse,
    PreservationAnalysisResponse,
    PreservationHoldResponse,
    PreservationLogResponse,
)

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.get("", response_model=list[ClaimResponse])
def list_claims():
    return services.fetch_claims()


@router.get("/{claim_id}", response_model=ClaimResponse)
def get_claim(claim_id: str):
    return services.fetch_claim(claim_id)


@router.get("/{claim_id}/evidence", response_model=list[EvidenceItemResponse])
def get_evidence(claim_id: str):
    return services.fetch_evidence(claim_id)


@router.get("/{claim_id}/analysis", response_model=PreservationAnalysisResponse)
def get_analysis(claim_id: str):
    """Read-only: computes the current preservation analysis without
    recording an audit event. See POST /analyze for the auditable version.
    """
    return services.fetch_analysis(claim_id)


@router.post("/{claim_id}/analyze", response_model=PreservationAnalysisResponse)
def run_analysis(claim_id: str):
    """Same calculation as GET /analysis, plus an ANALYSIS_RUN preservation
    log entry.
    """
    return services.run_analysis(claim_id)


@router.get("/{claim_id}/timeline", response_model=list[PreservationLogResponse])
def get_timeline(claim_id: str):
    return services.fetch_timeline(claim_id)


@router.get("/{claim_id}/preservation-log", response_model=list[PreservationLogResponse])
def get_preservation_log(claim_id: str):
    return services.fetch_logs(claim_id)


@router.post("/{claim_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(claim_id: str, payload: DocumentUploadRequest):
    """Persists the document (classification_status=PENDING) and returns
    immediately. Classification is a separate call
    (POST .../documents/{document_id}/classify) so the AI round trip never
    blocks — or risks — the upload itself.
    """
    return services.upload_document(claim_id, payload.filename, payload.text)


@router.post("/{claim_id}/documents/{document_id}/classify", response_model=ClassifyDocumentResponse)
def classify_document(claim_id: str, document_id: int):
    """Calls the standalone AI service (2s timeout, fails open). If the AI
    service is unavailable, times out, or returns something unparseable,
    the document is marked classification_status=MANUAL_REVIEW and
    `ai_provider` is left null — never falsely attributed to an LLM.
    A MANUAL_REVIEW or below-threshold result never satisfies evidence and
    never activates a preservation hold; a litigation signal above the
    configured threshold creates a PROPOSED hold only (human confirmation
    required to reach ACTIVE — see POST .../holds/{hold_id}/confirm).
    """
    outcome = services.classify_document(claim_id, document_id)
    return ClassifyDocumentResponse(
        document=outcome.document,
        manual_review_required=outcome.document.classification_status == ClassificationStatus.MANUAL_REVIEW,
        litigation_hold_created=outcome.hold,
    )


@router.get("/{claim_id}/holds", response_model=list[PreservationHoldResponse])
def list_holds(claim_id: str):
    return services.fetch_holds(claim_id)


@router.post("/{claim_id}/holds", response_model=PreservationHoldResponse, status_code=status.HTTP_201_CREATED)
def create_hold(claim_id: str, payload: HoldCreateRequest):
    """Always creates status=PROPOSED — there is no way to request ACTIVE
    directly through this endpoint.
    """
    return services.propose_hold(
        claim_id,
        trigger_reason=payload.trigger_reason,
        trigger_source=payload.trigger_source,
        user=payload.user,
        confidence=payload.confidence,
    )


@router.post("/{claim_id}/holds/{hold_id}/confirm", response_model=PreservationHoldResponse)
def confirm_hold(claim_id: str, hold_id: int, payload: HoldConfirmRequest):
    """The only endpoint that can transition a hold to ACTIVE, and only
    from PROPOSED. Any other starting status returns 409.
    """
    return services.confirm_hold(claim_id, hold_id, payload.user)


@router.post("/{claim_id}/override", response_model=OverrideResponse)
def override(claim_id: str, payload: OverrideRequest):
    """MVP does not implement real authentication or authorization.
    `user` and `role` are identity/role information supplied by the caller
    and recorded verbatim for audit purposes — not verified credentials.
    `justification` must be non-empty and at least
    schemas.MIN_JUSTIFICATION_LENGTH characters; requests that fail this
    return 422 before any state change occurs.
    """
    claim, log = services.apply_override(
        claim_id,
        user=payload.user,
        role=payload.role,
        justification=payload.justification,
        action=payload.action,
        detail=payload.detail,
    )
    return OverrideResponse(claim_id=claim.claim_id, log=log)
