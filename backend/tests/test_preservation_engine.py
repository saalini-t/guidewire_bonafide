"""Unit tests for the deterministic preservation engine. No DB, no AI —
pure function tests against plain objects that satisfy EvidenceLike /
ClaimLike.
"""
from dataclasses import dataclass

from app.enums import EvidenceType, ExpiryTrigger, RiskLevel
from app.preservation_engine import analyze_preservation


@dataclass
class FakeClaim:
    claim_id: str
    upcoming_business_event: ExpiryTrigger | None


@dataclass
class FakeEvidence:
    evidence_type: EvidenceType
    required: bool
    satisfied: bool
    expiry_trigger: ExpiryTrigger


def _item(evidence_type, satisfied, trigger=ExpiryTrigger.REPAIR_AUTHORIZATION, required=True):
    return FakeEvidence(evidence_type=evidence_type, required=required, satisfied=satisfied, expiry_trigger=trigger)


def test_no_upcoming_event_is_always_low_even_with_missing_evidence():
    claim = FakeClaim(claim_id="CLM-X", upcoming_business_event=None)
    items = [_item(EvidenceType.VEHICLE_PHOTOGRAPHS, satisfied=False)]

    result = analyze_preservation(claim, items)

    assert result.risk_level == RiskLevel.LOW
    assert result.at_risk_evidence == []
    assert result.missing_evidence == [EvidenceType.VEHICLE_PHOTOGRAPHS]


def test_zero_at_risk_items_is_low():
    claim = FakeClaim(claim_id="CLM-X", upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION)
    items = [_item(EvidenceType.VEHICLE_PHOTOGRAPHS, satisfied=True)]

    result = analyze_preservation(claim, items)

    assert result.risk_level == RiskLevel.LOW
    assert result.at_risk_evidence == []


def test_one_at_risk_item_is_medium():
    claim = FakeClaim(claim_id="CLM-X", upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION)
    items = [
        _item(EvidenceType.VEHICLE_PHOTOGRAPHS, satisfied=False),
        _item(EvidenceType.POLICE_REPORT, satisfied=False, trigger=ExpiryTrigger.CLAIM_CLOSURE),
    ]

    result = analyze_preservation(claim, items)

    assert result.risk_level == RiskLevel.MEDIUM
    assert result.at_risk_evidence == [EvidenceType.VEHICLE_PHOTOGRAPHS]
    # Police Report is missing too, but its trigger doesn't match the
    # upcoming event, so it is not "at risk" yet.
    assert EvidenceType.POLICE_REPORT in result.missing_evidence
    assert EvidenceType.POLICE_REPORT not in result.at_risk_evidence


def test_two_or_more_at_risk_items_is_high():
    claim = FakeClaim(claim_id="CLM-X", upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION)
    items = [
        _item(EvidenceType.VEHICLE_PHOTOGRAPHS, satisfied=False),
        _item(EvidenceType.REPAIR_APPRAISAL, satisfied=False),
    ]

    result = analyze_preservation(claim, items)

    assert result.risk_level == RiskLevel.HIGH


def test_not_required_items_are_never_missing_or_at_risk():
    claim = FakeClaim(claim_id="CLM-X", upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION)
    items = [_item(EvidenceType.VEHICLE_PHOTOGRAPHS, satisfied=False, required=False)]

    result = analyze_preservation(claim, items)

    assert result.missing_evidence == []
    assert result.at_risk_evidence == []
    assert result.risk_level == RiskLevel.LOW


def test_clm_10042_demo_claim_is_high_with_exact_three_at_risk_items():
    claim = FakeClaim(claim_id="CLM-10042", upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION)
    items = [
        _item(EvidenceType.VEHICLE_PHOTOGRAPHS, satisfied=False),
        _item(EvidenceType.POLICE_REPORT, satisfied=True, trigger=ExpiryTrigger.CLAIM_CLOSURE),
        _item(EvidenceType.REPAIR_APPRAISAL, satisfied=False),
        _item(EvidenceType.VEHICLE_INSPECTION, satisfied=True),
        _item(EvidenceType.RECORDED_STATEMENT, satisfied=False),
        _item(EvidenceType.REPAIR_ESTIMATE, satisfied=True),
    ]

    result = analyze_preservation(claim, items)

    assert result.risk_level == RiskLevel.HIGH
    assert set(result.at_risk_evidence) == {
        EvidenceType.VEHICLE_PHOTOGRAPHS,
        EvidenceType.REPAIR_APPRAISAL,
        EvidenceType.RECORDED_STATEMENT,
    }
    assert "RepairAuthorization" in result.explanation
    assert "RepairAuthorization" in result.recommendation
