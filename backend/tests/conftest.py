"""Tests run against the real Postgres `bonafide` database (no SQLite —
locked architecture decision, see docs/ARCHITECTURE.md).

Two testing strategies are used side by side:
- `db_session`: wraps a test in its own transaction, rolled back afterward
  (fast, used for repository/model/engine unit tests).
- `demo_claim`: creates and commits a real claim via the same
  session_scope() the app uses, then deletes it (cascades) on teardown —
  needed for API-level tests, since app.services opens its own independent
  session_scope() per call and can't share a wrapping test transaction.

`ai_service_url` starts the REAL standalone AI service as a subprocess
(its own venv, its own process) for tests that need a genuine successful
classification/litigation round trip. This sidesteps a real constraint:
the AI service's code is also a top-level package named `app`, so it can't
be imported in-process alongside the core backend's `app` package without
a name collision — running it as a separate OS process is not just more
realistic, it's the only practical way to exercise it from these tests.
"""
import datetime as dt
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, session_scope
from app.enums import EvidenceType, ExpiryTrigger
from app.main import app as fastapi_app
from app.models import Claim
from app.repositories import add_evidence_item, create_claim


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def client():
    return TestClient(fastapi_app)


@pytest.fixture
def demo_claim():
    claim_id = f"CLM-TEST-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        create_claim(
            session,
            claim_id=claim_id,
            policy_id="POL-TEST",
            claim_type="PersonalAuto",
            loss_date=dt.date(2026, 1, 1),
            claimant="Test Claimant",
            description="Synthetic claim created for API tests.",
            repair_status="PENDING",
            upcoming_business_event=ExpiryTrigger.REPAIR_AUTHORIZATION,
        )
        add_evidence_item(
            session,
            claim_id=claim_id,
            evidence_type=EvidenceType.REPAIR_ESTIMATE,
            expiry_trigger=ExpiryTrigger.REPAIR_AUTHORIZATION,
            required=True,
            satisfied=False,
        )
    yield claim_id
    with session_scope() as session:
        claim = session.get(Claim, claim_id)
        if claim is not None:
            session.delete(claim)


_AI_SERVICE_DIR = Path(__file__).resolve().parent.parent.parent / "ai_service"
_AI_SERVICE_PYTHON = _AI_SERVICE_DIR / ".venv" / "Scripts" / "python.exe"
_AI_SERVICE_PORT = 8199
_AI_SERVICE_URL = f"http://127.0.0.1:{_AI_SERVICE_PORT}"


@pytest.fixture(scope="session")
def ai_service_url():
    process = subprocess.Popen(
        [str(_AI_SERVICE_PYTHON), "-m", "uvicorn", "app.main:app", "--port", str(_AI_SERVICE_PORT)],
        cwd=str(_AI_SERVICE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        healthy = False
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"{_AI_SERVICE_URL}/health", timeout=0.5)
                if response.status_code == 200:
                    healthy = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        if not healthy:
            process.terminate()
            raise RuntimeError("ai_service did not become healthy in time for tests")
        yield _AI_SERVICE_URL
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
