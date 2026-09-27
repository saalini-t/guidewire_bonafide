"""Controlled vocabularies used across models, the preservation engine, and
the API layer. These are the taxonomies referenced by docs/DATA_MODEL and
docs/PRESERVATION_LOGIC — this module is the single source of truth for them.
"""
from enum import Enum


class EvidenceType(str, Enum):
    VEHICLE_PHOTOGRAPHS = "Vehicle Photographs"
    POLICE_REPORT = "Police Report"
    REPAIR_APPRAISAL = "Repair Appraisal"
    VEHICLE_INSPECTION = "Vehicle Inspection"
    RECORDED_STATEMENT = "Recorded Statement"
    REPAIR_ESTIMATE = "Repair Estimate"


class DocumentClass(str, Enum):
    """Classification classes the AI service may assign to a document.
    Same six evidence types, plus OTHER for anything that doesn't match.
    """
    VEHICLE_PHOTOGRAPHS = "Vehicle Photographs"
    POLICE_REPORT = "Police Report"
    REPAIR_APPRAISAL = "Repair Appraisal"
    VEHICLE_INSPECTION = "Vehicle Inspection"
    RECORDED_STATEMENT = "Recorded Statement"
    REPAIR_ESTIMATE = "Repair Estimate"
    OTHER = "Other"


class ExpiryTrigger(str, Enum):
    REPAIR_AUTHORIZATION = "RepairAuthorization"
    CLAIM_CLOSURE = "ClaimClosure"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClassificationStatus(str, Enum):
    PENDING = "PENDING"          # uploaded, not yet classified
    CLASSIFIED = "CLASSIFIED"    # AI classified at/above confidence threshold
    MANUAL_REVIEW = "MANUAL_REVIEW"  # low confidence, AI failure, or invalid AI response


class LitigationSignal(str, Enum):
    ATTORNEY_REPRESENTATION = "attorney_representation"
    DEMAND_LETTER = "demand_letter"
    RECORDS_REQUEST = "records_request"
    NONE = "none"


class HoldStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"


class PreservationEventType(str, Enum):
    CLAIM_CREATED = "CLAIM_CREATED"
    ANALYSIS_RUN = "ANALYSIS_RUN"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_CLASSIFIED = "DOCUMENT_CLASSIFIED"
    EVIDENCE_SATISFIED = "EVIDENCE_SATISFIED"
    LITIGATION_SIGNAL_DETECTED = "LITIGATION_SIGNAL_DETECTED"
    HOLD_PROPOSED = "HOLD_PROPOSED"
    HOLD_CONFIRMED = "HOLD_CONFIRMED"
    HOLD_RELEASED = "HOLD_RELEASED"
    OVERRIDE_APPLIED = "OVERRIDE_APPLIED"


class AIProvider(str, Enum):
    DETERMINISTIC = "deterministic"
    OLLAMA = "ollama"
