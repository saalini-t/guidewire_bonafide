import { useState } from "react";
import { api, ApiError } from "../api/client.js";

// Validation (non-empty + "meaningful" justification, non-empty user/role)
// is enforced by the backend (app/schemas.py OverrideRequest) — this form
// does not duplicate that logic, it just displays whatever the backend
// returns.
export default function OverrideForm({ claimId, upcomingBusinessEvent, onMutated }) {
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState("");
  const [role, setRole] = useState("");
  const [justification, setJustification] = useState("");
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Nothing to override when no business event is pending — except once
  // this form has already succeeded once, since a successful override is
  // exactly what clears upcomingBusinessEvent. Without the `success` guard
  // here, the confirmation message would vanish the instant the parent
  // refetches claim state after the override it just reported succeeding.
  if (!upcomingBusinessEvent && !success) {
    return null;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      const result = await api.applyOverride(claimId, {
        user,
        role,
        justification,
        action: upcomingBusinessEvent,
      });
      setSuccess(result.log);
      setJustification("");
      await onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Override failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Preservation Override</h2>
      {!open ? (
        <button type="button" className="button button--danger" onClick={() => setOpen(true)}>
          Override Preservation Rule
        </button>
      ) : (
        <form onSubmit={handleSubmit}>
          <p className="override-form__notice">
            This MVP does not implement real authentication. The user and role below are captured as
            supplied and are not verified credentials.
          </p>
          <label className="field">
            <span>User</span>
            <input value={user} onChange={(event) => setUser(event.target.value)} placeholder="supervisor.jane" />
          </label>
          <label className="field">
            <span>Role</span>
            <input value={role} onChange={(event) => setRole(event.target.value)} placeholder="Supervisor" />
          </label>
          <label className="field">
            <span>Justification (required, must be meaningful)</span>
            <textarea
              value={justification}
              onChange={(event) => setJustification(event.target.value)}
              rows={3}
              placeholder="Explain why this override is necessary..."
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          {success && (
            <p className="form-success">
              Override applied and logged ({success.event_type}) for {success.user}.
            </p>
          )}
          {upcomingBusinessEvent && (
            <div className="override-form__actions">
              <button type="submit" className="button button--danger" disabled={submitting}>
                {submitting ? "Submitting…" : `Override ${upcomingBusinessEvent}`}
              </button>
              <button type="button" className="button button--secondary" onClick={() => setOpen(false)}>
                Cancel
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
