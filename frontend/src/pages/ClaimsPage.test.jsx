import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClaimsPage from "./ClaimsPage.jsx";
import { api, ApiError } from "../api/client.js";

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
      listClaims: vi.fn(),
      getAnalysis: vi.fn(),
      createClaim: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ClaimsPage", () => {
  it("renders claims from the backend with their preservation risk", async () => {
    api.listClaims.mockResolvedValue([
      {
        claim_id: "CLM-10042",
        claim_type: "PersonalAuto",
        status: "OPEN",
        repair_status: "PENDING",
        upcoming_business_event: "RepairAuthorization",
      },
    ]);
    api.getAnalysis.mockResolvedValue({ risk_level: "HIGH" });

    render(
      <MemoryRouter>
        <ClaimsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("CLM-10042")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("HIGH")).toBeInTheDocument());
  });

  it("offers a Retry action on failure that recovers without a page reload", async () => {
    // Regression test: a transient failure (backend not up yet, a
    // momentary CORS/network blip) used to leave the user on a dead-end
    // error with no way to recover except manually reloading the browser
    // tab, which looked identical to "the app is broken".
    const user = userEvent.setup();
    api.listClaims.mockRejectedValueOnce(new ApiError("Cannot reach the Bona Fide backend. Is it running?", 0, null));

    render(
      <MemoryRouter>
        <ClaimsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/cannot reach the bona fide backend/i)).toBeInTheDocument();

    api.listClaims.mockResolvedValueOnce([
      {
        claim_id: "CLM-10042",
        claim_type: "PersonalAuto",
        status: "OPEN",
        repair_status: "PENDING",
        upcoming_business_event: "RepairAuthorization",
      },
    ]);
    api.getAnalysis.mockResolvedValue({ risk_level: "HIGH" });

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("CLM-10042")).toBeInTheDocument();
  });

  it("shows a newly created claim in the list after using + New Claim", async () => {
    const user = userEvent.setup();
    api.listClaims.mockResolvedValueOnce([]);

    render(
      <MemoryRouter>
        <ClaimsPage />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: /\+ new claim/i })).toBeInTheDocument();

    api.createClaim.mockResolvedValue({ claim_id: "CLM-54321" });
    api.listClaims.mockResolvedValueOnce([
      {
        claim_id: "CLM-54321",
        claim_type: "PersonalAuto",
        status: "OPEN",
        repair_status: "PENDING",
        upcoming_business_event: "RepairAuthorization",
      },
    ]);
    api.getAnalysis.mockResolvedValue({ risk_level: "HIGH" });

    await user.click(screen.getByRole("button", { name: /\+ new claim/i }));
    await user.type(screen.getByLabelText(/claimant name/i), "Alex Rivera");
    await user.type(screen.getByLabelText(/policy number/i), "POL-999");
    await user.type(screen.getByLabelText(/loss date/i), "2026-09-01");
    await user.type(screen.getByLabelText(/description/i), "Rear-end collision.");
    await user.click(screen.getByRole("button", { name: /^create claim$/i }));

    // The list is reloaded (onCreated) before navigating to the new
    // claim's detail page — api.listClaims must reflect the new claim.
    await waitFor(() => expect(api.listClaims).toHaveBeenCalledTimes(2));
  });
});
