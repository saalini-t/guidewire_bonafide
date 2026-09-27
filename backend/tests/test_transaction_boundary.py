"""Covers Day 2 acceptance item T: verify no DB transaction/connection
remains checked out from the pool while the AI HTTP call is in flight.
This is a concrete check, not an inference from reading the code — it spies
on the connection pool's own checkedout() count at the exact moment the AI
client is invoked.
"""
from app.ai_client import AIClassificationResult, AILitigationResult
from app.db import engine


def test_no_db_connection_checked_out_during_ai_call(client, demo_claim, monkeypatch):
    checkout_counts_during_ai_call = []

    class SpyAIClient:
        def classify_document(self, text):
            checkout_counts_during_ai_call.append(engine.pool.checkedout())
            return AIClassificationResult(available=True, classification="Other", confidence=0.5, provider="deterministic")

        def detect_litigation_signal(self, text):
            checkout_counts_during_ai_call.append(engine.pool.checkedout())
            return AILitigationResult(available=True, signal="none", confidence=0.95, provider="deterministic")

    monkeypatch.setattr("app.services.ai_client", SpyAIClient())

    upload = client.post(f"/api/claims/{demo_claim}/documents", json={"filename": "note.txt", "text": "hello world"})
    document_id = upload.json()["id"]

    response = client.post(f"/api/claims/{demo_claim}/documents/{document_id}/classify")

    assert response.status_code == 200
    assert checkout_counts_during_ai_call, "AI client was never invoked"
    assert all(count == 0 for count in checkout_counts_during_ai_call), (
        f"A DB connection was checked out from the pool during an AI call: {checkout_counts_during_ai_call}"
    )
