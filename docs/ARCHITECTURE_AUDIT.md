# Bona Fide Architecture Audit

Date: 2026-09-27
Status: Architecture decision stage — no code written under this audit.

## 1. Executive Summary

Bona Fide's MVP has one genuinely hard architectural question and it isn't
"monolith vs. microservices" in the abstract — it's **where does the
service boundary that already exists in production (ClaimCenter ↔ stateless
AI service) belong in the MVP, and does anything else deserve a boundary
too.**

The production spec already answers half the question: ClaimCenter (source
of truth, transactional, fail-closed) and the Bona Fide AI Service
(stateless, HTTP, fail-open) are two deployables connected by a narrow,
well-typed HTTP contract. That split is driven by an organizational/deployment
boundary (different systems, different failure semantics), not by scale. It
should be rehearsed in the MVP as-is.

Nothing else in the spec has that kind of natural seam. Claim, Evidence,
Hold, and Audit form one transactional saga (Section 9) — an insurance
compliance control where a hold with no audit record, or a satisfied
evidence item with no classified document, is a correctness bug, not an
eventual-consistency inconvenience. Splitting that saga across services
would force distributed transactions or a saga/compensation pattern to
reconstruct guarantees a single Postgres transaction gives for free.

**Recommendation (short form):** MVP = modular monolith for the
Claim/Evidence/Preservation/Hold/Audit domain, plus one standalone AI
service process, communicating over HTTP with a timeout and fail-open
behavior — i.e., the minimum slice of Option B, not the whole thing.
Full microservices (Option C) are not justified now and are unlikely to be
justified later; if the AI service ever needs to scale independently, that's
a second replica of the same process, not a redesign.

## 2. Requirements Summary

- 4-day build window, single/small dev team, empty repo (Section 18).
- Core product behavior: a deterministic, auditable preservation-gap engine
  (Sections 1, 5, 22) that must never be silently overridden by AI output
  (Section 7, 8).
- AI is explicitly stateless, swappable (Ollama / deterministic /
  external API), and must not own claim state (Section 15).
- Two different failure semantics are required by spec, not incidental:
  AI unavailable → fail open; preservation rules → fail closed (Section 8).
- Production target is a Guidewire ClaimCenter accelerator (Section 3),
  not a standalone platform — the MVP's domain boundaries should map onto
  that target without a rewrite (Section 17).
- Data scale target is 100–100,000+ claims (Section 16) — meaningful for
  document storage design, not meaningful for choosing a service topology.
- Postgres 18.1 is already installed with a `bonafide` database provisioned
  (Section 17) — this is the path of least setup, not just a preference.

## 3. Functional Architecture

```
                         React (Vite)
                              |
                              | REST (JSON)
                              v
                 ┌─────────────────────────┐
                 │   Bona Fide Backend      │   ← modular monolith
                 │   (FastAPI, one process) │
                 │                          │
                 │  claim module            │
                 │  evidence module         │
                 │  document module         │
                 │  preservation module     │──┐ deterministic,
                 │  hold module             │  │ fail-closed,
                 │  audit module            │──┘ single DB transaction
                 │  storage abstraction ────┼──> local filesystem
                 └───────────┬──────────────┘   (swap for S3/Blob later)
                              |
                              | HTTP, 2s timeout, fail-open
                              v
                 ┌─────────────────────────┐
                 │  Bona Fide AI Service    │   ← standalone process
                 │  (FastAPI, stateless)    │      (mirrors production
                 │                          │       Gosu→HTTP contract)
                 │  POST /classify-document │
                 │  POST /detect-litigation-signal
                 │  GET  /health            │
                 │                          │
                 │  ProviderInterface       │
                 │   ├─ DeterministicProvider (default, always on)
                 │   └─ OllamaProvider (optional, if reachable)
                 └───────────┬──────────────┘
                              |
                              v
                        PostgreSQL 18
                    (claims, evidence, documents-metadata,
                     holds, logs — one database, one owner:
                     the backend. AI service is stateless and
                     touches no tables.)
```

Two processes, one database (owned exclusively by the backend), one
filesystem directory for document bytes. No gateway, no broker, no service
discovery — none of the requirements below call for them.

## 4. Non-Functional Requirements

| Requirement | Driver | Implication |
|---|---|---|
| Deterministic rules never bypassed by AI | Section 7, 8 | Preservation engine is pure Python, called in-process, no network hop, no way for it to silently fail open |
| AI fail-open, rules fail-closed | Section 8 | These are different subsystems by design — the asymmetry itself argues for AI being a separable component, not for further splitting |
| Full audit trail | Section 5, 22 | Every state transition (classify → satisfy → signal → hold → confirm) needs one durable transaction |
| Swappable AI provider | Section 15 | Interface + 2 implementations, selected by config, not a plugin registry |
| Scale to 100k+ claims | Section 16 | Relational schema + indexes; not a service-count problem |
| Document volume growth | Section 16 | Storage interface now, filesystem today, object store later — decouple "where bytes live" from "what the DB tracks" |
| 4-day delivery | Section 12/13 | Every extra process, deploy target, or abstraction is time not spent on the actual demo |

## 5. Architecture Option A — Modular Monolith

Single FastAPI process, internally split into modules by responsibility
(claim, evidence, document, preservation, hold, audit), single Postgres
database, Ollama/AI called via a Python interface in-process.

**Strengths:** fastest to build and debug, one DB transaction spans the
whole preservation workflow for free, one process to run/restart for a
demo, trivial local dev (`uvicorn main:app`), no network failure modes to
simulate.

**Weakness against this spec specifically:** if AI classification lives
in-process, you cannot *actually* demonstrate "AI service unavailable →
fail open" (Section 8, Section 23-B) — you'd have to fake it with a flag,
which is a worse rehearsal of the real production behavior (Gosu calling
out over HTTP with a 2s timeout, Section 10) than just building it that way.

## 6. Architecture Option B — Small Service-Oriented Architecture

As specified: Claim Service, Evidence/Preservation Service, AI Service,
each independently deployed, behind a gateway, own Postgres or shared
Postgres.

**Strengths:** AI isolation is real; independent scaling is possible in
principle.

**Weaknesses:** splitting Claim from Evidence/Preservation breaks the exact
transaction the product depends on (Section 9) — the classify → satisfy →
signal → hold → confirm → audit chain would now cross a service boundary
with no technical reason to. That forces a distributed-transaction or saga
pattern to reconstruct a guarantee a single `BEGIN...COMMIT` already gives.
An API gateway and multi-service deployment also costs real setup time
against a 4-day budget for zero benefit at this scale (5–100k claims is a
non-event for one Postgres instance).

**Verdict:** the full 3-way split in the spec's Option B is not justified.
The one part of it that *is* justified — AI as its own service — should be
taken, and the rest left as a monolith. See Section 16 for the recommended
hybrid.

## 7. Architecture Option C — Full Microservices

Eight-plus services, potentially a message broker, service discovery,
per-service databases.

**Strengths:** none that apply at this project's actual scale or team size.

**Weaknesses:** every failure mode in Section 23 gets harder (more network
hops = more partial-failure states to handle), every consistency guarantee
in Section 9 gets harder (a hold confirmation now spans Evidence Service +
Hold Service + Audit Service, each with a `COMMIT` in a different
database — a crash between any two leaves the compliance record wrong), and
operational overhead (deploying, monitoring, and debugging 8 services) is
disproportionate to a project whose entire dataset at "large scale" is a
few hundred thousand rows across five tables. There is no line item in
Sections 20/24 that this buys back.

**Verdict:** not justified now, and no scale target in this spec's future
(Section 16, 24) changes that conclusion. If Bona Fide ever needs true
microservices, it would be driven by something not in scope here — e.g.
becoming a multi-tenant SaaS platform with per-carrier data isolation
requirements — not by claim volume or AI load.

## 8. Architecture Comparison

| Criterion | A. Modular Monolith | B. Small SOA (as specified) | C. Full Microservices |
|---|---|---|---|
| MVP speed (4 days) | Best | Worse — gateway + 3 deploy targets | Infeasible in 4 days |
| Complexity | Low | Medium | High |
| Scalability (this project's actual targets) | Sufficient to 100k+ claims | No advantage over A at this scale | Over-provisioned |
| Testing | Easiest — one process, one DB | Harder — cross-service test setup | Hardest |
| Deployment | One backend + one frontend | Gateway + 3 services | Many services + infra |
| Failure isolation | AI failure isolated only if called over HTTP (see hybrid) | Good, but isolates things that don't need isolating (Claim vs Evidence) | Good, but at large ops cost |
| Consistency (Section 9 chain) | Trivial — one transaction | Broken — needs saga/2PC across Claim/Evidence split | Broken further |
| Auditability | Strong by default | Weakened by cross-service writes | Weakest |
| AI isolation | None, unless AI is split out (hybrid) | Yes | Yes |
| Guidewire integration fit | AI module maps 1:1 to future AI Service if given a clean interface | Matches production shape but over-splits the ClaimCenter-side domain | No production analogue |
| Maintainability (small team) | High | Medium | Low |
| 4-day feasibility | Yes | Marginal, only by cutting scope elsewhere | No |

**Recommended hybrid (not a 4th named option, just the honest scoring
result):** Option A for everything except AI, Option B's AI/rest split for
AI only. This is what Section 16 recommends.

## 9. Data Consistency Analysis

Workflow: document uploaded → classified → evidence satisfied → litigation
signal detected → proposed hold created → user confirms → active hold →
audit event.

- **Document uploaded → classified:** can be eventually consistent. The
  spec's own production design encodes this (`ClassificationPending_Ext`,
  Section 5 Rule 4) — a document can sit in "pending" state briefly. No
  transaction requirement.
- **Classified → evidence satisfied:** **must** be one transaction. A
  classification result recorded without the matching evidence item being
  marked satisfied (or vice versa) is a silent data integrity bug that
  directly undermines the product's core promise.
- **Litigation signal → proposed hold created:** **must** be one
  transaction. A detected signal with no resulting hold record (or a hold
  with no recorded trigger) breaks the audit trail that is the entire point
  of the product.
- **User confirms → active hold → audit event:** **must** be one
  transaction. This is the safety-critical control path (Section 5 Rule 3,
  Section 11). An "active" hold with no audit record, or a confirmed action
  that didn't actually flip the hold to active, is precisely the kind of
  gap the product exists to prevent — and would itself be a compliance
  finding if it happened in production.

**Conclusion:** everything from "classified" through "audit event" needs to
happen inside a single ACID transaction against a single database. This is
the strongest single argument in this audit against splitting Claim,
Evidence, Hold, and Audit into separate services — doing so would require
reintroducing (via 2PC or saga/compensation) a guarantee that one
`BEGIN...COMMIT` in Postgres already provides for free. It does **not**
argue against separating AI, because AI's output (classification,
confidence, signal type) is an *input* to that transaction, not a
participant in it — the backend calls AI, gets a result, and then runs the
whole downstream chain as one local transaction.

## 10. AI Architecture Analysis

Evaluated: (A) Ollama on the same machine as the app, (B) Ollama as an
independent local service, (C) separate AI service process, (D) external
API.

- **Ollama placement:** Ollama already runs as its own local daemon
  (`ollama serve`) regardless of how the app calls it — so (A) vs (B) is
  not really a choice the app architecture makes; Ollama is always a
  separate process on the machine. The real decision is what calls it.
- **Recommended MVP arrangement:** a standalone Bona Fide AI Service
  (FastAPI, Section 3/10 contract exactly) that internally holds the
  provider interface:
  - `DeterministicProvider` — keyword/heuristic classifier, zero setup,
    always available. **Default.** Guarantees the demo works on a machine
    with no Ollama installed.
  - `OllamaProvider` — used automatically if `OLLAMA_HOST` is reachable at
    startup; produces more convincing classifications for the demo when
    available. Optional, additive polish, never a hard dependency.
  - No external paid API provider is needed for the MVP (spec explicitly
    forbids dependence on one, Section 15/17 "architecture requirements");
    the interface leaves room for one later without changing callers.
- The backend calls this service over HTTP with a short timeout (mirrors
  Section 10's `java.net.http.HttpClient`, 2s timeout, fail-open exactly),
  so the MVP rehearses the actual production failure contract instead of
  faking it.
- **Future production arrangement:** the same AI service, unchanged
  contract, deployed as its own container, called by the real
  `BonaFideAIClient` Gosu plugin instead of the MVP's Python HTTP client
  (Section 10). `OllamaProvider` would likely be replaced or supplemented
  by a hosted model behind the same interface. No rewrite of the contract
  is needed — that's the point of building it this way now.

## 11. Database Analysis

| | PostgreSQL | SQLite | MySQL |
|---|---|---|---|
| Transactional consistency | Full ACID, real isolation levels | ACID but single-writer, weaker concurrent-write story | Full ACID |
| Concurrent access | Good — needed once frontend + AI service + any future batch sweep all hit it | Poor for concurrent writers, fine for the AI service's read-nothing pattern but not for a multi-user demo | Good |
| JSON support | Native `jsonb`, indexable | JSON1 extension, weaker | JSON type, weaker than jsonb |
| Full-text search | Built-in (`tsvector`) — useful for document text later | Limited (FTS5 extension) | Weaker |
| pgvector (future) | Direct path, same database | Not available | Not available |
| Migrations | Standard tooling (Alembic) | Same tooling works, but less need | Standard tooling |
| Dev complexity | One extra local dependency — **already installed and provisioned** (Section 17) | Zero setup | Not installed, no reason to add it |

**Recommendation: PostgreSQL.** This isn't the "safe familiar choice" —
it's the objectively better fit (real concurrency, jsonb for flexible
classification metadata, a straight path to pgvector if document
semantic search is ever wanted) *and* it's already sitting there installed
and provisioned as `bonafide`. SQLite would only win on "even less setup,"
and there is no setup left to save. MySQL has no advantage over Postgres
here and isn't installed. Raw `sqlite3`/ORM debate from the prior audit is
superseded — use SQLAlchemy Core or plain `psycopg`/`asyncpg` with
hand-written SQL; either is fine at this schema size, ORM-vs-not is not an
architecture-level decision.

## 12. Document Storage Analysis

| | In Postgres (bytea) | Local filesystem | Object storage (S3/Blob/GCS) | Hybrid (metadata in DB, bytes elsewhere) |
|---|---|---|---|---|
| MVP setup cost | Low | Lowest | Highest (cloud account, credentials) | Same as whichever bytes-store is chosen |
| Scales with document volume | Bloats the DB, hurts backup/restore | Fine to tens of thousands of files | Best | Best |
| Matches Section 16's explicit instruction | Explicitly discouraged | Explicitly allowed for MVP | Explicitly named as future | This *is* the pattern |

**Recommendation:** Hybrid — always. Postgres stores document metadata
(filename, content hash, size, content type, classification result,
storage URI). A thin `StorageBackend` interface (`save(bytes) -> uri`,
`load(uri) -> bytes`) has one implementation now (`LocalFilesystemStorage`)
and gets a second (`S3Storage`) in production without touching any caller.
This is exactly what Section 16 asks for, and it costs one small interface
now versus a schema migration later if documents were put directly in
Postgres.

## 13. Scalability Analysis

| Claims | What actually matters | Bottleneck? |
|---|---|---|
| 10 | Nothing | None |
| 1,000 | Nothing | None |
| 10,000 | Indexes on `claim_id` foreign keys | None if indexed |
| 100,000 | Document count/size, not claim count | Filesystem layout (flat dir vs. sharded by claim_id), not the DB |
| 1,000,000 | Synchronous AI classification in the request path | AI service throughput, if classification is still done inline per upload |

Postgres handles a few hundred thousand rows across five narrow tables
without any special design — that is a non-event for a relational
database. The first real bottleneck as volume grows is **document storage
management** (flat-directory filesystem storage starts to strain well
before claim count does — mitigate by sharding storage paths by claim ID,
a filesystem detail, not a service-topology one) and **synchronous AI
calls** if classification stays on the request path at high upload volume
(mitigate with a background queue/worker reusing the same AI service,
mirroring the production `BonaFideClassificationBatch` sweep — an
application-level change, not a reason to add microservices).

**Explicitly: none of the scale targets in Section 16 (up to 100,000+
claims) individually justify splitting the transactional core into
services.** They justify a storage-path decision and, far later, a
background job.

## 14. Failure Analysis

| Scenario | Modular Monolith (+ separate AI service) | Full SOA (Option B) | Full Microservices (Option C) |
|---|---|---|---|
| A. Ollama unavailable | AI service falls back to `DeterministicProvider` automatically | Same | Same |
| B. AI service unavailable | Backend HTTP call times out at 2s → document marked unclassified, manual-review flag set, upload still commits (fail-open, Section 8) | Same, plus gateway must also handle the timeout | Same, plus more services in the call graph that could also be down |
| C. PostgreSQL unavailable | Whole app degrades — correct, since Postgres is the single source of truth (fail-closed is appropriate here) | Multiple services degrade independently, harder to reason about which writes landed | Same, worse — multiple databases means partial-write scenarios across services |
| D. Document storage unavailable | Upload fails cleanly at the storage interface; classification/evidence chain untouched | Same, but now behind a service boundary and its own timeout | Same |
| E. Frontend unavailable | Backend/API still testable via curl/Swagger UI | Same | Same |
| F. Preservation engine error | Caught in-process, one stack trace, fail-closed (block the operation) — correct default for a compliance-critical rule | Same logic, now reachable over the network from a gateway — one more hop that can fail | Same, plus which service "owns" the error is less obvious |
| G. AI returns invalid JSON | AI service's own response validation catches it, returns `unclassified` + low confidence, same as a timeout | Same | Same |
| H. AI returns low confidence | Below-threshold path: manual-review flag, no automatic irreversible action (Section 7/8) — enforced in the preservation module, not the AI service | Same, as long as the Evidence/Preservation service enforces it, not the AI service | Same, but now a cross-service policy that's easier to accidentally duplicate or skip |
| I. Duplicate document upload | Enforced by a DB unique constraint (e.g. content hash + claim_id) inside the one transaction | Needs a cross-service check or a duplicate constraint replicated in whichever service owns Document | Same, more places it can be missed |
| J. Simultaneous hold confirmation | Enforced by a DB row lock / optimistic version check inside one transaction — trivial | Needs distributed locking or a saga compensating action if two services race | Same, harder |

The pattern across every row: the monolith-plus-AI-service hybrid handles
every scenario with a mechanism already built for a different reason (one
DB, one transaction, one timeout to one external service). Splitting the
core domain buys nothing on this table and adds a distributed-locking or
saga design burden on rows I and J specifically.

## 15. Future Guidewire Integration

The recommended hybrid is not a detour from the production architecture —
it **is** the production architecture, minus ClaimCenter itself:

- MVP's AI Service → becomes the production Bona Fide AI Service unchanged
  in contract (Section 3, 7, 10). Only the caller changes: MVP's Python
  HTTP client → production's Gosu `BonaFideAIClient` (`java.net.http.HttpClient`,
  same 2s timeout, same fail-open).
- MVP's Claim/Evidence/Preservation/Hold/Audit modules → become
  ClaimCenter customizations: `EvidenceItem_Ext`, `Hold_Ext`,
  `PreservationLog_Ext`, `Claim.etx`, `Document.etx` fields and the four
  business rules in Section 5. The preservation engine's *logic* (pure
  functions, unit-tested in the MVP) ports directly to Gosu rule bodies —
  the hard part (getting the rules right) was already done and tested
  before any Gosu is written.
- MVP's storage interface → the object-storage side (S3/Blob/GCS) is
  standard ClaimCenter document storage in production; the abstraction
  built for the MVP's local filesystem was never meant to survive into
  production anyway, only its callers' expectations (`save`/`load` by URI).

This is only true because the MVP kept AI genuinely separate and kept the
domain logic pure and framework-free. A modular monolith where AI is just
another in-process module would have blurred this line and made the
eventual ClaimCenter/Gosu port harder to scope.

## 16. Recommended Architecture

**Modular monolith for the domain (Claim, Evidence, Document metadata,
Preservation, Hold, Audit) + one standalone stateless AI service**,
talking over HTTP with a short timeout and fail-open semantics, backed by
the already-provisioned PostgreSQL `bonafide` database, with documents on
local filesystem behind a storage interface.

This is deliberately *not* a clean pick of Option A, B, or C — it is
Option A for the transactional core (Section 9 forces this) and exactly
the one seam from Option B that the production spec already mandates
(Section 3), with Option B's other two splits (Claim vs. Evidence/
Preservation) rejected as unjustified.

## 17. Why This Architecture

1. It is the only option that keeps the Section 9 transaction chain inside
   one database transaction without extra machinery (Sections 9, 14).
2. It is the only option that lets Section 8's fail-open/fail-closed
   asymmetry be *demonstrated for real* (stop the AI process, watch the
   app degrade gracefully) rather than simulated with a flag (Section 5,
   10).
3. It costs almost nothing extra over a pure monolith — one more FastAPI
   app, no gateway, no broker, no service discovery, no second database.
4. It directly rehearses the production topology (Section 15), so nothing
   built for the demo is throwaway with respect to architecture, only with
   respect to ClaimCenter-specific implementation (Gosu/PCF).
5. It is achievable in 4 days (Section 19) — the marginal complexity is
   "run two `uvicorn` processes locally," not "stand up a gateway and
   three deploy targets."

## 18. Migration Path

```
MVP (this audit)
  Modular monolith (Claim/Evidence/Doc/Preservation/Hold/Audit)
  + standalone AI service (Deterministic + optional Ollama)
  + PostgreSQL (bonafide)
  + local filesystem storage
        │
        ▼
Production v1 (Guidewire accelerator)
  ClaimCenter = source of truth (replaces the monolith's domain modules
    with Hold_Ext/EvidenceItem_Ext/PreservationLog_Ext + 4 business rules
    + 2 batch processes, Sections 4–6)
  Bona Fide AI Service = same service, same contract, containerized,
    called by Gosu BonaFideAIClient instead of the MVP's Python client
  Document storage = object storage (S3/Blob/GCS) behind the same
    storage interface contract
        │
        ▼
Large-scale production (only if actually needed)
  AI Service gets horizontal replicas behind a load balancer
    (stateless — this was always the design, Section 15)
  Classification moves off the synchronous request path into a queue/
    worker (mirrors BonaFideExpirySweep/ClassificationBatch, Section 6)
  pgvector added to the same Postgres for semantic document search,
    if RAG-style features are ever wanted (Section 17/22 in the spec)
  Full microservice decomposition of the ClaimCenter-side domain is
    still not indicated at this stage — Guidewire itself is the scaling
    unit there, not our service topology.
```

Note that MVP and production are **not** architecturally identical (the
domain layer is Python/Postgres in the MVP, Gosu/ClaimCenter in
production) — but the AI-service boundary and its contract survive the
transition unchanged, which is the piece worth protecting now.

## 19. Four-Day Implementation Plan

*(Architecture only — no code written as part of this audit.)*

**Day 1 — Domain + Postgres + preservation engine**
Schema and migrations for claims, evidence items, documents (metadata
only), holds, preservation log. `preservation_engine.py` as pure,
side-effect-free functions. Seed data: 5 synthetic claims including
CLM-10042 with the exact evidence state in Section 14 of the spec (three
unsatisfied items, all `RepairAuthorization`-triggered → HIGH risk).
Unit tests for the engine (low/medium/high risk cases).

**Day 2 — Backend API + AI service + storage**
FastAPI app exposing the endpoints in the original MVP spec, wired to the
engine inside one DB transaction per workflow step identified in Section 9.
Standalone AI service process (`/classify-document`,
`/detect-litigation-signal`, `/health`) with `DeterministicProvider`
default and `OllamaProvider` if reachable. Backend's HTTP client to the AI
service: 2s timeout, fail-open, marks `unclassified` + manual-review on any
failure. `LocalFilesystemStorage` behind the storage interface.

**Day 3 — Frontend**
Claims Dashboard, Claim Detail (evidence checklist, risk panel with
plain-language explanation, AI analysis, hold banner/confirm, preservation
timeline), Document Upload (upload or paste, shows classification +
confidence + litigation signal + recommended action), ClaimCenter Gap page.

**Day 4 — End-to-end wiring, failure rehearsal, tests, docs**
Run the full CLM-10042 demo script by hand. Deliberately kill the AI
service mid-session to confirm fail-open behavior is real, not assumed.
Confirm repair-authorization-blocked → override-with-justification →
logged, and claim-closure-blocked-while-hold-active, both work. Finish the
test suite (API tests per risk tier, AI classification incl. low-confidence
path, one full e2e test). Write/finish the docs set.

## 20. Risks

- **Demo-machine dependency on Ollama:** mitigated by `DeterministicProvider`
  as the hard default; Ollama is additive polish only, never required.
- **Two-process setup friction during the demo:** mitigate with a single
  dev script that starts both `uvicorn` processes; document exact commands
  in `SETUP.md`.
- **Scope creep toward reproducing more of ClaimCenter than intended:**
  the MVP decision in Section 12 (no Gosu, no PCF, no real ClaimCenter
  entities) needs to be re-affirmed if implementation drifts toward "let's
  also simulate batch jobs" — Section 6's batches are documented as future
  work, not built.
- **14-document doc set competing with build time on a 4-day budget:**
  flagged as an open decision below rather than silently cut.
- **Confidence-threshold tuning:** the demo's attorney-letter document
  needs to reliably clear the 0.85 threshold with whichever provider is
  active during the actual demo; worth a dry run before presenting.

## 21. Open Decisions

1. Should the two backend processes (main app, AI service) be started by
   one script/Procfile, or is running two terminal windows acceptable for
   a 4-day MVP demo?
2. Should `pgvector` be enabled now (near-zero cost, `CREATE EXTENSION
   vector` on the existing Postgres 18 instance) even though nothing uses
   it yet, or deferred until a real semantic-search feature is scoped?
3. Given the 4-day budget, is the full 14-document doc set expected by end
   of Day 4, or should a subset (PROJECT_OVERVIEW, ARCHITECTURE,
   DATA_MODEL, DEMO_SCRIPT, LIMITATIONS) ship first with the rest following
   after the working demo is confirmed?

---

## Final Recommendation

**MVP architecture:** Modular monolith for the Claim/Evidence/Document/
Preservation/Hold/Audit domain, plus one standalone stateless AI service
process, connected by HTTP with a short timeout and fail-open behavior.
This is not the full Option B from the spec (that over-splits the
transactional core) and not pure Option A (that would fake the AI
fail-open behavior instead of demonstrating it). It is the smallest
architecture that satisfies Section 8's stated asymmetry honestly.

**Production evolution target:** ClaimCenter as source of truth (Gosu
entities/rules/batches per Sections 4–6) calling the same Bona Fide AI
Service contract, unchanged, now containerized and possibly
horizontally replicated; document storage moved to object storage behind
the same interface; a queue/worker added for classification only if
volume ever pushes it off the synchronous path. Full microservice
decomposition of the domain is not on this path at any scale discussed in
this spec.
