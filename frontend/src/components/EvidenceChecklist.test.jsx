import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EvidenceChecklist from "./EvidenceChecklist.jsx";

const analysis = {
  upcoming_event: "RepairAuthorization",
  at_risk_evidence: ["Vehicle Photographs"],
};

const evidence = [
  { id: 1, evidence_type: "Vehicle Photographs", required: true, satisfied: false, expiry_trigger: "RepairAuthorization" },
  { id: 2, evidence_type: "Police Report", required: true, satisfied: true, expiry_trigger: "ClaimClosure" },
  { id: 3, evidence_type: "Repair Estimate", required: true, satisfied: false, expiry_trigger: "ClaimClosure" },
];

describe("EvidenceChecklist", () => {
  it("distinguishes SATISFIED, AT RISK, and MISSING", () => {
    render(<EvidenceChecklist evidence={evidence} analysis={analysis} />);

    expect(screen.getByText("SATISFIED")).toBeInTheDocument();
    expect(screen.getByText("AT RISK")).toBeInTheDocument();
    expect(screen.getByText("MISSING")).toBeInTheDocument();
  });

  it("renders an empty state with no evidence", () => {
    render(<EvidenceChecklist evidence={[]} analysis={analysis} />);

    expect(screen.getByText(/no evidence items/i)).toBeInTheDocument();
  });
});
