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
  // A FormData body (multipart file upload) must NOT get a manual
  // Content-Type — the browser sets one with the correct boundary. Only
  // JSON bodies get the default header, and only when the caller hasn't
  // already supplied their own headers.
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = isFormData ? options.headers : { "Content-Type": "application/json", ...options.headers };

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
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
  createClaim: (payload) => request("/api/claims", { method: "POST", body: JSON.stringify(payload) }),
  getClaim: (claimId) => request(`/api/claims/${claimId}`),
  getEvidence: (claimId) => request(`/api/claims/${claimId}/evidence`),
  getAnalysis: (claimId) => request(`/api/claims/${claimId}/analysis`),
  getTimeline: (claimId) => request(`/api/claims/${claimId}/timeline`),
  getPreservationLog: (claimId) => request(`/api/claims/${claimId}/preservation-log`),
  getHolds: (claimId) => request(`/api/claims/${claimId}/holds`),
  getDocuments: (claimId) => request(`/api/claims/${claimId}/documents`),
  uploadDocument: (claimId, { filename, text }) =>
    request(`/api/claims/${claimId}/documents`, {
      method: "POST",
      body: JSON.stringify({ filename, text }),
    }),
  uploadFile: (claimId, file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/api/claims/${claimId}/documents/upload`, { method: "POST", body: formData });
  },
  classifyDocument: (claimId, documentId) =>
    request(`/api/claims/${claimId}/documents/${documentId}/classify`, { method: "POST" }),
  analyzeImage: (claimId, documentId) =>
    request(`/api/claims/${claimId}/documents/${documentId}/analyze-image`, { method: "POST" }),
  analyzeDocument: (claimId, documentId) =>
    request(`/api/claims/${claimId}/documents/${documentId}/analyze`, { method: "POST" }),
  analyzeAllPending: (claimId) => request(`/api/claims/${claimId}/documents/analyze-all`, { method: "POST" }),
  deleteDocument: (claimId, documentId, { user, role, reason }) =>
    request(`/api/claims/${claimId}/documents/${documentId}`, {
      method: "DELETE",
      body: JSON.stringify({ user, role, reason }),
    }),
  documentFileUrl: (claimId, documentId) => `${BASE_URL}/api/claims/${claimId}/documents/${documentId}/file`,
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
