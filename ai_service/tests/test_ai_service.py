"""OLLAMA_BASE_URL is empty in this environment's .env (Ollama isn't
installed here), so classify/litigation calls normally skip Ollama
entirely via the `if settings.ollama_base_url:` short-circuit. The
dedicated fallback test below instead points settings at a real-but-
unreachable URL to exercise the OTHER fallback path: Ollama configured,
but the connection genuinely fails.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "ollama_configured" in body


def test_classify_document_high_confidence_matches_repair_estimate():
    text = "Attached is the repair estimate from the body shop, covering parts and labor for the rear bumper."

    response = client.post("/classify-document", json={"text": text})

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "Repair Estimate"
    assert body["confidence"] >= 0.85
    assert body["provider"] == "deterministic"  # no Ollama running in this environment


def test_classify_document_with_no_keyword_match_returns_other_low_confidence():
    text = "Please see the attached file for your review."

    response = client.post("/classify-document", json={"text": text})

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "Other"
    assert body["confidence"] < 0.85


def test_classify_document_rejects_empty_text():
    response = client.post("/classify-document", json={"text": ""})

    assert response.status_code == 422


def test_litigation_detects_attorney_representation():
    text = (
        "The Law Offices of Smith & Associates represents the claimant in this matter. "
        "Please direct all further correspondence to our legal counsel, attorney for Jordan Reyes."
    )

    response = client.post("/detect-litigation-signal", json={"text": text})

    assert response.status_code == 200
    body = response.json()
    assert body["signal"] == "attorney_representation"
    assert body["confidence"] >= 0.85
    assert body["provider"] == "deterministic"


def test_litigation_detects_natural_attorney_preservation_letter():
    """Regression test for a real bug found in live Day 3 testing: a
    textbook attorney evidence-preservation letter phrased naturally
    ("We represent the claimant... please preserve all relevant
    records... legal representation... preservation of relevant
    evidence") previously returned signal="none" at 0.95 confidence,
    because the keyword list only matched "represents" (third-person)
    and missed "represent" (first-person plural), and had no other
    keyword that matched this letter's actual wording.
    """
    text = (
        "We represent the claimant in connection with this insurance matter.\n\n"
        "Please preserve all relevant records, documents, photographs,\n"
        "communications, estimates, reports, and other evidence relating\n"
        "to this claim.\n\n"
        "This correspondence concerns the claimant's legal representation\n"
        "and preservation of relevant evidence."
    )

    response = client.post("/detect-litigation-signal", json={"text": text})

    assert response.status_code == 200
    body = response.json()
    assert body["signal"] == "attorney_representation"
    assert body["confidence"] >= 0.85


def test_natural_attorney_preservation_letter_is_not_classified_as_vehicle_photographs():
    """Companion regression test: the same letter merely mentions
    "photographs" as one item in a list of evidence categories to
    preserve — it is not itself a vehicle-photo submission. The bare
    "photograph" keyword previously matched as a substring of
    "photographs" regardless of context, misclassifying it.
    """
    text = (
        "We represent the claimant in connection with this insurance matter.\n\n"
        "Please preserve all relevant records, documents, photographs,\n"
        "communications, estimates, reports, and other evidence relating\n"
        "to this claim.\n\n"
        "This correspondence concerns the claimant's legal representation\n"
        "and preservation of relevant evidence."
    )

    response = client.post("/classify-document", json={"text": text})

    assert response.status_code == 200
    assert response.json()["classification"] != "Vehicle Photographs"


def test_litigation_returns_none_when_no_signal_keywords_present():
    text = "Enclosed please find the vehicle inspection report requested last week."

    response = client.post("/detect-litigation-signal", json={"text": text})

    assert response.status_code == 200
    body = response.json()
    assert body["signal"] == "none"


def test_ollama_configured_but_unreachable_falls_back_to_deterministic_provider(monkeypatch):
    """Regression test for the fallback contract: with OLLAMA_BASE_URL
    pointed at a real-but-unreachable address (a port nothing listens on,
    as opposed to the empty/disabled default in this environment's .env),
    the request must still succeed via DeterministicProvider rather than
    erroring out, and must never claim the result came from Ollama.
    """
    monkeypatch.setattr("app.services.classification.settings.ollama_base_url", "http://127.0.0.1:59996")

    response = client.post("/classify-document", json={"text": "repair estimate, parts and labor included"})

    assert response.status_code == 200
    assert response.json()["provider"] == "deterministic"
