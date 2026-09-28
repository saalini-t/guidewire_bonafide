import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewClaimForm from "./NewClaimForm.jsx";
import { api } from "../api/client.js";

const navigateSpy = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => navigateSpy };
});

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
      createClaim: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

function renderForm(onCreated = vi.fn()) {
  return render(
    <MemoryRouter>
      <NewClaimForm onCreated={onCreated} />
    </MemoryRouter>
  );
}

describe("NewClaimForm", () => {
  it("shows a New Claim button that opens the form", async () => {
    const user = userEvent.setup();
    renderForm();

    expect(screen.getByRole("button", { name: /\+ new claim/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /\+ new claim/i }));

    expect(screen.getByRole("heading", { name: "Create Claim" })).toBeInTheDocument();
    expect(screen.getByLabelText(/claimant name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/policy number/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/claim type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/loss date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/repair status/i)).toBeInTheDocument();
  });

  it("creates a claim and navigates to its detail page", async () => {
    const user = userEvent.setup();
    api.createClaim.mockResolvedValue({ claim_id: "CLM-54321" });
    const onCreated = vi.fn();
    renderForm(onCreated);

    await user.click(screen.getByRole("button", { name: /\+ new claim/i }));
    await user.type(screen.getByLabelText(/claimant name/i), "Alex Rivera");
    await user.type(screen.getByLabelText(/policy number/i), "POL-999");
    await user.type(screen.getByLabelText(/loss date/i), "2026-09-01");
    await user.type(screen.getByLabelText(/description/i), "Rear-end collision at intersection.");
    await user.click(screen.getByRole("button", { name: /^create claim$/i }));

    await waitFor(() =>
      expect(api.createClaim).toHaveBeenCalledWith({
        claimant: "Alex Rivera",
        policy_id: "POL-999",
        claim_type: "PersonalAuto",
        loss_date: "2026-09-01",
        description: "Rear-end collision at intersection.",
        repair_status: "PENDING",
      })
    );
    expect(onCreated).toHaveBeenCalled();
    expect(navigateSpy).toHaveBeenCalledWith("/claims/CLM-54321");
  });

  it("shows a validation error from the backend without navigating", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("../api/client.js");
    api.createClaim.mockRejectedValue(new ApiError("Unsupported claim type", 422, null));
    renderForm();

    await user.click(screen.getByRole("button", { name: /\+ new claim/i }));
    await user.type(screen.getByLabelText(/claimant name/i), "Alex Rivera");
    await user.type(screen.getByLabelText(/policy number/i), "POL-999");
    await user.type(screen.getByLabelText(/loss date/i), "2026-09-01");
    await user.type(screen.getByLabelText(/description/i), "Rear-end collision.");
    await user.click(screen.getByRole("button", { name: /^create claim$/i }));

    expect(await screen.findByText(/unsupported claim type/i)).toBeInTheDocument();
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
