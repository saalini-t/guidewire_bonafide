import { useState } from "react";
import { api, ApiError } from "../api/client.js";
import StatusBadge from "./StatusBadge.jsx";

const TONE_BY_STATUS = { PROPOSED: "warning", ACTIVE: "danger", RELEASED: "neutral" };
const LABEL_BY_STATUS = {
  PROPOSED: "PRESERVATION HOLD PROPOSED",
  ACTIVE: "ACTIVE HOLD",
  RELEASED: "RELEASED",
};

export default function HoldsPanel({ claimId, holds, onMutated }) {
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);

  async function handleConfirm(holdId) {
    setError(null);
    setBusyId(holdId);
    try {
      // MVP does not implement authentication; "adjuster.demo" stands in
      // for the confirming user (see docs/LIMITATIONS.md).
      await api.confirmHold(claimId, holdId, "adjuster.demo");
      await onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not confirm hold.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Preservation Hold</h2>
      {error && <p className="form-error">{error}</p>}
      {holds.length === 0 ? (
        <p className="panel__empty">No preservation hold has been proposed for this claim.</p>
      ) : (
        <ul className="hold-list">
          {holds.map((hold) => (
            <li key={hold.id} className="hold-list__item">
              <div className="hold-list__row">
                <StatusBadge tone={TONE_BY_STATUS[hold.status] ?? "neutral"}>
                  {LABEL_BY_STATUS[hold.status] ?? hold.status}
                </StatusBadge>
                {hold.confidence != null && (
                  <span className="hold-list__confidence">{Math.round(hold.confidence * 100)}% confidence</span>
                )}
              </div>
              <p className="hold-list__reason">{hold.trigger_reason}</p>
              {hold.status === "PROPOSED" && (
                <button
                  type="button"
                  className="button button--primary"
                  disabled={busyId === hold.id}
                  onClick={() => handleConfirm(hold.id)}
                >
                  {busyId === hold.id ? "Confirming…" : "Confirm Hold"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
