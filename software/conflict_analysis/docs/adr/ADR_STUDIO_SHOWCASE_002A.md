# ADR_STUDIO_SHOWCASE_002A: presentation-only Studio session

- Status: accepted for the Issue #64 showcase lane
- Date: 2026-08-25
- Task: `CA-SUITE-I1-STUDIO-SHOWCASE-002A`
- Base: `codex/ca-suite-i1-foundation` at
  `eaee9227c5c43ea18ef3c3ea7a2b9d70fb5910bf`

## Context

The production Studio authoring/publication contract is not yet authorized.
Issue #64 nevertheless authorizes a runnable partner-safe interface that can
demonstrate editing a project structure without pretending to publish,
validate, calculate, predict, or persist an authoritative project.

The showcase therefore needs its own composition entry point, but it must not
create a second domain model, publisher, package authority, audit workspace, or
production data path.

## Decision

The Studio showcase is a server-rendered Django application with small,
dependency-free JavaScript interactions. It is composed only by
`conflict_analysis.studio_showcase_settings` and
`conflict_analysis.studio_showcase_urls`; the normal product composition root
does not include it.

The showcase data contract is the explicitly labelled, versioned
`SHOWCASE_SESSION_V1` JSON view-model. Project structure edits remain in the
current browser page. Opening, cloning, importing, exporting, previewing, and
validating operate only on this view-model. Import validation is non-mutating,
and export creates a user-directed JSON download. This format is not a
Foundation package and is never accepted as one.

Only versioned UI preferences (panel widths and the active right-hand tab) may
be stored in `localStorage`. Project/session content, evidence content, and
publication state must never be stored there. Missing, malformed, or
out-of-range preferences reset to the safe default layout.

The showcase settings replace the database connection with an in-memory
SQLite database solely to give Django a complete system-check configuration.
Showcase views and validation helpers make no ORM calls. Starting the showcase
requires no migration and writes neither the Foundation ORM nor a production
database.

Publication cannot report a fabricated success. It is disabled, or limited to
an explicitly non-mutating preview with an explanation that the production
authoring/publication contract is absent.

The right-hand evidence trace is a static, non-numeric demonstration of the
canonical direction:

`Assessment -> Fact -> Fragment -> DocumentVersion -> Source`

It does not create or alter evidence records. Chat remains disabled until a
separate provider/RAG gate. Help pages are local, versioned presentation
content.

## Hard boundaries

- Session-only and presentation-only; no authoritative state or production
  readiness claim.
- No ORM models, migrations, production database writes, second publisher,
  alternative package authority, or fake audit workspace.
- No input, editing, calculation, or persistence of `TimeSlice`, `Assessment`,
  `POS`, or `SAL`; `Assessment` appears only as the first label in the static
  evidence-trace fixture. No scalar Power/`POW`, Power aggregation, formulas,
  Calculation Core, automatic weights, or `POW x SAL`.
- No prediction, risk score, early warning, scenario/modeling engine,
  recommendation, ranking, or decision automation.
- No OCR, live LLM, live RAG, provider integration, merge, or release.
- The showcase must not change Foundation service or package semantics.

If a future UI requirement needs any of these capabilities, implementation
stops with `SHOWCASE_SCOPE_CONFLICT` until an independent production contract
is accepted.

## Verification

CI keeps the existing Foundation PostgreSQL 18 and SQLite gates and adds a
focused showcase composition check plus the `test_studio_showcase_*.py` suite.
Tests cover arbitrary `6x8` and `3x4` cardinalities, validation diagnostics,
session import/export behavior, absence of ORM writes, layout restore/reset,
keyboard/accessibility smoke, and forbidden claims.

The local entry point is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_studio_showcase.ps1
```

It selects a local `.venv` Python first and falls back to `py -3.12`, sets the
isolated showcase settings, and starts the server without running migrations.

## Consequences

The partner can interact with a real UI and exchange a clearly marked JSON
session, while refresh/restart recovery, multi-user collaboration,
authoritative persistence, publication, and scientific validation remain
intentionally unavailable. Production Studio work still requires its separate
accepted contract.
