import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client.js";

// Claim type and repair status options mirror exactly what the backend
// currently supports (app.evidence_taxonomy / app.schemas) — this form
// does not invent values the backend would reject.
const CLAIM_TYPES = ["PersonalAuto"];
const REPAIR_STATUSES = ["PENDING", "COMPLETE", "NOT_APPLICABLE"];

const initialForm = {
  claimant: "",
  policyId: "",
  claimType: "PersonalAuto",
  lossDate: "",
  description: "",
  repairStatus: "PENDING",
};

export default function NewClaimForm({ onCreated }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function update(field) {
    return (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const claim = await api.createClaim({
        claimant: form.claimant,
        policy_id: form.policyId,
        claim_type: form.claimType,
        loss_date: form.lossDate,
        description: form.description,
        repair_status: form.repairStatus,
      });
      setForm(initialForm);
      setOpen(false);
      await onCreated?.();
      navigate(`/claims/${claim.claim_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create claim.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="button button--primary" onClick={() => setOpen(true)}>
        + New Claim
      </button>
    );
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <h2 className="panel__title">Create Claim</h2>

      <label className="field">
        <span>Claimant Name</span>
        <input value={form.claimant} onChange={update("claimant")} required />
      </label>

      <label className="field">
        <span>Policy Number</span>
        <input value={form.policyId} onChange={update("policyId")} required />
      </label>

      <label className="field">
        <span>Claim Type</span>
        <select value={form.claimType} onChange={update("claimType")}>
          {CLAIM_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Loss Date</span>
        <input type="date" value={form.lossDate} onChange={update("lossDate")} required />
      </label>

      <label className="field">
        <span>Description</span>
        <textarea value={form.description} onChange={update("description")} rows={3} required />
      </label>

      <label className="field">
        <span>Repair Status</span>
        <select value={form.repairStatus} onChange={update("repairStatus")}>
          {REPAIR_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="override-form__actions">
        <button type="submit" className="button button--primary" disabled={submitting}>
          {submitting ? "Creating…" : "Create Claim"}
        </button>
        <button type="button" className="button button--secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
