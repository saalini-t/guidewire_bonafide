import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DocumentsPanel from "./DocumentsPanel.jsx";
import { api } from "../api/client.js";

vi.mock("../api/client.js", () => {
  class ApiError extends Error {
    constructor(message, status, body) {
      super(message);
      this.status = status;
      this.body = body;
    }
  }
  return {
    ApiError,
    api: {
      uploadFile: vi.fn(),
      uploadDocument: vi.fn(),
      classifyDocument: vi.fn(),
      analyzeImage: vi.fn(),
      analyzeDocument: vi.fn(),
      analyzeAllPending: vi.fn(),
      deleteDocument: vi.fn(),
      documentFileUrl: (claimId, documentId) => `http://test/${claimId}/${documentId}/file`,
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

const realFileDocument = {
  id: 1,
  filename: "damage.jpg",
  mime_type: "image/jpeg",
  file_size: 20480,
  uploaded_at: "2026-09-27T12:00:00Z",
  classification: null,
  confidence: null,
  litigation_signal: null,
  litigation_confidence: null,
  classification_status: "PENDING",
  ai_provider: null,
  image_analysis_status: "PENDING",
  image_analysis: null,
};

const pdfDocument = {
  id: 3,
  filename: "police-report.pdf",
  mime_type: "application/pdf",
  file_size: 51200,
  uploaded_at: "2026-09-27T12:02:00Z",
  text: null,
  classification: null,
  confidence: null,
  litigation_signal: null,
  litigation_confidence: null,
  classification_status: "FAILED",
  ai_provider: null,
  image_analysis_status: "NOT_APPLICABLE",
  image_analysis: null,
  findings: null,
};

const pdfWithTextDocument = {
  ...pdfDocument,
  id: 5,
  text: "Repair estimate totaling $1,200.00 for the front bumper.",
  classification_status: "PENDING",
};

const classifiedPdfDocument = {
  ...pdfWithTextDocument,
  id: 6,
  classification: "Repair Estimate",
  confidence: 0.95,
  ai_provider: "deterministic",
  classification_status: "CLASSIFIED",
  findings: { estimated_repair_cost: "$1,200.00", incident_date: null },
};

const analyzedImageDocument = {
  ...realFileDocument,
  id: 4,
  image_analysis_status: "ANALYZED",
  image_analysis: {
    id: 1,
    document_id: 4,
    evidence_type: "Vehicle Photographs",
    vehicle_present: true,
    damage_observed: true,
    damage_regions: ["front_bumper", "hood"],
    image_quality: "clear",
    relevance: "relevant",
    confidence: 0.92,
    explanation: "A vehicle with visible front-end damage is shown.",
    provider: "ollama",
    model: "llava",
    analyzed_at: "2026-09-27T12:10:00Z",
  },
};

const pastedTextDocument = {
  id: 2,
  filename: "note.txt",
  mime_type: null,
  file_size: null,
  uploaded_at: "2026-09-27T12:05:00Z",
  classification: null,
  confidence: null,
  litigation_signal: null,
  litigation_confidence: null,
  classification_status: "PENDING",
  ai_provider: null,
};

describe("DocumentsPanel", () => {
  it("shows an empty state with no documents", () => {
    render(<DocumentsPanel claimId="CLM-10042" documents={[]} onMutated={vi.fn()} />);

    expect(screen.getByText(/no documents uploaded yet/i)).toBeInTheDocument();
  });

  it("has a real file picker restricted to the supported extensions", () => {
    render(<DocumentsPanel claimId="CLM-10042" documents={[]} onMutated={vi.fn()} />);

    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    expect(input.accept).toContain(".jpg");
    expect(input.accept).toContain(".pdf");
  });

  it("uploads a selected file via api.uploadFile and refreshes", async () => {
    const user = userEvent.setup();
    api.uploadFile.mockResolvedValue(realFileDocument);
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[]} onMutated={onMutated} />);

    const file = new File(["fake-image-bytes"], "damage.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]');
    await user.upload(input, file);

    await waitFor(() => expect(api.uploadFile).toHaveBeenCalledWith("CLM-10042", file));
    expect(onMutated).toHaveBeenCalled();
  });

  it("displays a real uploaded image's metadata, thumbnail, and an Analyze Image action instead of Classify", () => {
    render(<DocumentsPanel claimId="CLM-10042" documents={[realFileDocument]} onMutated={vi.fn()} />);

    expect(screen.getByText("damage.jpg")).toBeInTheDocument();
    expect(screen.getByText(/image\/jpeg/)).toBeInTheDocument();
    expect(screen.getByText(/20\.0 KB/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /classify document/i })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "damage.jpg" })).toHaveAttribute(
      "src",
      "http://test/CLM-10042/1/file"
    );
    expect(screen.getByText(/image analysis: PENDING/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze image/i })).toBeInTheDocument();
  });

  it("displays a PDF with no extractable text and no analyze action", () => {
    render(<DocumentsPanel claimId="CLM-10042" documents={[pdfDocument]} onMutated={vi.fn()} />);

    expect(screen.getByText("police-report.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /classify document/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /analyze document/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no extractable text found/i)).toBeInTheDocument();
  });

  it("shows a re-upload message for a legacy PDF stuck PENDING with no extracted text", () => {
    // Regression: a document uploaded before text extraction existed (or
    // any other state with mime_type set but text never populated) must
    // never render silently blank — see the live bug this covers.
    const legacyStuckPdf = { ...pdfDocument, classification_status: "PENDING" };
    render(<DocumentsPanel claimId="CLM-10042" documents={[legacyStuckPdf]} onMutated={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /analyze document/i })).not.toBeInTheDocument();
    expect(screen.getByText(/delete and re-upload it to analyze it/i)).toBeInTheDocument();
  });

  it("offers Analyze Document for a real PDF/TXT file with extracted text and calls the general analyze API", async () => {
    const user = userEvent.setup();
    api.analyzeDocument.mockResolvedValue(classifiedPdfDocument);
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[pdfWithTextDocument]} onMutated={onMutated} />);
    await user.click(screen.getByRole("button", { name: /analyze document/i }));

    await waitFor(() => expect(api.analyzeDocument).toHaveBeenCalledWith("CLM-10042", pdfWithTextDocument.id));
    expect(onMutated).toHaveBeenCalled();
  });

  it("shows extracted findings for a classified PDF/TXT document", () => {
    render(<DocumentsPanel claimId="CLM-10042" documents={[classifiedPdfDocument]} onMutated={vi.fn()} />);

    expect(screen.getByText(/estimated repair cost \(extracted\): \$1,200\.00/i)).toBeInTheDocument();
  });

  it("shows an Analyze All Pending button when documents are eligible and reports per-document results", async () => {
    const user = userEvent.setup();
    api.analyzeAllPending.mockResolvedValue([
      { document_id: realFileDocument.id, outcome: "analyzed", reason: null },
      { document_id: pdfWithTextDocument.id, outcome: "failed", reason: "ai unavailable" },
    ]);
    const onMutated = vi.fn();

    render(
      <DocumentsPanel claimId="CLM-10042" documents={[realFileDocument, pdfWithTextDocument]} onMutated={onMutated} />
    );
    await user.click(screen.getByRole("button", { name: /analyze all pending/i }));

    await waitFor(() => expect(api.analyzeAllPending).toHaveBeenCalledWith("CLM-10042"));
    expect(onMutated).toHaveBeenCalled();
    expect(screen.getByText(/document 1: analyzed/i)).toBeInTheDocument();
    expect(screen.getByText(/document 5: failed \(ai unavailable\)/i)).toBeInTheDocument();
  });

  it("deletes a document after confirmation", async () => {
    const user = userEvent.setup();
    api.deleteDocument.mockResolvedValue(undefined);
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[classifiedPdfDocument]} onMutated={onMutated} />);
    await user.click(screen.getAllByRole("button", { name: /^delete$/i })[0]);
    await user.type(screen.getByPlaceholderText(/reason for deletion/i), "duplicate upload");
    await user.click(screen.getByRole("button", { name: /confirm delete/i }));

    await waitFor(() =>
      expect(api.deleteDocument).toHaveBeenCalledWith("CLM-10042", classifiedPdfDocument.id, {
        user: "adjuster.demo",
        role: "Adjuster",
        reason: "duplicate upload",
      })
    );
    expect(onMutated).toHaveBeenCalled();
  });

  it("analyzes an image via the API and refreshes", async () => {
    const user = userEvent.setup();
    api.analyzeImage.mockResolvedValue(analyzedImageDocument);
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[realFileDocument]} onMutated={onMutated} />);
    await user.click(screen.getByRole("button", { name: /analyze image/i }));

    await waitFor(() => expect(api.analyzeImage).toHaveBeenCalledWith("CLM-10042", 1));
    expect(onMutated).toHaveBeenCalled();
  });

  it("shows structured vision findings for an analyzed image, never a Classify or Analyze action", () => {
    render(<DocumentsPanel claimId="CLM-10042" documents={[analyzedImageDocument]} onMutated={vi.fn()} />);

    expect(screen.getByText(/image analysis: ANALYZED/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /analyze image/i })).not.toBeInTheDocument();
    expect(screen.getByText(/vehicle present:/i)).toBeInTheDocument();
    expect(screen.getByText(/damage observed:/i)).toBeInTheDocument();
    expect(screen.getByText(/front_bumper, hood/)).toBeInTheDocument();
    expect(screen.getByText(/clear/)).toBeInTheDocument();
    expect(screen.getByText(/relevant/)).toBeInTheDocument();
    expect(screen.getByText(/92% confidence/)).toBeInTheDocument();
    expect(screen.getByText(/ollama\/llava/)).toBeInTheDocument();
    expect(screen.getByText(/A vehicle with visible front-end damage is shown\./)).toBeInTheDocument();
  });

  it("shows a manual-review message and a Retry Analysis action when vision analysis was unavailable/inconclusive", async () => {
    const user = userEvent.setup();
    const manualReviewDocument = { ...realFileDocument, image_analysis_status: "MANUAL_REVIEW" };
    api.analyzeImage.mockResolvedValue(analyzedImageDocument);
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[manualReviewDocument]} onMutated={onMutated} />);

    expect(screen.getByText(/vision analysis unavailable or inconclusive/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^analyze image$/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /retry analysis/i }));

    await waitFor(() => expect(api.analyzeImage).toHaveBeenCalledWith("CLM-10042", manualReviewDocument.id));
    expect(onMutated).toHaveBeenCalled();
  });

  it("offers Classify for a pasted-text document and calls the API", async () => {
    const user = userEvent.setup();
    api.classifyDocument.mockResolvedValue({
      document: { ...pastedTextDocument, classification_status: "CLASSIFIED" },
      manual_review_required: false,
      litigation_hold_created: null,
    });
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[pastedTextDocument]} onMutated={onMutated} />);

    await user.click(screen.getByRole("button", { name: /classify document/i }));

    await waitFor(() => expect(api.classifyDocument).toHaveBeenCalledWith("CLM-10042", 2));
    expect(onMutated).toHaveBeenCalled();
  });

  it("still supports pasting text for AI classification testing", async () => {
    const user = userEvent.setup();
    api.uploadDocument.mockResolvedValue(pastedTextDocument);
    const onMutated = vi.fn();

    render(<DocumentsPanel claimId="CLM-10042" documents={[]} onMutated={onMutated} />);

    await user.click(screen.getByRole("button", { name: /paste text/i }));
    await user.type(screen.getByPlaceholderText("pasted-document.txt"), "note.txt");
    await user.type(screen.getByPlaceholderText(/paste the document text here/i), "some text");
    await user.click(screen.getByRole("button", { name: /upload pasted text/i }));

    await waitFor(() =>
      expect(api.uploadDocument).toHaveBeenCalledWith("CLM-10042", { filename: "note.txt", text: "some text" })
    );
    expect(onMutated).toHaveBeenCalled();
  });
});
