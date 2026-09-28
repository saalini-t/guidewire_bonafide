import { useState } from "react";
import { api, ApiError } from "../api/client.js";
import StatusBadge from "./StatusBadge.jsx";

const STATUS_TONE = {
  PENDING: "neutral",
  PROCESSING: "neutral",
  CLASSIFIED: "success",
  MANUAL_REVIEW: "warning",
  FAILED: "warning",
};
const IMAGE_STATUS_TONE = {
  NOT_APPLICABLE: "neutral",
  PENDING: "neutral",
  PROCESSING: "neutral",
  ANALYZED: "success",
  MANUAL_REVIEW: "warning",
  FAILED: "warning",
};
const ACCEPTED_EXTENSIONS = ".jpg,.jpeg,.png,.webp,.pdf,.txt";
const IMAGE_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const TEXT_ANALYSIS_MIME_TYPES = new Set(["application/pdf", "text/plain"]);
// Statuses from which (re-)analyzing this document's real file makes sense.
const ANALYZABLE_IMAGE_STATUSES = new Set(["PENDING", "MANUAL_REVIEW", "FAILED"]);
const ANALYZABLE_TEXT_STATUSES = new Set(["PENDING", "MANUAL_REVIEW", "FAILED"]);

function formatFileSize(bytes) {
  if (bytes == null) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function isRealFile(document) {
  return document.mime_type != null;
}

function isAnalyzable(document) {
  if (IMAGE_MIME_TYPES.has(document.mime_type)) {
    return ANALYZABLE_IMAGE_STATUSES.has(document.image_analysis_status);
  }
  if (TEXT_ANALYSIS_MIME_TYPES.has(document.mime_type)) {
    return document.text != null && ANALYZABLE_TEXT_STATUSES.has(document.classification_status);
  }
  return false;
}

/**
 * Documents are fetched by the parent (GET /api/claims/{id}/documents) and
 * passed in as `documents` — this component holds no document list state
 * of its own, so uploaded files are still visible after a page refresh.
 */
export default function DocumentsPanel({ claimId, documents, onMutated }) {
  const [uploadError, setUploadError] = useState(null);
  const [uploading, setUploading] = useState(false);

  const [pasteOpen, setPasteOpen] = useState(false);
  const [filename, setFilename] = useState("");
  const [text, setText] = useState("");
  const [pasteError, setPasteError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deleteReason, setDeleteReason] = useState("");

  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState(null);

  const pendingCount = documents.filter(isAnalyzable).length;

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-selecting the same file later
    if (!file) return;

    setUploadError(null);
    setUploading(true);
    try {
      await api.uploadFile(claimId, file);
      await onMutated();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function handlePasteSubmit(event) {
    event.preventDefault();
    setPasteError(null);
    if (!text.trim()) {
      setPasteError("Paste or type the document text before uploading.");
      return;
    }
    try {
      await api.uploadDocument(claimId, { filename: filename.trim() || "pasted-document.txt", text });
      setFilename("");
      setText("");
      await onMutated();
    } catch (err) {
      setPasteError(err instanceof ApiError ? err.message : "Upload failed.");
    }
  }

  async function handleClassify(documentId) {
    setBusyId(documentId);
    setActionError(null);
    try {
      await api.classifyDocument(claimId, documentId);
      await onMutated();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Classification failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleAnalyze(document) {
    setBusyId(document.id);
    setActionError(null);
    try {
      if (IMAGE_MIME_TYPES.has(document.mime_type)) {
        await api.analyzeImage(claimId, document.id);
      } else {
        await api.analyzeDocument(claimId, document.id);
      }
      await onMutated();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Analysis failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleAnalyzeAll() {
    setBulkBusy(true);
    setBulkError(null);
    setBulkResult(null);
    try {
      const results = await api.analyzeAllPending(claimId);
      setBulkResult(results);
      await onMutated();
    } catch (err) {
      setBulkError(err instanceof ApiError ? err.message : "Bulk analysis failed.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleDelete(documentId) {
    setActionError(null);
    try {
      // MVP does not implement authentication; "adjuster.demo" stands in
      // for the deleting user (see docs/LIMITATIONS.md), same convention
      // as HoldsPanel's confirm action.
      await api.deleteDocument(claimId, documentId, {
        user: "adjuster.demo",
        role: "Adjuster",
        reason: deleteReason.trim() || "Removed by adjuster",
      });
      setConfirmDeleteId(null);
      setDeleteReason("");
      await onMutated();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Deletion failed.");
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Documents</h2>

      <label className="field">
        <span>Upload Evidence ({ACCEPTED_EXTENSIONS})</span>
        <input type="file" accept={ACCEPTED_EXTENSIONS} onChange={handleFileChange} disabled={uploading} />
      </label>
      {uploading && <p className="panel__empty">Uploading…</p>}
      {uploadError && <p className="form-error">{uploadError}</p>}

      {documents.length > 0 && (
        <div className="document-list__row" style={{ margin: "12px 0" }}>
          <span className="document-list__meta">
            {pendingCount > 0 ? `${pendingCount} document(s) awaiting analysis` : "All documents analyzed"}
          </span>
          {pendingCount > 0 && (
            <button type="button" className="button button--secondary" disabled={bulkBusy} onClick={handleAnalyzeAll}>
              {bulkBusy ? "Analyzing all…" : "Analyze All Pending"}
            </button>
          )}
        </div>
      )}
      {bulkError && <p className="form-error">{bulkError}</p>}
      {bulkResult && (
        <ul className="panel__empty">
          {bulkResult.map((item) => (
            <li key={item.document_id}>
              Document {item.document_id}: {item.outcome}
              {item.reason ? ` (${item.reason})` : ""}
            </li>
          ))}
        </ul>
      )}
      {actionError && <p className="form-error">{actionError}</p>}

      {documents.length === 0 ? (
        <p className="panel__empty">No documents uploaded yet.</p>
      ) : (
        <ul className="document-list">
          {documents.map((document) => (
            <li key={document.id} className="document-list__item">
              <div className="document-list__row">
                <span className="document-list__filename">{document.filename}</span>
                <StatusBadge tone={STATUS_TONE[document.classification_status] ?? "neutral"}>
                  {document.classification_status}
                </StatusBadge>
              </div>
              <div className="document-list__meta">
                {document.mime_type ?? "text/plain (pasted)"}
                {formatFileSize(document.file_size) ? ` · ${formatFileSize(document.file_size)}` : ""}
                {" · uploaded "}
                {formatTimestamp(document.uploaded_at)}
              </div>

              {IMAGE_MIME_TYPES.has(document.mime_type) && (
                <img
                  src={api.documentFileUrl(claimId, document.id)}
                  alt={document.filename}
                  style={{ maxWidth: "220px", maxHeight: "220px", display: "block", margin: "8px 0", borderRadius: "6px" }}
                />
              )}

              <div className="document-list__row" style={{ gap: "8px" }}>
                {isRealFile(document) && (
                  <a href={api.documentFileUrl(claimId, document.id)} target="_blank" rel="noreferrer" className="button button--secondary">
                    View / Download
                  </a>
                )}
              </div>

              {document.classification && (
                <div className="document-list__meta">
                  Classified as <strong>{document.classification}</strong> (
                  {Math.round(document.confidence * 100)}% confidence, via {document.ai_provider ?? "unknown"})
                </div>
              )}

              {document.litigation_signal && document.litigation_signal !== "none" && (
                <div className="document-list__meta document-list__meta--alert">
                  Litigation signal: <strong>{document.litigation_signal}</strong> (
                  {Math.round(document.litigation_confidence * 100)}% confidence)
                </div>
              )}

              {document.findings && (document.findings.estimated_repair_cost || document.findings.incident_date) && (
                <div className="document-list__meta">
                  {document.findings.estimated_repair_cost && (
                    <div>Estimated repair cost (extracted): {document.findings.estimated_repair_cost}</div>
                  )}
                  {document.findings.incident_date && <div>Incident date (extracted): {document.findings.incident_date}</div>}
                </div>
              )}

              {document.classification_status === "PENDING" && document.mime_type == null && (
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={busyId === document.id}
                  onClick={() => handleClassify(document.id)}
                >
                  {busyId === document.id ? "Classifying…" : "Classify Document"}
                </button>
              )}

              {TEXT_ANALYSIS_MIME_TYPES.has(document.mime_type) && document.text != null && (
                <div className="document-list__row" style={{ marginTop: "8px", gap: "8px" }}>
                  {isAnalyzable(document) && (
                    <button
                      type="button"
                      className="button button--secondary"
                      disabled={busyId === document.id}
                      onClick={() => handleAnalyze(document)}
                    >
                      {busyId === document.id
                        ? "Analyzing…"
                        : document.classification_status === "PENDING"
                          ? "Analyze Document"
                          : "Retry Analysis"}
                    </button>
                  )}
                  {document.classification_status === "CLASSIFIED" && (
                    <button
                      type="button"
                      className="button button--secondary"
                      disabled={busyId === document.id}
                      onClick={() => handleAnalyze(document)}
                    >
                      {busyId === document.id ? "Analyzing…" : "Re-analyze"}
                    </button>
                  )}
                </div>
              )}
              {TEXT_ANALYSIS_MIME_TYPES.has(document.mime_type) && document.text == null && (
                <div className="panel__empty">
                  {document.classification_status === "FAILED"
                    ? "No extractable text found (scanned/image-only PDF, and OCR was unavailable or found nothing) — manual review required."
                    : "This document has no extracted text yet — it was likely uploaded before text extraction was enabled. Delete and re-upload it to analyze it."}
                </div>
              )}

              {IMAGE_MIME_TYPES.has(document.mime_type) && (
                <div className="document-list__row" style={{ marginTop: "8px" }}>
                  <StatusBadge tone={IMAGE_STATUS_TONE[document.image_analysis_status] ?? "neutral"}>
                    Image analysis: {document.image_analysis_status}
                  </StatusBadge>
                </div>
              )}

              {IMAGE_MIME_TYPES.has(document.mime_type) && isAnalyzable(document) && (
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={busyId === document.id}
                  onClick={() => handleAnalyze(document)}
                >
                  {busyId === document.id
                    ? "Analyzing…"
                    : document.image_analysis_status === "PENDING"
                      ? "Analyze Image"
                      : "Retry Analysis"}
                </button>
              )}

              {document.image_analysis && (
                <div className="document-list__meta">
                  <div>
                    Vehicle present: <strong>{document.image_analysis.vehicle_present ? "Yes" : "No"}</strong> ·
                    Damage observed: <strong>{document.image_analysis.damage_observed ? "Yes" : "No"}</strong>
                  </div>
                  {document.image_analysis.damage_regions.length > 0 && (
                    <div>Damage regions: {document.image_analysis.damage_regions.join(", ")}</div>
                  )}
                  <div>
                    Image quality: {document.image_analysis.image_quality} · Relevance:{" "}
                    {document.image_analysis.relevance} · {Math.round(document.image_analysis.confidence * 100)}%
                    confidence (via {document.image_analysis.provider}
                    {document.image_analysis.model ? `/${document.image_analysis.model}` : ""})
                  </div>
                  <div style={{ fontStyle: "italic" }}>{document.image_analysis.explanation}</div>
                </div>
              )}
              {document.image_analysis_status === "MANUAL_REVIEW" && !document.image_analysis && (
                <div className="panel__empty">
                  Vision analysis unavailable or inconclusive — manual review required.
                </div>
              )}

              <div style={{ marginTop: "8px" }}>
                {confirmDeleteId === document.id ? (
                  <div className="document-list__row" style={{ gap: "8px" }}>
                    <input
                      placeholder="Reason for deletion"
                      value={deleteReason}
                      onChange={(event) => setDeleteReason(event.target.value)}
                    />
                    <button type="button" className="button button--primary" onClick={() => handleDelete(document.id)}>
                      Confirm Delete
                    </button>
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => {
                        setConfirmDeleteId(null);
                        setDeleteReason("");
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button type="button" className="button button--secondary" onClick={() => setConfirmDeleteId(document.id)}>
                    Delete
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div style={{ marginTop: "16px" }}>
        {!pasteOpen ? (
          <button type="button" className="button button--secondary" onClick={() => setPasteOpen(true)}>
            Paste text (for AI classification testing)
          </button>
        ) : (
          <form onSubmit={handlePasteSubmit}>
            <label className="field">
              <span>Filename</span>
              <input
                value={filename}
                onChange={(event) => setFilename(event.target.value)}
                placeholder="pasted-document.txt"
              />
            </label>
            <label className="field">
              <span>Document text</span>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={4}
                placeholder="Paste the document text here..."
              />
            </label>
            {pasteError && <p className="form-error">{pasteError}</p>}
            <div className="override-form__actions">
              <button type="submit" className="button button--primary">
                Upload Pasted Text
              </button>
              <button type="button" className="button button--secondary" onClick={() => setPasteOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
