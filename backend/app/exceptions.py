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


class InvalidHoldTransitionError(DomainError):
    """Raised by repositories.confirm_hold for any starting status other
    than PROPOSED. This is the only mechanism that can produce this error —
    there is deliberately no general-purpose "set hold status" function.
    """

    def __init__(self, hold_id: int, current_status: str):
        self.hold_id = hold_id
        self.current_status = current_status
        super().__init__(f"Hold {hold_id} cannot be confirmed from status {current_status} (must be PROPOSED)")
