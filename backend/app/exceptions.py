"""Domain-level errors. app.main registers an exception handler per type so
route functions in app.api never need try/except (see docs/ARCHITECTURE.md
"Keep API routes thin").
"""


class DomainError(Exception):
    pass


class ClaimNotFoundError(DomainError):
    def __init__(self, claim_id: str):
        self.claim_id = claim_id
        super().__init__(f"Claim {claim_id} not found")


class DocumentNotFoundError(DomainError):
    def __init__(self, document_id: int):
        self.document_id = document_id
        super().__init__(f"Document {document_id} not found")


class HoldNotFoundError(DomainError):
    def __init__(self, hold_id: int):
        self.hold_id = hold_id
        super().__init__(f"Hold {hold_id} not found")


class UnsupportedClaimTypeError(DomainError):
    """Raised when claim creation is requested for a claim type with no
    known evidence taxonomy (see app.evidence_taxonomy) — only PersonalAuto
    is supported today.
    """

    def __init__(self, claim_type: str):
        self.claim_type = claim_type
        super().__init__(f"Unsupported claim type: {claim_type!r} (only 'PersonalAuto' is supported)")


class UnsupportedFileTypeError(DomainError):
    def __init__(self, reason: str):
        super().__init__(reason)


class FileTooLargeError(DomainError):
    def __init__(self, size: int, max_size: int):
        self.size = size
        self.max_size = max_size
        super().__init__(f"File is {size} bytes, exceeding the {max_size}-byte limit")


class DocumentAlreadyProcessingError(DomainError):
    """Raised when an analyze request arrives for a document that already
    has one in flight — prevents duplicate concurrent AI calls for the
    same document.
    """

    def __init__(self, document_id: int):
        self.document_id = document_id
        super().__init__(f"Document {document_id} is already being analyzed")


class DocumentProtectedByHoldError(DomainError):
    def __init__(self, document_id: int, hold_id: int):
        self.document_id = document_id
        self.hold_id = hold_id
        super().__init__(f"Document {document_id} cannot be deleted: referenced by preservation hold {hold_id}")


class DocumentProtectedBySatisfiedEvidenceError(DomainError):
    def __init__(self, document_id: int, evidence_type: str):
        self.document_id = document_id
        self.evidence_type = evidence_type
        super().__init__(f"Document {document_id} cannot be deleted: it satisfies required evidence {evidence_type!r}")


class InvalidHoldTransitionError(DomainError):
    """Raised by repositories.confirm_hold for any starting status other
    than PROPOSED. This is the only mechanism that can produce this error —
    there is deliberately no general-purpose "set hold status" function.
    """

    def __init__(self, hold_id: int, current_status: str):
        self.hold_id = hold_id
        self.current_status = current_status
        super().__init__(f"Hold {hold_id} cannot be confirmed from status {current_status} (must be PROPOSED)")
