from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import settings
from app.exceptions import (
    ClaimNotFoundError,
    DocumentAlreadyProcessingError,
    DocumentNotFoundError,
    DocumentProtectedByHoldError,
    DocumentProtectedBySatisfiedEvidenceError,
    FileTooLargeError,
    HoldNotFoundError,
    InvalidHoldTransitionError,
    UnsupportedFileTypeError,
)

app = FastAPI(
    title="Bona Fide Core API",
    description=(
        "Evidence-preservation intelligence layer for insurance claims. "
        "Deterministic preservation rules (fail-closed) are authoritative; "
        "AI classification/litigation-signal detection (via the standalone "
        "Bona Fide AI service) is advisory input that fails open — see "
        "docs/ARCHITECTURE.md and docs/PRESERVATION_LOGIC.md. "
        "Human-in-the-loop: low-confidence or unavailable AI results never "
        "satisfy evidence or activate a hold; a litigation signal only ever "
        "creates a PROPOSED hold, and only an explicit confirm action can "
        "move it to ACTIVE."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(ClaimNotFoundError)
def _claim_not_found(request: Request, exc: ClaimNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(DocumentNotFoundError)
def _document_not_found(request: Request, exc: DocumentNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(HoldNotFoundError)
def _hold_not_found(request: Request, exc: HoldNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidHoldTransitionError)
def _invalid_hold_transition(request: Request, exc: InvalidHoldTransitionError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(UnsupportedFileTypeError)
def _unsupported_file_type(request: Request, exc: UnsupportedFileTypeError):
    return JSONResponse(status_code=415, content={"detail": str(exc)})


@app.exception_handler(FileTooLargeError)
def _file_too_large(request: Request, exc: FileTooLargeError):
    return JSONResponse(status_code=413, content={"detail": str(exc)})


@app.exception_handler(DocumentAlreadyProcessingError)
def _document_already_processing(request: Request, exc: DocumentAlreadyProcessingError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(DocumentProtectedByHoldError)
def _document_protected_by_hold(request: Request, exc: DocumentProtectedByHoldError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(DocumentProtectedBySatisfiedEvidenceError)
def _document_protected_by_evidence(request: Request, exc: DocumentProtectedBySatisfiedEvidenceError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})
