"""Single source of truth for which evidence items a claim of a given type
requires, and which business event expires each one. Used by both
app.seed_data (synthetic demo claims) and app.services (real claim
creation) — do not duplicate this map elsewhere.
"""
from app.enums import EvidenceType, ExpiryTrigger

# The only claim type this taxonomy currently covers. Claim creation
# rejects anything else rather than silently generating no evidence
# requirements for a type nobody has defined a taxonomy for.
PERSONAL_AUTO = "PersonalAuto"

# Default expiry-trigger mapping for the six-item Personal Auto evidence
# taxonomy (docs/DATA_MODEL.md documents this as the configurable default).
PERSONAL_AUTO_EVIDENCE_TRIGGER_MAP: dict[EvidenceType, ExpiryTrigger] = {
    EvidenceType.VEHICLE_PHOTOGRAPHS: ExpiryTrigger.REPAIR_AUTHORIZATION,
    EvidenceType.POLICE_REPORT: ExpiryTrigger.CLAIM_CLOSURE,
    EvidenceType.REPAIR_APPRAISAL: ExpiryTrigger.REPAIR_AUTHORIZATION,
    EvidenceType.VEHICLE_INSPECTION: ExpiryTrigger.REPAIR_AUTHORIZATION,
    EvidenceType.RECORDED_STATEMENT: ExpiryTrigger.REPAIR_AUTHORIZATION,
    EvidenceType.REPAIR_ESTIMATE: ExpiryTrigger.REPAIR_AUTHORIZATION,
}

EVIDENCE_TAXONOMY_BY_CLAIM_TYPE: dict[str, dict[EvidenceType, ExpiryTrigger]] = {
    PERSONAL_AUTO: PERSONAL_AUTO_EVIDENCE_TRIGGER_MAP,
}


def evidence_taxonomy_for(claim_type: str) -> dict[EvidenceType, ExpiryTrigger]:
    return EVIDENCE_TAXONOMY_BY_CLAIM_TYPE[claim_type]
