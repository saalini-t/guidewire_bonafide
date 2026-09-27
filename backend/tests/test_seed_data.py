import datetime as dt

from app.enums import EvidenceType, HoldStatus, RiskLevel
from app.preservation_engine import analyze_preservation
from app.repositories import create_document, get_claim, list_evidence_items, list_holds
from app.seed_data import reset, seed


def test_seed_creates_five_claims_covering_all_required_scenarios(db_session):
    reset(db_session)
    claims = seed(db_session)

    assert len(claims) == 5
    claim_ids = {c.claim_id for c in claims}
    assert claim_ids == {"CLM-10042", "CLM-20011", "CLM-20022", "CLM-20033", "CLM-20044"}


def test_clm_10042_is_high_risk_with_expected_at_risk_items(db_session):
    reset(db_session)
    seed(db_session)

    claim = get_claim(db_session, "CLM-10042")
    evidence = list_evidence_items(db_session, "CLM-10042")

    result = analyze_preservation(claim, evidence)

    assert result.risk_level == RiskLevel.HIGH
    assert set(result.at_risk_evidence) == {
        EvidenceType.VEHICLE_PHOTOGRAPHS,
        EvidenceType.REPAIR_APPRAISAL,
        EvidenceType.RECORDED_STATEMENT,
    }


def test_clm_20011_is_low_risk(db_session):
    reset(db_session)
    seed(db_session)

    claim = get_claim(db_session, "CLM-20011")
    evidence = list_evidence_items(db_session, "CLM-20011")

    result = analyze_preservation(claim, evidence)

    assert result.risk_level == RiskLevel.LOW


def test_clm_20022_is_medium_risk(db_session):
    reset(db_session)
    seed(db_session)

    claim = get_claim(db_session, "CLM-20022")
    evidence = list_evidence_items(db_session, "CLM-20022")

    result = analyze_preservation(claim, evidence)

    assert result.risk_level == RiskLevel.MEDIUM
    assert result.at_risk_evidence == [EvidenceType.REPAIR_APPRAISAL]


def test_clm_20033_is_high_risk(db_session):
    reset(db_session)
    seed(db_session)

    claim = get_claim(db_session, "CLM-20033")
    evidence = list_evidence_items(db_session, "CLM-20033")

    result = analyze_preservation(claim, evidence)

    assert result.risk_level == RiskLevel.HIGH


def test_reset_succeeds_even_when_evidence_is_satisfied_by_a_document(db_session):
    """Regression test: EvidenceItem.satisfying_document_id references
    Document.id, so reset() must delete evidence rows before document rows
    — deleting documents first raises a ForeignKeyViolation once any
    evidence item has actually been satisfied by a document (as happens
    once the real classify workflow runs against seeded data).
    """
    reset(db_session)
    seed(db_session)
    document = create_document(
        db_session, claim_id="CLM-10042", filename="test.txt", storage_path="CLM-10042/test.txt", text="test"
    )
    evidence = next(
        e for e in list_evidence_items(db_session, "CLM-10042") if e.evidence_type == EvidenceType.VEHICLE_PHOTOGRAPHS
    )
    evidence.satisfied = True
    evidence.satisfied_date = dt.datetime.now(dt.timezone.utc)
    evidence.satisfying_document_id = document.id
    db_session.flush()

    reset(db_session)  # must not raise ForeignKeyViolation

    assert get_claim(db_session, "CLM-10042") is None


def test_clm_20044_has_active_hold(db_session):
    reset(db_session)
    seed(db_session)

    holds = list_holds(db_session, "CLM-20044")

    assert len(holds) == 1
    assert holds[0].status == HoldStatus.ACTIVE
