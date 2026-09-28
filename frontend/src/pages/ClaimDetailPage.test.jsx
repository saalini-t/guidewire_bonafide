import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClaimDetailPage from "./ClaimDetailPage.jsx";
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
      getClaim: vi.fn(),
      getEvidence: vi.fn(),
      getAnalysis: vi.fn(),
      getHolds: vi.fn(),
      getDocuments: vi.fn(),
      getPreservationLog: vi.fn(),
      uploadFile: vi.fn(),
      uploadDocument: vi.fn(),
      classifyDocument: vi.fn(),
      analyzeImage: vi.fn(),
      documentFileUrl: (claimId, documentId) => `http://test/${claimId}/${documentId}/file`,
    },
  };
});

function renderAt(claimId) {
  return render(
    <MemoryRouter initialEntries={[`/claims/${claimId}`]}>
      <Routes>
        <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ClaimDetailPage", () => {
  it("renders the claim header and the backend's HIGH risk analysis for CLM-10042", async () => {
    api.getClaim.mockResolvedValue({
      claim_id: "CLM-10042",
      claim_type: "PersonalAuto",
      status: "OPEN",
      repair_status: "PENDING",
      upcoming_business_event: "RepairAuthorization",
      claimant: "Jordan Reyes",
    });
    api.getEvidence.mockResolvedValue([
      { id: 1, evidence_type: "Vehicle Photographs", required: true, satisfied: false, expiry_trigger: "RepairAuthorization" },
    ]);
    api.getAnalysis.mockResolvedValue({
      risk_level: "HIGH",
      upcoming_event: "RepairAuthorization",
      at_risk_evidence: ["Vehicle Photographs", "Repair Appraisal", "Recorded Statement"],
      missing_evidence: ["Vehicle Photographs", "Repair Appraisal", "Recorded Statement"],
      explanation: "RepairAuthorization is pending.",
      recommendation: "Preserve the evidence.",
    });
    api.getHolds.mockResolvedValue([]);
    api.getDocuments.mockResolvedValue([]);
    api.getPreservationLog.mockResolvedValue([]);

    renderAt("CLM-10042");

    expect(await screen.findByText("CLM-10042")).toBeInTheDocument();
    expect(screen.getByText("HIGH PRESERVATION RISK")).toBeInTheDocument();
    expect(screen.getByText("Jordan Reyes")).toBeInTheDocument();
  });

  it("shows a not-found message for a missing claim", async () => {
    const { ApiError } = await import("../api/client.js");
    api.getClaim.mockRejectedValue(new ApiError("not found", 404, null));
    api.getEvidence.mockResolvedValue([]);
    api.getAnalysis.mockResolvedValue({});
    api.getHolds.mockResolvedValue([]);
    api.getDocuments.mockResolvedValue([]);
    api.getPreservationLog.mockResolvedValue([]);

    renderAt("CLM-NOPE");

    expect(await screen.findByText(/was not found/i)).toBeInTheDocument();
  });

  it("offers a Retry action on a non-404 failure that recovers without a page reload", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("../api/client.js");
    api.getClaim.mockRejectedValueOnce(new ApiError("Cannot reach the Bona Fide backend. Is it running?", 0, null));
    api.getEvidence.mockResolvedValue([]);
    api.getAnalysis.mockResolvedValue({
      risk_level: "LOW",
      upcoming_event: null,
      at_risk_evidence: [],
      missing_evidence: [],
      explanation: "No upcoming business event is scheduled.",
      recommendation: "No preservation action required at this time.",
    });
    api.getHolds.mockResolvedValue([]);
    api.getDocuments.mockResolvedValue([]);
    api.getPreservationLog.mockResolvedValue([]);

    renderAt("CLM-10042");

    expect(await screen.findByText(/cannot reach the bona fide backend/i)).toBeInTheDocument();

    api.getClaim.mockResolvedValueOnce({
      claim_id: "CLM-10042",
      claim_type: "PersonalAuto",
      status: "OPEN",
      repair_status: "PENDING",
      upcoming_business_event: null,
      claimant: "Jordan Reyes",
    });

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("Jordan Reyes")).toBeInTheDocument();
  });

  it("shows documents fetched from the backend, surviving a page refresh", async () => {
    // Regression coverage for the known limitation this phase fixes:
    // documents used to live only in local component state and vanished
    // on reload. They now come from GET .../documents on every refresh().
    api.getClaim.mockResolvedValue({
      claim_id: "CLM-10042",
      claim_type: "PersonalAuto",
      status: "OPEN",
      repair_status: "PENDING",
      upcoming_business_event: "RepairAuthorization",
      claimant: "Jordan Reyes",
    });
    api.getEvidence.mockResolvedValue([]);
    api.getAnalysis.mockResolvedValue({
      risk_level: "LOW",
      upcoming_event: null,
      at_risk_evidence: [],
      missing_evidence: [],
      explanation: "",
      recommendation: "",
    });
    api.getHolds.mockResolvedValue([]);
    api.getDocuments.mockResolvedValue([
      {
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
      },
    ]);
    api.getPreservationLog.mockResolvedValue([]);

    renderAt("CLM-10042");

    expect(await screen.findByText("damage.jpg")).toBeInTheDocument();
  });
});
