import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OverrideForm from "./OverrideForm.jsx";
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
      applyOverride: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("OverrideForm", () => {
  it("renders nothing when there is no upcoming business event", () => {
    const { container } = render(
      <OverrideForm claimId="CLM-20011" upcomingBusinessEvent={null} onMutated={vi.fn()} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("explains that this is identity capture, not real authentication", async () => {
    const user = userEvent.setup();
    render(<OverrideForm claimId="CLM-10042" upcomingBusinessEvent="RepairAuthorization" onMutated={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /override preservation rule/i }));

    expect(screen.getByText(/does not implement real authentication/i)).toBeInTheDocument();
  });

  it("shows the backend's validation error for a rejected justification", async () => {
    const user = userEvent.setup();
    api.applyOverride.mockRejectedValue(
      new ApiError("justification: justification must be at least 10 characters", 422, null)
    );

    render(<OverrideForm claimId="CLM-10042" upcomingBusinessEvent="RepairAuthorization" onMutated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /override preservation rule/i }));
    await user.type(screen.getByLabelText(/^user$/i), "supervisor.jane");
    await user.type(screen.getByLabelText(/^role$/i), "Supervisor");
    await user.type(screen.getByLabelText(/justification/i), "ok");
    await user.click(screen.getByRole("button", { name: /override repairauthorization/i }));

    expect(await screen.findByText(/must be at least 10 characters/i)).toBeInTheDocument();
  });

  it("keeps showing the success message after the parent clears upcomingBusinessEvent (regression)", async () => {
    // A successful override clears the claim's upcoming_business_event
    // server-side, and the parent re-fetches and passes that down — the
    // success confirmation must not vanish just because its own trigger
    // condition disappeared.
    const user = userEvent.setup();
    api.applyOverride.mockResolvedValue({
      claim_id: "CLM-10042",
      log: { event_type: "OVERRIDE_APPLIED", user: "supervisor.jane" },
    });

    const { rerender } = render(
      <OverrideForm claimId="CLM-10042" upcomingBusinessEvent="RepairAuthorization" onMutated={vi.fn()} />
    );
    await user.click(screen.getByRole("button", { name: /override preservation rule/i }));
    await user.type(screen.getByLabelText(/^user$/i), "supervisor.jane");
    await user.type(screen.getByLabelText(/^role$/i), "Supervisor");
    await user.type(
      screen.getByLabelText(/justification/i),
      "Repair shop deadline requires authorization despite the gap."
    );
    await user.click(screen.getByRole("button", { name: /override repairauthorization/i }));
    await waitFor(() => expect(screen.getByText(/override applied and logged/i)).toBeInTheDocument());

    rerender(<OverrideForm claimId="CLM-10042" upcomingBusinessEvent={null} onMutated={vi.fn()} />);

    expect(screen.getByText(/override applied and logged/i)).toBeInTheDocument();
  });

  it("shows success and calls onMutated when the override succeeds", async () => {
    const user = userEvent.setup();
    api.applyOverride.mockResolvedValue({
      claim_id: "CLM-10042",
      log: { event_type: "OVERRIDE_APPLIED", user: "supervisor.jane" },
    });
    const onMutated = vi.fn();

    render(<OverrideForm claimId="CLM-10042" upcomingBusinessEvent="RepairAuthorization" onMutated={onMutated} />);
    await user.click(screen.getByRole("button", { name: /override preservation rule/i }));
    await user.type(screen.getByLabelText(/^user$/i), "supervisor.jane");
    await user.type(screen.getByLabelText(/^role$/i), "Supervisor");
    await user.type(
      screen.getByLabelText(/justification/i),
      "Repair shop deadline requires authorization despite the gap."
    );
    await user.click(screen.getByRole("button", { name: /override repairauthorization/i }));

    await waitFor(() => expect(screen.getByText(/override applied and logged/i)).toBeInTheDocument());
    expect(onMutated).toHaveBeenCalled();
  });
});
