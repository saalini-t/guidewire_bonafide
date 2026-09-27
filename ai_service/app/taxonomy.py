"""Label taxonomy for this service. Intentionally duplicated from the core
app's app.enums rather than imported — the AI service is a separate
deployable with no dependency on the core backend's codebase (see
docs/ARCHITECTURE.md: it must not own claim state and must not be coupled
to the core domain model). Keep in sync by hand if the taxonomy changes.
"""

DOCUMENT_CLASSES: list[str] = [
    "Vehicle Photographs",
    "Police Report",
    "Repair Appraisal",
    "Vehicle Inspection",
    "Recorded Statement",
    "Repair Estimate",
    "Other",
]

LITIGATION_SIGNALS: list[str] = [
    "attorney_representation",
    "demand_letter",
    "records_request",
    "none",
]
