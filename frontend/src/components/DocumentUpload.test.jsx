import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DocumentUpload from "./DocumentUpload.jsx";
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
      uploadDocument: vi.fn(),
      classifyDocument: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DocumentUpload", () => {
  it("uploads a document and shows it PENDING, then classifies it", async () => {
    const user = userEvent.setup();
    api.uploadDocument.mockResolvedValue({
      id: 1,
      filename: "note.txt",
      classification: null,
      confidence: null,
      litigation_signal: null,
      litigation_confidence: null,
      classification_status: "PENDING",
      ai_provider: null,
    });
    api.classifyDocument.mockResolvedValue({
      document: {
        id: 1,
        filename: "note.txt",
        classification: "Repair Estimate",
        confidence: 0.9,
        litigation_signal: "none",
        litigation_confidence: 0.95,
        classification_status: "CLASSIFIED",
        ai_provider: "deterministic",
      },
      manual_review_required: false,
      litigation_hold_created: null,
    });

    const onMutated = vi.fn();
    render(<DocumentUpload claimId="CLM-10042" onMutated={onMutated} />);

    await user.type(screen.getByLabelText(/filename/i), "note.txt");
    await user.type(screen.getByLabelText(/document text/i), "repair estimate details");
    await user.click(screen.getByRole("button", { name: /upload document/i }));

    await waitFor(() => expect(screen.getByText("note.txt")).toBeInTheDocument());
    expect(screen.getByText("PENDING")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /classify document/i }));

    await waitFor(() => expect(screen.getByText("CLASSIFIED")).toBeInTheDocument());
    expect(screen.getByText(/Repair Estimate/)).toBeInTheDocument();
    expect(onMutated).toHaveBeenCalled();
  });

  it("shows MANUAL_REVIEW clearly for a low-confidence classification", async () => {
    const user = userEvent.setup();
    api.uploadDocument.mockResolvedValue({
      id: 2,
      filename: "vague.txt",
      classification: null,
      confidence: null,
      litigation_signal: null,
      litigation_confidence: null,
      classification_status: "PENDING",
      ai_provider: null,
    });
    api.classifyDocument.mockResolvedValue({
      document: {
        id: 2,
        filename: "vague.txt",
        classification: "Repair Estimate",
        confidence: 0.7,
        litigation_signal: "none",
        litigation_confidence: 0.95,
        classification_status: "MANUAL_REVIEW",
        ai_provider: "deterministic",
      },
      manual_review_required: true,
      litigation_hold_created: null,
    });

    render(<DocumentUpload claimId="CLM-10042" onMutated={vi.fn()} />);

    await user.type(screen.getByLabelText(/document text/i), "a rough estimate");
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /classify document/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /classify document/i }));

    await waitFor(() => expect(screen.getByText("MANUAL_REVIEW")).toBeInTheDocument());
  });

  it("rejects an empty upload without calling the API", async () => {
    const user = userEvent.setup();
    render(<DocumentUpload claimId="CLM-10042" onMutated={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /upload document/i }));

    expect(await screen.findByText(/paste or type the document text/i)).toBeInTheDocument();
    expect(api.uploadDocument).not.toHaveBeenCalled();
  });
});
