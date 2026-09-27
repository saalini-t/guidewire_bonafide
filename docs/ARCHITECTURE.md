# Bona Fide — Architecture (Locked)

Status: Approved. Supersedes the architecture options explored in
`ARCHITECTURE_AUDIT.md` — this document describes what is being built, not
what was considered.

## System Overview

```
React + Vite  ──REST(JSON)──▶  FastAPI core application  ──HTTP──▶  Bona Fide AI Service
                                       │                                  │
                                       ▼                                  ▼
                                 PostgreSQL 18                    (stateless, no DB)
                                 database: bonafide          DeterministicProvider (default)
                                 (SQLAlchemy + Alembic)       OllamaProvider (optional)
                                       │
                                       ▼
                              Local filesystem
                            (storage/documents/,
                             behind StorageBackend)
```

Two processes, one database, owned exclusively by the core application. The
AI service is stateless and never touches Postgres.

## Core Application (FastAPI, one process)

Internal modules, all in one codebase, one process, one database connection
pool:

- **Claim** — claim records, lifecycle status, upcoming business event.
- **Evidence** — evidence checklist per claim, satisfaction state, expiry
  triggers.
- **Document** — document metadata + storage pointer; bytes live on disk via
  `StorageBackend`.
- **Preservation** — deterministic risk engine (`preservation_engine.py`).
  Pure functions: domain data in, `PreservationAnalysis` out. No AI calls,
  no DB calls.
- **Hold** — preservation hold lifecycle: PROPOSED → ACTIVE → RELEASED.
- **Audit** — append-only `preservation_logs`, no update/delete endpoint.

These modules share one Postgres database and may share a transaction when
a state transition requires atomicity (see Transactional Design below).

## AI Service (FastAPI, separate process, stateless)

Endpoints: `POST /classify-document`, `POST /detect-litigation-signal`,
`GET /health`.

Providers, selected internally by the AI service (never by the caller):

1. `DeterministicProvider` — keyword/heuristic classifier. Always
   available. Default.
2. `OllamaProvider` — used automatically if `OLLAMA_HOST` is configured and
   reachable at request time. Optional, additive.

Every response records which provider produced it (`ai_provider` field) —
a deterministic result is never reported as having come from Ollama.

The AI service owns no claim state. It receives text, returns a
classification/signal + confidence, and forgets it.

### Failure semantics (asymmetric, by design)

- **AI unavailable, times out, or returns invalid JSON → fail open.** The
  document stays `classification_status=PENDING` / gets flagged for manual
  review. The claim workflow does not fail because AI is down.
- **Deterministic preservation rules → fail closed.** AI availability has
  no effect on the preservation engine's risk calculation or on the rule
  that blocks a destructive operation when required evidence is missing.
  This asymmetry is enforced in code, not just in docs: the preservation
  engine has no AI dependency to fail in the first place (see below).

## Transactional Design

**Rule: never hold a Postgres transaction open while waiting on the AI
service's HTTP call.** Two transactions, not one, for the document
classification workflow:

```
POST /api/claims/{id}/documents
    BEGIN
      insert document row, classification_status = PENDING
    COMMIT
    (request returns; AI call has not happened yet)

POST /api/claims/{id}/documents/{doc_id}/classify
    → call AI service over HTTP (outside any transaction)
    → on success or failure, open a NEW transaction:
        BEGIN
          update document.classification / confidence / ai_provider
          update matching evidence_item.satisfied (if applicable)
          insert preservation_hold (PROPOSED) if litigation signal fires
          insert preservation_log event
        COMMIT   (all-or-nothing; a failure here rolls back cleanly,
                  leaving the document merely still PENDING/unclassified —
                  never a half-applied state)
```

This is the one place in the system where multiple tables change together
and must be atomic (Section 9 of the architecture audit) — and it is
deliberately kept clear of any network call.

## Database

PostgreSQL 18, database `bonafide`, schema owned entirely by Alembic
migrations (no manual `psql` DDL). SQLAlchemy models are the single source
of truth for the schema; Alembic autogenerates migrations from them.

## Document Storage

`StorageBackend` interface (`save(bytes) -> uri`, `load(uri) -> bytes`).
`LocalStorageBackend` is the only implementation for the MVP, writing under
`storage/documents/`. Postgres stores only metadata (filename, storage
path, extracted text, classification results) — never document bytes.
Swapping in S3/Azure/GCS later means writing one new class, no schema or
caller changes.

## API Surface

Pydantic schemas at every API boundary — SQLAlchemy models are never
returned directly from an endpoint. See `API_SPECIFICATION.md` (written
alongside Day 2) for the full contract.

## Explicitly Out of Scope for the MVP

Docker, Kubernetes, Redis, Kafka, Celery, LangChain, Neo4j, RAG, pgvector,
authentication, multi-tenancy, cloud deployment, real Guidewire/Gosu/PCF
integration. See `MVP_SCOPE.md` and `CLAIMCENTER_INTEGRATION.md`.

## Future Guidewire Mapping

See `CLAIMCENTER_INTEGRATION.md` for the full mapping (written once the
domain models below are finalized). Summary: the AI service's contract and
failure semantics are designed to survive unchanged into production,
called by a Gosu `BonaFideAIClient` instead of this repo's Python HTTP
client; the domain modules map onto ClaimCenter extension entities and
business rules.
