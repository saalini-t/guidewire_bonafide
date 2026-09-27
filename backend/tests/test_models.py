import datetime as dt

from app.enums import ExpiryTrigger, PreservationEventType
from app.models import Claim, EvidenceItem, PreservationLog
from app.repositories import add_evidence_item, add_log, create_claim


def test_deleting_claim_cascades_to_evidence_and_logs(db_session):
    claim = create_claim(
        db_session,
        claim_id="CLM-CASCADE",
        policy_id="POL-1",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 1, 1),
        claimant="Test Claimant",
        description="synthetic",
    )
    add_evidence_item(
        db_session,
        claim_id=claim.claim_id,
        evidence_type="Vehicle Photographs",
        expiry_trigger=ExpiryTrigger.REPAIR_AUTHORIZATION,
    )
    add_log(db_session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user="tester")
    db_session.flush()

    db_session.delete(claim)
    db_session.flush()

    assert db_session.query(EvidenceItem).filter_by(claim_id="CLM-CASCADE").count() == 0
    assert db_session.query(PreservationLog).filter_by(claim_id="CLM-CASCADE").count() == 0


def test_preservation_log_detail_round_trips_as_jsonb(db_session):
    claim = create_claim(
        db_session,
        claim_id="CLM-JSON",
        policy_id="POL-1",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 1, 1),
        claimant="Test Claimant",
        description="synthetic",
    )
    log = add_log(
        db_session,
        claim_id=claim.claim_id,
        event_type=PreservationEventType.LITIGATION_SIGNAL_DETECTED,
        user="tester",
        detail={"signal_type": "attorney_representation", "confidence": 0.91},
    )
    db_session.flush()
    db_session.expire(log)

    reloaded = db_session.get(PreservationLog, log.id)

    assert reloaded.detail == {"signal_type": "attorney_representation", "confidence": 0.91}
