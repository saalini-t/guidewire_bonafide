"""Keyword/heuristic provider. Always available, no external dependency —
this is what keeps the whole application demoable when Ollama isn't
running. Deterministic: same text in, same output out, every time.
"""
from app.providers.base import AIProvider, ClassificationOutcome, LitigationOutcome

_CLASSIFICATION_KEYWORDS: dict[str, list[str]] = {
    "Vehicle Photographs": [
        # Anchored to "of the vehicle/damage" or "attached" — a bare
        # "photograph"/"photo" stem matches as a substring of "photographs"
        # anywhere the word is merely mentioned (e.g. an attorney letter
        # listing "records, documents, photographs, communications..." as
        # categories of evidence to preserve), which is a false positive:
        # that document is not itself a vehicle-photo submission.
        "photo of the vehicle",
        "photograph of the vehicle",
        "photographs of the vehicle",
        "photos of the vehicle",
        "picture of the vehicle",
        "picture of the damage",
        "attached images",
        "image of the vehicle",
        "images of the vehicle",
    ],
    "Police Report": [
        "police report",
        "incident report",
        "responding officer",
        "case number",
        "citation issued",
    ],
    "Repair Appraisal": [
        "appraisal",
        "appraiser",
        "appraised value",
        "damage appraisal",
    ],
    "Vehicle Inspection": [
        "inspection report",
        "inspected the vehicle",
        "inspection findings",
        "vehicle was inspected",
    ],
    "Recorded Statement": [
        "recorded statement",
        "transcript of",
        "statement given by",
        "interview transcript",
    ],
    "Repair Estimate": [
        "repair estimate",
        "estimate for repairs",
        "body shop estimate",
        "parts and labor",
        "estimated cost of repair",
    ],
}

_LITIGATION_KEYWORDS: dict[str, list[str]] = {
    "attorney_representation": [
        # "represent" (not "represents") so it matches every conjugation:
        # represent/represents/representing/representation/representative.
        # The previous "represents"-only form missed "We represent the
        # claimant" (first-person plural) entirely.
        "represent",
        "our client",
        "law offices of",
        "legal counsel",
        "legal representation",
        "esq.",
        "attorney for",
        # Evidence-preservation-demand phrasing — the canonical
        # counterpart to "represent" in a real preservation-hold-triggering
        # letter (e.g. "we represent the claimant... please preserve all
        # relevant records/evidence"), corroborating rather than replacing
        # the representation signal above.
        "preserve all relevant",
        "preservation of relevant evidence",
    ],
    "demand_letter": [
        "demand letter",
        "demand payment",
        "settlement demand",
        "policy limits demand",
        "demand is made",
    ],
    "records_request": [
        "records request",
        "request for records",
        "please provide all records",
        "subpoena",
        "request for production",
    ],
}

# classification: score 0 -> "Other" @ 0.40; score N>=1 -> 0.55 + 0.15*N, capped
_CLASSIFICATION_BASE, _CLASSIFICATION_STEP, _CLASSIFICATION_CAP = 0.55, 0.15, 0.97
_NO_MATCH_CONFIDENCE = 0.40

# litigation: score 0 -> "none" @ 0.95; score N>=1 -> 0.60 + 0.15*N, capped.
# Two corroborating keyword hits (0.90) clears the 0.85 acceptance
# threshold; a single ambiguous hit (0.75) correctly does not.
_LITIGATION_BASE, _LITIGATION_STEP, _LITIGATION_CAP = 0.60, 0.15, 0.97
_NO_SIGNAL_CONFIDENCE = 0.95


def _best_match(lowered_text: str, keyword_map: dict[str, list[str]]) -> tuple[str | None, int]:
    best_label, best_score = None, 0
    for label, keywords in keyword_map.items():
        score = sum(1 for kw in keywords if kw in lowered_text)
        if score > best_score:
            best_label, best_score = label, score
    return best_label, best_score


class DeterministicProvider(AIProvider):
    name = "deterministic"

    def classify_document(self, text: str) -> ClassificationOutcome:
        label, score = _best_match(text.lower(), _CLASSIFICATION_KEYWORDS)
        if score == 0:
            return ClassificationOutcome(classification="Other", confidence=_NO_MATCH_CONFIDENCE)
        confidence = min(_CLASSIFICATION_BASE + _CLASSIFICATION_STEP * score, _CLASSIFICATION_CAP)
        return ClassificationOutcome(classification=label, confidence=confidence)

    def detect_litigation_signal(self, text: str) -> LitigationOutcome:
        label, score = _best_match(text.lower(), _LITIGATION_KEYWORDS)
        if score == 0:
            return LitigationOutcome(signal="none", confidence=_NO_SIGNAL_CONFIDENCE)
        confidence = min(_LITIGATION_BASE + _LITIGATION_STEP * score, _LITIGATION_CAP)
        return LitigationOutcome(signal=label, confidence=confidence)
