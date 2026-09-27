import StatusBadge from "./StatusBadge.jsx";

// Status is derived only from what the backend already computed
// (item.satisfied, analysis.at_risk_evidence) — no risk logic is
// reimplemented here.
function evidenceStatus(item, analysis) {
  if (item.satisfied) return { label: "SATISFIED", tone: "success" };
  if (analysis?.at_risk_evidence?.includes(item.evidence_type)) {
    return { label: "AT RISK", tone: "danger" };
  }
  return { label: "MISSING", tone: "neutral" };
}

export default function EvidenceChecklist({ evidence, analysis }) {
  return (
    <section className="panel">
      <h2 className="panel__title">Evidence Checklist</h2>
      {evidence.length === 0 ? (
        <p className="panel__empty">No evidence items on this claim.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Evidence Type</th>
              <th>Required</th>
              <th>Status</th>
              <th>Expiry Trigger</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((item) => {
              const status = evidenceStatus(item, analysis);
              const isUpcomingTrigger = analysis?.upcoming_event && item.expiry_trigger === analysis.upcoming_event;
              return (
                <tr key={item.id}>
                  <td>{item.evidence_type}</td>
                  <td>{item.required ? "Yes" : "No"}</td>
                  <td>
                    <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                  </td>
                  <td className={isUpcomingTrigger ? "table__cell--warning" : undefined}>
                    {item.expiry_trigger}
                    {isUpcomingTrigger && <span className="table__flag"> ⚠ upcoming</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
