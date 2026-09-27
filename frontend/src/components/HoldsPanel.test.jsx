import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HoldsPanel from "./HoldsPanel.jsx";
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
      confirmHold: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

const proposedHold = {
  id: 43,
  status: "PROPOSED",
  trigger_reason: "Litigation signal detected: attorney_representation",
  confidence: 0.97,
};

describe("HoldsPanel", () => {
  it("shows an empty state with no holds", () => {
    render(<HoldsPanel claimId="CLM-10042" holds={[]} onMutated={vi.fn()} />);

    expect(screen.getByText(/no preservation hold has been proposed/i)).toBeInTheDocument();
  });

  it("displays a PROPOSED hold with reason, confidence, and a Confirm Hold action", () => {
    render(<HoldsPanel claimId="CLM-10042" holds={[proposedHold]} onMutated={vi.fn()} />);

    expect(screen.getByText("PRESERVATION HOLD PROPOSED")).toBeInTheDocument();
    expect(screen.getByText(/attorney_representation/)).toBeInTheDocument();
    expect(screen.getByText("97% confidence")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm hold/i })).toBeInTheDocument();
  });

  it("does not show ACTIVE until the confirmation call succeeds, then reflects it via onMutated", async () => {
    const user = userEvent.setup();
    api.confirmHold.mockResolvedValue({ ...proposedHold, status: "ACTIVE" });
    const onMutated = vi.fn();

    render(<HoldsPanel claimId="CLM-10042" holds={[proposedHold]} onMutated={onMutated} />);

    expect(screen.queryByText("ACTIVE HOLD")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm hold/i }));

    await waitFor(() => expect(api.confirmHold).toHaveBeenCalledWith("CLM-10042", 43, "adjuster.demo"));
    expect(onMutated).toHaveBeenCalled();
  });

  it("shows an error message when confirmation fails", async () => {
    const user = userEvent.setup();
    api.confirmHold.mockRejectedValue(new Error("Hold 43 cannot be confirmed from status ACTIVE"));

    render(<HoldsPanel claimId="CLM-10042" holds={[proposedHold]} onMutated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /confirm hold/i }));

    expect(await screen.findByText(/could not confirm hold/i)).toBeInTheDocument();
  });
});
