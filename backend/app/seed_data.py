"""Synthetic demo data. All claimants, policies, and descriptions below are
fictional — no real personal information. Five claims, covering LOW,
MEDIUM, HIGH (x2, including the canonical demo claim CLM-10042), and one
claim with an ACTIVE preservation hold.
"""
import datetime as dt

from sqlalchemy.orm import Session

from app.enums import EvidenceType, ExpiryTrigger, HoldStatus, PreservationEventType
from app.evidence_taxonomy import PERSONAL_AUTO_EVIDENCE_TRIGGER_MAP as EVIDENCE_TRIGGER_MAP
from app.models import Claim, Document, EvidenceItem, ImageAnalysis, PreservationHold, PreservationLog
from app.repositories import add_evidence_item, add_log, confirm_hold, create_claim, create_hold

SEEDED_BY = "seed_script"


def _seed_evidence(session: Session, claim_id: str, satisfaction: dict[EvidenceType, bool]) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    for evidence_type, trigger in EVIDENCE_TRIGGER_MAP.items():
        satisfied = satisfaction[evidence_type]
        add_evidence_item(
            session,
            claim_id=claim_id,
            evidence_type=evidence_type,
            expiry_trigger=trigger,
            required=True,
            satisfied=satisfied,
            satisfied_date=now if satisfied else None,
        )


def reset(session: Session) -> None:
    """Delete all seeded data. Fine for an MVP demo dataset; not intended
    for a production data-retention path.
    """
    session.query(PreservationLog).delete()
    session.query(PreservationHold).delete()
    # EvidenceItem.satisfying_document_id and ImageAnalysis.document_id both
    # reference Document.id, so both must go before document rows.
    session.query(EvidenceItem).delete()
    session.query(ImageAnalysis).delete()
    session.query(Document).delete()
    session.query(Claim).delete()


def seed(session: Session) -> list[Claim]:
    claims: list[Claim] = []

    # CLM-10042 — the canonical demo claim. HIGH risk: 3 unsatisfied
    # RepairAuthorization-triggered items (Vehicle Photographs, Repair
    # Appraisal, Recorded Statement).
    claim = create_claim(
        session,
        claim_id="CLM-10042",
        policy_id="POL-778142",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 8, 12),
        claimant="Jordan Reyes",
        description=(
            "Single-vehicle collision with guardrail. Repair shop has requested authorization "
            "to begin bodywork; several pre-repair evidence items have not yet been captured."
        ),
        repair_status="PENDING",
        upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION,
    )
    _seed_evidence(
        session,
        claim.claim_id,
        {
            EvidenceType.VEHICLE_PHOTOGRAPHS: False,
            EvidenceType.POLICE_REPORT: True,
            EvidenceType.REPAIR_APPRAISAL: False,
            EvidenceType.VEHICLE_INSPECTION: True,
            EvidenceType.RECORDED_STATEMENT: False,
            EvidenceType.REPAIR_ESTIMATE: True,
        },
    )
    add_log(session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user=SEEDED_BY)
    claims.append(claim)

    # CLM-20011 — LOW risk: repairs already complete, all evidence
    # preserved, no upcoming business event still pending.
    claim = create_claim(
        session,
        claim_id="CLM-20011",
        policy_id="POL-441029",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 6, 3),
        claimant="Priya Nakamura",
        description="Parking-lot fender bender. Repairs completed after full pre-repair documentation.",
        repair_status="COMPLETE",
        upcoming_business_event=None,
    )
    _seed_evidence(session, claim.claim_id, dict.fromkeys(EVIDENCE_TRIGGER_MAP, True))
    add_log(session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user=SEEDED_BY)
    claims.append(claim)

    # CLM-20022 — MEDIUM risk: exactly one at-risk item (Repair Appraisal).
    claim = create_claim(
        session,
        claim_id="CLM-20022",
        policy_id="POL-552087",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 9, 1),
        claimant="Marcus Webb",
        description="Rear-end collision at low speed. Repair authorization pending; appraisal outstanding.",
        repair_status="PENDING",
        upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION,
    )
    _seed_evidence(
        session,
        claim.claim_id,
        {
            EvidenceType.VEHICLE_PHOTOGRAPHS: True,
            EvidenceType.POLICE_REPORT: True,
            EvidenceType.REPAIR_APPRAISAL: False,
            EvidenceType.VEHICLE_INSPECTION: True,
            EvidenceType.RECORDED_STATEMENT: True,
            EvidenceType.REPAIR_ESTIMATE: True,
        },
    )
    add_log(session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user=SEEDED_BY)
    claims.append(claim)

    # CLM-20033 — HIGH risk (second example, different evidence mix):
    # Vehicle Photographs, Repair Appraisal, Vehicle Inspection unsatisfied.
    claim = create_claim(
        session,
        claim_id="CLM-20033",
        policy_id="POL-663311",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 9, 10),
        claimant="Elena Cho",
        description="Multi-vehicle intersection collision. Repair authorization imminent; most pre-repair evidence outstanding.",
        repair_status="PENDING",
        upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION,
    )
    _seed_evidence(
        session,
        claim.claim_id,
        {
            EvidenceType.VEHICLE_PHOTOGRAPHS: False,
            EvidenceType.POLICE_REPORT: True,
            EvidenceType.REPAIR_APPRAISAL: False,
            EvidenceType.VEHICLE_INSPECTION: False,
            EvidenceType.RECORDED_STATEMENT: True,
            EvidenceType.REPAIR_ESTIMATE: True,
        },
    )
    add_log(session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user=SEEDED_BY)
    claims.append(claim)

    # CLM-20044 — evidence fully preserved (engine risk LOW on its own),
    # but an ACTIVE preservation hold from a litigation signal blocks
    # claim closure regardless of evidence completeness.
    claim = create_claim(
        session,
        claim_id="CLM-20044",
        policy_id="POL-774920",
        claim_type="PersonalAuto",
        loss_date=dt.date(2026, 5, 22),
        claimant="Dana Whitfield",
        description="Rear-end collision; claimant retained counsel. Repairs complete; closure blocked pending hold review.",
        repair_status="COMPLETE",
        upcoming_business_event=ExpiryTrigger.CLAIM_CLOSURE,
    )
    _seed_evidence(session, claim.claim_id, dict.fromkeys(EVIDENCE_TRIGGER_MAP, True))
    add_log(session, claim_id=claim.claim_id, event_type=PreservationEventType.CLAIM_CREATED, user=SEEDED_BY)
    add_log(
        session,
        claim_id=claim.claim_id,
        event_type=PreservationEventType.LITIGATION_SIGNAL_DETECTED,
        user=SEEDED_BY,
        detail={"signal_type": "attorney_representation", "confidence": 0.93},
    )
    hold = create_hold(
        session,
        claim_id=claim.claim_id,
        trigger_reason="Attorney representation letter received from claimant's counsel.",
        trigger_source="litigation_signal:attorney_representation",
        confidence=0.93,
        status=HoldStatus.PROPOSED,
    )
    add_log(
        session,
        claim_id=claim.claim_id,
        event_type=PreservationEventType.HOLD_PROPOSED,
        user=SEEDED_BY,
        detail={"hold_id": hold.id},
    )
    # Confirmation goes through the same guarded state-machine function the
    # API uses (app.repositories.confirm_hold) — no raw status assignment.
    confirm_hold(session, hold.id, user="adjuster.demo")
    claims.append(claim)

    return claims


def main() -> None:
    from app.db import session_scope

    with session_scope() as session:
        reset(session)
        seeded = seed(session)
        print(f"Seeded {len(seeded)} claims: {', '.join(c.claim_id for c in seeded)}")


if __name__ == "__main__":
    main()
