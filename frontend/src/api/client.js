/**
 * Centralized API client. No component calls fetch() directly — everything
 * goes through the `api` object below, so the backend contract lives in
 * one place. The backend (deterministic preservation engine, risk levels,
 * evidence-satisfaction rules) is authoritative; this layer never
 * recalculates or duplicates that logic, only requests and displays it.
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function extractMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((entry) => entry.msg ?? JSON.stringify(entry)).join("; ");
  }
  return fallback;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError("Cannot reach the Bona Fide backend. Is it running?", 0, null);
  }

  let body = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(extractMessage(body, `Request failed (${response.status})`), response.status, body);
  }
  return body;
}

export const api = {
  listClaims: () => request("/api/claims"),
  getClaim: (claimId) => request(`/api/claims/${claimId}`),
  getEvidence: (claimId) => request(`/api/claims/${claimId}/evidence`),
  getAnalysis: (claimId) => request(`/api/claims/${claimId}/analysis`),
  getTimeline: (claimId) => request(`/api/claims/${claimId}/timeline`),
  getPreservationLog: (claimId) => request(`/api/claims/${claimId}/preservation-log`),
  getHolds: (claimId) => request(`/api/claims/${claimId}/holds`),
  uploadDocument: (claimId, { filename, text }) =>
    request(`/api/claims/${claimId}/documents`, {
      method: "POST",
      body: JSON.stringify({ filename, text }),
    }),
  classifyDocument: (claimId, documentId) =>
    request(`/api/claims/${claimId}/documents/${documentId}/classify`, { method: "POST" }),
  confirmHold: (claimId, holdId, user) =>
    request(`/api/claims/${claimId}/holds/${holdId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ user }),
    }),
  applyOverride: (claimId, payload) =>
    request(`/api/claims/${claimId}/override`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
