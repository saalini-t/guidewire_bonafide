import { useState } from "react";
import { api, ApiError } from "../api/client.js";
import StatusBadge from "./StatusBadge.jsx";

const STATUS_TONE = { PENDING: "neutral", CLASSIFIED: "success", MANUAL_REVIEW: "warning" };

// Note: the backend has no "list documents for a claim" endpoint (Day 2
// scope), so uploaded documents are tracked in this component's local
// state for the current session only — they will not reappear after a
// page reload, even though they remain persisted server-side.
export default function DocumentUpload({ claimId, onMutated }) {
  const [filename, setFilename] = useState("");
  const [text, setText] = useState("");
  const [documents, setDocuments] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);

  async function handleUpload(event) {
    event.preventDefault();
    setError(null);
    if (!text.trim()) {
      setError("Paste or type the document text before uploading.");
      return;
    }
    try {
      const document = await api.uploadDocument(claimId, {
        filename: filename.trim() || "pasted-document.txt",
        text,
      });
      setDocuments((prev) => [{ document, classifyResult: null }, ...prev]);
      setFilename("");
      setText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    }
  }

  async function handleClassify(documentId) {
    setError(null);
    setBusyId(documentId);
    try {
      const result = await api.classifyDocument(claimId, documentId);
      setDocuments((prev) =>
        prev.map((entry) =>
          entry.document.id === documentId ? { document: result.document, classifyResult: result } : entry
        )
      );
      await onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Classification failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Document Upload</h2>
      <form className="upload-form" onSubmit={handleUpload}>
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
        {error && <p className="form-error">{error}</p>}
        <button type="submit" className="button button--primary">
          Upload Document
        </button>
      </form>

      {documents.length > 0 && (
        <ul className="document-list">
          {documents.map(({ document, classifyResult }) => (
            <li key={document.id} className="document-list__item">
              <div className="document-list__row">
                <span className="document-list__filename">{document.filename}</span>
                <StatusBadge tone={STATUS_TONE[document.classification_status] ?? "neutral"}>
                  {document.classification_status}
                </StatusBadge>
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

              {classifyResult?.litigation_hold_created && (
                <div className="document-list__meta document-list__meta--alert">
                  Preservation hold proposed from this document — see below.
                </div>
              )}

              {document.classification_status === "PENDING" && (
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={busyId === document.id}
                  onClick={() => handleClassify(document.id)}
                >
                  {busyId === document.id ? "Classifying…" : "Classify Document"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
