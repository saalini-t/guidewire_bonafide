import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client.js";
import NewClaimForm from "../components/NewClaimForm.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const RISK_TONE = { HIGH: "danger", MEDIUM: "warning", LOW: "success" };

export default function ClaimsPage() {
  const [claims, setClaims] = useState(null);
  const [risks, setRisks] = useState({});
  const [error, setError] = useState(null);

  // Exposed so the error state below can offer a real retry instead of a
  // dead end — a transient failure (backend not up yet, a momentary
  // network blip) would otherwise require the user to know to hard-refresh
  // the browser tab, which looks indistinguishable from "the app is broken".
  const load = useCallback(async () => {
    setError(null);
    try {
      const list = await api.listClaims();
      setClaims(list);

      const entries = await Promise.all(
        list.map(async (claim) => {
          try {
            const analysis = await api.getAnalysis(claim.claim_id);
            return [claim.claim_id, analysis.risk_level];
          } catch {
            return [claim.claim_id, null];
          }
        })
      );
      setRisks(Object.fromEntries(entries));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load claims.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <div className="panel">
        <p className="form-error">{error}</p>
        <button type="button" className="button button--secondary" onClick={load}>
          Retry
        </button>
      </div>
    );
  }
  if (!claims) return <p className="panel__empty">Loading claims…</p>;

  return (
    <>
      <div style={{ marginBottom: "16px" }}>
        <NewClaimForm onCreated={load} />
      </div>
      <section className="panel">
        <h1 className="page-title">Claims</h1>
        <table className="table">
        <thead>
          <tr>
            <th>Claim ID</th>
            <th>Type</th>
            <th>Status</th>
            <th>Repair Status</th>
            <th>Upcoming Business Event</th>
            <th>Preservation Risk</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => (
            <tr key={claim.claim_id}>
              <td>
                <Link to={`/claims/${claim.claim_id}`}>{claim.claim_id}</Link>
              </td>
              <td>{claim.claim_type}</td>
              <td>{claim.status}</td>
              <td>{claim.repair_status}</td>
              <td>{claim.upcoming_business_event ?? "—"}</td>
              <td>
                {risks[claim.claim_id] ? (
                  <StatusBadge tone={RISK_TONE[risks[claim.claim_id]] ?? "neutral"}>
                    {risks[claim.claim_id]}
                  </StatusBadge>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
        </table>
      </section>
    </>
  );
}
