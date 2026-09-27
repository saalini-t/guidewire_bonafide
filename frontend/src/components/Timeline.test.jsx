import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Timeline from "./Timeline.jsx";

describe("Timeline", () => {
  it("renders events with user and justification", () => {
    const entries = [
      {
        id: 1,
        event_type: "HOLD_PROPOSED",
        timestamp: "2026-09-27T12:00:00Z",
        user: "system",
        justification: null,
        detail: { hold_id: 1 },
      },
      {
        id: 2,
        event_type: "OVERRIDE_APPLIED",
        timestamp: "2026-09-27T12:05:00Z",
        user: "supervisor.demo",
        justification: "Deadline requires authorization.",
        detail: null,
      },
    ];

    render(<Timeline entries={entries} />);

    expect(screen.getByText("HOLD_PROPOSED")).toBeInTheDocument();
    expect(screen.getByText("OVERRIDE_APPLIED")).toBeInTheDocument();
    expect(screen.getByText("by supervisor.demo")).toBeInTheDocument();
    expect(screen.getByText(/Deadline requires authorization/)).toBeInTheDocument();
  });

  it("shows an empty state with no entries", () => {
    render(<Timeline entries={[]} />);

    expect(screen.getByText(/no preservation events/i)).toBeInTheDocument();
  });
});
