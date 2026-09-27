# Bona Fide — 4-Day Implementation Plan

Locked architecture: see `ARCHITECTURE.md`. This document tracks what gets
built each day and is updated as work completes (checkboxes reflect actual
state, not aspiration).

## Day 1 — Foundation: DB, models, preservation engine

- [x] Project structure (`backend/`, `docs/`, `storage/documents/`)
- [x] `.gitignore`, `.env.example`, `backend/.env` (local, gitignored)
- [x] `backend/requirements.txt`
- [x] Verify PostgreSQL connectivity (`bonafide` database, localhost:5432)
- [x] SQLAlchemy engine/session setup (`app/db.py`)
- [x] Domain models: Claim, EvidenceItem, Document, PreservationHold,
      PreservationLog (`app/models.py`)
- [x] Alembic setup + initial migration (schema owned by Alembic, not psql)
- [x] Repositories (`app/repositories.py`) — thin data-access functions per
      entity, no business logic
- [x] `preservation_engine.py` — pure, deterministic, no AI/DB dependency
- [x] Synthetic seed data — 5 claims: CLM-10042 (HIGH), plus LOW, MEDIUM,
      HIGH, and one with an ACTIVE hold
- [x] Tests: models, repositories, preservation engine, seed data (20
      tests, all passing against real Postgres)
- [x] End-of-day verification: migrate → seed → run analysis on CLM-10042
      → confirmed HIGH risk + 3 expected at-risk items

## Day 2 — APIs + AI service

- [x] FastAPI core app, Pydantic schemas, all `/api/claims/...` endpoints
- [x] `StorageBackend` / `LocalStorageBackend`
- [x] Standalone AI service (separate FastAPI app):
      `DeterministicProvider`, `OllamaProvider`, provider selection,
      `/classify-document`, `/detect-litigation-signal`, `/health`
- [x] Core app's AI client: HTTP, 2s timeout, fail-open, records
      `ai_provider` on the result
- [x] Two-transaction document classification flow (see `ARCHITECTURE.md`)
- [x] Hold workflow: proposed → confirm → active; override + justification
- [x] API tests (per risk tier, AI unavailable, low confidence, duplicate
      upload, transaction rollback) — 52 backend + 7 AI service tests, all
      passing
- [x] Full manual demo run against real running services (CLM-10042):
      upload → classify → evidence satisfied → litigation letter →
      PROPOSED hold → confirmed → ACTIVE → override → full audit trail

## Day 3 — Frontend

- [x] React + Vite scaffold
- [x] Claims Dashboard
- [x] Claim Details (evidence checklist, risk panel, upcoming event)
- [x] Document Upload + AI Classification + Litigation Signal display
- [x] Preservation Hold confirmation UI
- [x] Override UI
- [x] Audit Timeline
- [x] Frontend tests (19, Vitest + Testing Library)
- [x] Full manual demo run in a real headless browser (Playwright),
      screenshots captured at every step
- [ ] ClaimCenter Integration Gap page — deferred to Day 4 per the docs
      pass (not exercised by the Day 3 demo script)

## Day 4 — Integration, hardening, docs

- [ ] Full end-to-end manual run of the CLM-10042 demo script
- [ ] Kill the AI service mid-session, confirm fail-open behavior for real
- [ ] Full pytest suite (unit + API + one complete e2e test)
- [ ] Larger synthetic dataset + basic performance sanity check
- [ ] Remaining docs (`API_SPECIFICATION.md`, `PRESERVATION_LOGIC.md`,
      `AI_CLASSIFICATION.md`, `CLAIMCENTER_INTEGRATION.md`, `MVP_SCOPE.md`,
      `TEST_STRATEGY.md`, `DEMO_SCRIPT.md`, `SETUP.md`, `LIMITATIONS.md`,
      `ROADMAP.md`, root `README.md`)

## Scope Guardrails

Not added unless explicitly requested: Docker, Kubernetes, Redis, Kafka,
Celery, LangChain, Neo4j, RAG, pgvector, authentication, multi-tenancy,
cloud deployment, real Guidewire/Gosu/PCF integration.
