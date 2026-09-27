import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client.js";
import RiskBanner from "../components/RiskBanner.jsx";
import EvidenceChecklist from "../components/EvidenceChecklist.jsx";
import DocumentUpload from "../components/DocumentUpload.jsx";
import HoldsPanel from "../components/HoldsPanel.jsx";
import OverrideForm from "../components/OverrideForm.jsx";
import Timeline from "../components/Timeline.jsx";

export default function ClaimDetailPage() {
  const { claimId } = useParams();
  const [claim, setClaim] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [holds, setHolds] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [notFound, setNotFound] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [claimData, evidenceData, analysisData, holdsData, logsData] = await Promise.all([
        api.getClaim(claimId),
        api.getEvidence(claimId),
        api.getAnalysis(claimId),
        api.getHolds(claimId),
        api.getPreservationLog(claimId),
      ]);
      setClaim(claimData);
      setEvidence(evidenceData);
      setAnalysis(analysisData);
      setHolds(holdsData);
      setLogs(logsData);
      setError(null);
      setNotFound(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not reach the Bona Fide backend.");
      }
    }
  }, [claimId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (notFound) {
    return (
      <div className="panel">
        <p>Claim {claimId} was not found.</p>
        <Link to="/claims">Back to claims</Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel">
        <p className="form-error">{error}</p>
        <button type="button" className="button button--secondary" onClick={refresh}>
          Retry
        </button>
      </div>
    );
  }
  if (!claim) return <p className="panel__empty">Loading claim…</p>;

  return (
    <div className="claim-detail">
      <Link to="/claims" className="back-link">
        ← All claims
      </Link>
      <header className="claim-detail__header">
        <h1 className="page-title">{claim.claim_id}</h1>
        <dl className="claim-detail__facts">
          <div>
            <dt>Claim Type</dt>
            <dd>{claim.claim_type}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{claim.status}</dd>
          </div>
          <div>
            <dt>Repair Status</dt>
            <dd>{claim.repair_status}</dd>
          </div>
          <div>
            <dt>Upcoming Business Event</dt>
            <dd>{claim.upcoming_business_event ?? "None"}</dd>
          </div>
          <div>
            <dt>Claimant</dt>
            <dd>{claim.claimant}</dd>
          </div>
        </dl>
      </header>

      <RiskBanner analysis={analysis} />
      <EvidenceChecklist evidence={evidence} analysis={analysis} />
      <DocumentUpload claimId={claimId} onMutated={refresh} />
      <HoldsPanel claimId={claimId} holds={holds} onMutated={refresh} />
      <OverrideForm claimId={claimId} upcomingBusinessEvent={claim.upcoming_business_event} onMutated={refresh} />
      <Timeline entries={logs} />
    </div>
  );
}
