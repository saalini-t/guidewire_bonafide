# Project Audit — Bona Fide MVP

Date: 2026-09-27

## 1. Repository Structure

`C:\Saalu_Data\guidewire\` contains a single subfolder, `bondafide\`, which is
**completely empty** (no files, no `.git`, no hidden config). There is no
parent-level git repository either. This is a greenfield project — nothing
has been scaffolded yet.

## 2. Existing Code

None. No frontend, no backend, no dependency manifests, no data files, no
CI config, no `.env` files.

## 3. What Can Be Reused

Nothing from this directory. Nothing to reuse, nothing to conflict with —
no risk of duplicating existing logic or fighting an existing structure.

## 4. What Is Missing

Everything the spec asks for:
- Backend (FastAPI app, models, services, preservation engine, AI provider abstraction)
- Frontend (React app, pages, components)
- Storage (SQLite file + seed script)
- Tests
- `docs/` set (14 files listed in the spec)
- Root `README.md`
- Env var scaffolding (`.env.example`)

## 5. Proposed MVP Architecture

Matches the spec as-is; no adjustments needed since there's nothing to
reconcile it against.

```
bondafide/
  backend/
    app/
      main.py                 # FastAPI app, routes
      models.py                # Claim, EvidenceItem, Document, PreservationHold, PreservationLog
      db.py                     # SQLite via sqlite3 or SQLAlchemy (lean: sqlite3 + light wrapper)
      preservation_engine.py    # deterministic rules, pure functions, unit-testable
      ai/
        base.py                 # Provider interface (classify, detect_litigation)
        deterministic.py        # keyword/heuristic fallback provider (default, no API key needed)
        openai_provider.py       # optional, only if OPENAI_API_KEY set
      seed_data.py              # 5 synthetic claims incl. CLM-10042
    tests/
      test_preservation_engine.py
      test_ai_classification.py
      test_api_e2e.py
    requirements.txt
  frontend/
    (Vite + React, minimal deps: react, react-dom, react-router-dom)
    src/
      pages/ (Dashboard, ClaimDetail, ClaimCenterGap)
      api.js
  docs/
    PROJECT_AUDIT.md (this file)
    PROJECT_OVERVIEW.md, ARCHITECTURE.md, SYSTEM_DESIGN.md, DATA_MODEL.md,
    API_SPECIFICATION.md, PRESERVATION_LOGIC.md, AI_CLASSIFICATION.md,
    CLAIMCENTER_GAP.md, CLAIMCENTER_INTEGRATION.md, MVP_SCOPE.md,
    DEMO_SCRIPT.md, SETUP.md, TEST_STRATEGY.md, ROADMAP.md, LIMITATIONS.md
  README.md
```

**Ponytail notes on stack choices** (lazy = fewest moving parts that still
satisfy the spec):
- SQLite via Python's built-in `sqlite3` module, not SQLAlchemy — the spec's
  data model is 5 small tables with no complex joins; an ORM is a dependency
  and abstraction the MVP doesn't need. One `db.py` with plain SQL is enough.
  Upgrade to SQLAlchemy only if the schema grows relationships that make raw
  SQL painful.
- Frontend build tool: Vite (industry-standard minimal React scaffold, not
  Create React App which is deprecated).
- No Docker, no microservices, single FastAPI process + single React dev
  server, as the spec explicitly requires ("do not build unnecessary
  microservices").
- AI provider abstraction: a single `ClassifierProvider` interface with two
  concrete implementations (deterministic keyword-matcher, optional
  OpenAI-backed one gated on an env var). No plugin registry/factory pattern
  — just an `if OPENAI_API_KEY: ... else: ...` at startup, since there are
  only ever two providers in scope for the MVP.

## 6. Proposed Implementation Phases

1. **Backend core**: models, SQLite schema + seed data (5 claims incl.
   CLM-10042), preservation engine (pure functions) + unit tests.
2. **Backend API**: FastAPI routes wired to the engine, deterministic AI
   provider, document classification/litigation endpoints, hold
   create/confirm/override, preservation log.
3. **Frontend**: Claims Dashboard, Claim Detail (evidence checklist, risk
   panel, AI analysis, holds, timeline), Document Upload, ClaimCenter Gap
   page.
4. **End-to-end wiring + demo pass**: run the full CLM-10042 workflow
   (upload attorney letter → classify → propose hold → confirm → timeline
   updates) manually to confirm it behaves as scripted.
5. **Tests**: engine unit tests, API tests per risk tier (low/med/high),
   AI classification + low-confidence path, one full e2e test.
6. **Docs**: write the 14 docs + README + CLAIMCENTER_INTEGRATION.md,
   reflecting what was actually built (not aspirational).

## 7. Conflicts Between Spec and MVP Approach

None found — there is no existing code or architecture to conflict with.
Two spec items worth flagging as intentional lazy calls rather than
deviations:

- The spec asks for "provider abstraction so we can use local LLM /
  API-based LLM / deterministic fallback" — three tiers. Proposing to build
  two (deterministic + optional API-based) and skip a local-LLM provider
  entirely, since standing up a local model server is out of scope for an
  MVP demo and adds a real dependency (Ollama or similar) nobody asked to
  install. The interface will make adding a third provider a one-file
  change later.
- SQLite access via raw `sqlite3` instead of an ORM (see above) — flagging
  in case there's a preference for SQLAlchemy models for future ClaimCenter
  integration work.

## Next Step

Per instructions, implementation has not started. Awaiting approval of this
audit and the proposed architecture/phases before writing any code.
