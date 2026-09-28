from abc import ABC, abstractmethod
from enum import Enum
from typing import NamedTuple


class ImageAnalysisOutcome(NamedTuple):
    vehicle_present: bool
    damage_observed: bool
    damage_regions: list[str]
    image_quality: str
    relevance: str
    confidence: float
    explanation: str


class VisionFailureReason(str, Enum):
    """Sanitized diagnostic categories — never a raw exception message,
    never a secret/credential value, never image bytes. Safe to return in
    an HTTP response body and to persist in an audit log.
    """

    NOT_CONFIGURED = "not_configured"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    UNSUPPORTED_MODEL = "unsupported_model"
    MALFORMED_RESPONSE = "malformed_response"
    INTERNAL_ERROR = "internal_error"


class VisionProviderUnavailableError(Exception):
    """Raised for every failure mode: no provider configured, connection
    refused, timeout, non-JSON output, or a response that fails validation
    (out-of-range confidence, unknown enum values, missing fields). There is
    no deterministic fallback for image analysis (unlike text), so this is
    always the end of the line — the caller marks the document for manual
    review rather than inventing a result. `reason` is a coarse, sanitized
    category (see VisionFailureReason) for developer-facing diagnostics;
    the exception message itself may contain more detail but is logged
    server-side only, never returned to the frontend or persisted in the
    audit log.
    """

    def __init__(self, message: str, reason: VisionFailureReason = VisionFailureReason.INTERNAL_ERROR):
        super().__init__(message)
        self.reason = reason


class VisionProvider(ABC):
    name: str

    @abstractmethod
    def analyze_image(self, image_base64: str, mime_type: str) -> ImageAnalysisOutcome: ...
