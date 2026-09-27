"""Deterministic preservation-risk engine.

Pure functions only: no AI calls, no database access, no I/O. Takes claim +
evidence data, returns a PreservationAnalysis. This is the fail-closed half
of the system (see docs/ARCHITECTURE.md) — AI availability has no bearing
on anything in this module.

Thresholds (exact, by design — not tunable at runtime for the MVP):

    at-risk evidence count == 0  -> LOW
    at-risk evidence count == 1  -> MEDIUM
    at-risk evidence count >= 2  -> HIGH

"At risk" = required, unsatisfied, and its expiry_trigger matches the
claim's upcoming_business_event. If a claim has no upcoming_business_event,
nothing can be at risk (there is no imminent irreversible event), so risk
is always LOW even if evidence is missing. "Missing" evidence (required +
unsatisfied, regardless of trigger match) is reported separately from
"at risk" evidence, since evidence expiry is bound to business events, not
merely to being unsatisfied.
"""
from dataclasses import dataclass
from typing import Protocol

from app.enums import EvidenceType, ExpiryTrigger, RiskLevel

HIGH_RISK_AT_RISK_COUNT = 2
MEDIUM_RISK_AT_RISK_COUNT = 1


class EvidenceLike(Protocol):
    evidence_type: EvidenceType
    required: bool
    satisfied: bool
    expiry_trigger: ExpiryTrigger


class ClaimLike(Protocol):
    claim_id: str
    upcoming_business_event: ExpiryTrigger | None


@dataclass(frozen=True)
class PreservationAnalysis:
    claim_id: str
    risk_level: RiskLevel
    upcoming_event: ExpiryTrigger | None
    missing_evidence: list[EvidenceType]
    at_risk_evidence: list[EvidenceType]
    explanation: str
    recommendation: str


def analyze_preservation(claim: ClaimLike, evidence_items: list[EvidenceLike]) -> PreservationAnalysis:
    missing = [e.evidence_type for e in evidence_items if e.required and not e.satisfied]

    if claim.upcoming_business_event is None:
        at_risk: list[EvidenceType] = []
    else:
        at_risk = [
            e.evidence_type
            for e in evidence_items
            if e.required and not e.satisfied and e.expiry_trigger == claim.upcoming_business_event
        ]

    if len(at_risk) >= HIGH_RISK_AT_RISK_COUNT:
        risk = RiskLevel.HIGH
    elif len(at_risk) == MEDIUM_RISK_AT_RISK_COUNT:
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.LOW

    return PreservationAnalysis(
        claim_id=claim.claim_id,
        risk_level=risk,
        upcoming_event=claim.upcoming_business_event,
        missing_evidence=missing,
        at_risk_evidence=at_risk,
        explanation=_explain(claim, at_risk),
        recommendation=_recommend(claim, risk, at_risk),
    )


def _explain(claim: ClaimLike, at_risk: list[EvidenceType]) -> str:
    if claim.upcoming_business_event is None:
        return "No upcoming business event is scheduled, so no evidence is currently at risk."
    event = claim.upcoming_business_event.value
    if not at_risk:
        return f"{event} is pending, but all evidence required before it has already been preserved."
    items = ", ".join(e.value for e in at_risk)
    return (
        f"{event} is pending. {len(at_risk)} required evidence item(s) have not been preserved "
        f"and will become materially harder to recover once {event} occurs: {items}."
    )


def _recommend(claim: ClaimLike, risk: RiskLevel, at_risk: list[EvidenceType]) -> str:
    if risk == RiskLevel.LOW:
        return "No preservation action required at this time."
    items = ", ".join(e.value for e in at_risk)
    event = claim.upcoming_business_event.value if claim.upcoming_business_event else "the upcoming event"
    return f"Preserve the following evidence before {event} occurs: {items}."
