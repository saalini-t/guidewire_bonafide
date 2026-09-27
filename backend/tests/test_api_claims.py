def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_claim_returns_claim(client, demo_claim):
    response = client.get(f"/api/claims/{demo_claim}")

    assert response.status_code == 200
    assert response.json()["claim_id"] == demo_claim


def test_get_claim_missing_returns_404(client):
    response = client.get("/api/claims/CLM-DOES-NOT-EXIST")

    assert response.status_code == 404


def test_get_evidence_returns_seeded_item(client, demo_claim):
    response = client.get(f"/api/claims/{demo_claim}/evidence")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["evidence_type"] == "Repair Estimate"
    assert items[0]["satisfied"] is False


def test_analysis_reflects_one_unsatisfied_required_item(client, demo_claim):
    response = client.get(f"/api/claims/{demo_claim}/analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "MEDIUM"
    assert body["at_risk_evidence"] == ["Repair Estimate"]


def test_run_analysis_creates_analysis_run_log(client, demo_claim):
    response = client.post(f"/api/claims/{demo_claim}/analyze")

    assert response.status_code == 200
    assert response.json()["risk_level"] == "MEDIUM"

    log_response = client.get(f"/api/claims/{demo_claim}/preservation-log")
    event_types = [entry["event_type"] for entry in log_response.json()]
    assert "ANALYSIS_RUN" in event_types
