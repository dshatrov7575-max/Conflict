# Zhanaozen 2011 — source/context recovery protocol freeze

**AI preparation only. Protocol and empty ledger freeze; no retrieval or substantive review executed.**

Base: `c48e3730cc9a7c67d62429614e1ca9e5c58be920`. Plan: `ZHANAOZEN_2011_RECOVERY_PROTOCOL_V1`. All 53 PR-14 blocker units are frozen before execution.
The protocol preserves BLOCKED, NOT_REVIEWED, UNKNOWN, NOT_PROVEN, and DISPUTED exactly unless a later separately frozen review satisfies the corresponding contract.

## Scope and hard stop

This package defines only allowed recovery routes, prospective queries, custody requirements, deterministic stopping, error semantics, and retention/supersession rules.
Network search: NOT_EXECUTED. Substantive source review: NOT_EXECUTED. HUMAN coding: NOT_PERFORMED. Historical area UNO: NOT_COMPUTED / BLOCKED.
No factor values, numeric anchors, scoring, weights, outcomes, HistoricalAssessment, ValidationRecord, prediction, probability, risk, or country rating are created.
The superseded company KVS=5 / Pol=50 is not restored.

## Frozen blocker inventory

The plan contains 53 immutable blocker units and 160 prospective query records across seven allowed routes.
Each blocker retains its PR-14 ID, affected IDs, prior status, missing-proof statement, forbidden shortcuts, source JSON Pointer, and canonical source-entry SHA-256.
No attempt may begin until the plan, ledger, validator, receipt, and manifest are committed as one immutable version.

## Allowed routes

### `ROUTE_ACTOR_MANDATE_OR_REPRESENTATION`

Establish whether an observed speaker or organization represents the exact frozen actor group for the issue and time at hand.
Evidence contract: Bind the represented group, representative, authority source, issue scope, temporal scope, and any limits or revocation.
Success: Representation of the exact frozen actor group is explicit, source-bound, issue-specific, and valid for the relevant time.
Failure: Retain UNKNOWN_GROUP_REPRESENTATION; title, employment, participation, or affiliation alone is insufficient.
Forbidden inference: person represents group by participation; company represents all employers; organ represents aggregate authority group without mandate.

### `ROUTE_AUTHENTICATED_FRAGMENT_WITNESS`

Authenticate a frozen exact fragment without claiming the full historical edition.
Evidence contract: Record exact fragment bytes, fragment SHA-256, archive capture timestamp, payload digest, literal-match result, and source locator.
Success: The exact frozen fragment is literally present in an authenticated pre-cutoff payload; claim scope remains FRAGMENT only.
Failure: Retain NOT_PROVEN for that fragment and retain full-edition NOT_PROVEN in all cases.
Forbidden inference: fragment witness authenticates every fragment; fragment witness authenticates the full edition; similar wording is an exact match.

### `ROUTE_CONTEXT_ATTRIBUTION_LANGUAGE`

Recover enough context to identify speaker, attribution, modality, actor scope, reference scope, and original-language meaning.
Evidence contract: Preserve original bytes, language, speaker, quotation boundary, modality, surrounding context, translation author/status, and custody hashes.
Success: The exact fragment is attributable, context-complete for the proposed mapping, and linguistically interpretable without invented speaker or scope.
Failure: Retain the inherited BLOCKED or NOT_REVIEWED state; AI translation candidates are not HUMAN-certified.
Forbidden inference: short excerpt supplies missing speaker; AI translation is human validation; journalist voice equals actor voice.

### `ROUTE_COUNTEREVIDENCE_REVIEW`

Review all preserved DISPUTED, unlinked, and possible counterevidence facts without deletion or convenient selection.
Evidence contract: Retain original fact status and IDs; record every linkage decision, exclusion reason, conflicting source, and search-limit statement.
Success: All preserved counterevidence units are explicitly reviewed under frozen rules, and any direct resolution is source-bound and separately frozen.
Failure: Retain DISPUTED, unlinked, and completeness-UNKNOWN states; absence of a found source is not proof of absence.
Forbidden inference: unlinked means irrelevant; no search hit proves absence; conflicts may be averaged or silently selected.

### `ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION`

Recover an authenticated complete pre-cutoff edition bound to the frozen DocumentVersion identity.
Evidence contract: Preserve capture timestamp, locator, retrieved bytes, SHA-256, content type, redirect chain, and exact binding to the frozen DocumentVersion.
Success: Complete edition bytes are authenticated at or before cutoff and match the frozen edition identity without rebinding.
Failure: Retain NOT_PROVEN and every prior blocker; a current page, publication date, metadata, or late copy is insufficient.
Forbidden inference: fragment proof implies full-edition proof; current content equals historical edition; publication date proves archived availability.

### `ROUTE_REFERENCE_COMPONENT_COVERAGE`

Test evidence coverage against every component of the unchanged frozen reference statement.
Evidence contract: Preserve exact reference text and SHA-256; identify each component, supporting chain, uncovered component, and conflicting evidence.
Success: Every essential reference component is explicitly covered for the same actor and time without rewriting or narrowing the reference.
Failure: Retain UNKNOWN_FULL_REFERENCE_COVERAGE when any essential component remains uncovered or disputed.
Forbidden inference: one component implies whole reference; reference may be narrowed after evidence review; different actors or dates may be silently combined.

### `ROUTE_TARGET_TIME_APPLICABILITY`

Establish applicability at the frozen target time without automatic carry-forward.
Evidence contract: Record observation time, asserted duration, actor/reference identity, source edition status, and any superseding or contradictory statement.
Success: An admissible source directly covers target time or explicitly covers the full gap with no superseding evidence.
Failure: Retain UNKNOWN_NO_CARRY_FORWARD; the last earlier message is never carried forward automatically.
Forbidden inference: last observation persists to cutoff; publication date establishes target state; silence establishes continuity.

## Edition proof versus fragment proof

A pre-cutoff exact-fragment witness proves only that exact frozen fragment in that payload. It never authenticates the complete historical edition, another fragment, or the late-captured DocumentVersion bytes.
Full-edition proof requires immutable pre-cutoff capture identity, retrieved bytes, custody hashes, locator history, and exact binding to the frozen DocumentVersion. Publication date, current URL, PDF metadata, and late snapshots are not substitutes.

## Representation, reference, target time, and language

A person, subgroup, company, or organ does not represent the aggregate actor group without a source-bound mandate whose issue and temporal scope are explicit.
Evidence about one component does not cover a composite reference statement. The frozen reference text and hash cannot be narrowed after evidence review.
No message is automatically carried into 2011-11-28..2011-12-15 or the frozen target time. Silence and absence of a later found source do not establish persistence.
Speaker, attribution, modality, surrounding context, original language, and translation status must be preserved. AI translation candidates are not HUMAN-certified.

## Counterevidence and negative evidence

All DISPUTED and unlinked facts remain visible. Every inclusion or exclusion decision requires provenance; averaging, deletion, and convenient selection are forbidden.
Timeouts, transport errors, parser errors, and finite searches with no result retain the exact prior state. They do not prove non-existence or absence.
Repository records cannot prove the absence of hidden external attempts; future service receipts must be recorded when available.

## Deterministic attempts and stopping

Attempt IDs use UUID5 over plan ID, blocker ID, route ID, query ordinal, and query-text SHA-256. Query order is frozen by blocker order, route order, and template order.
Each frozen query may have one substantive attempt. Stop on the first admissibility-contract satisfaction or when allowed routes are exhausted. Additional queries require a new version frozen before execution.
Rerun-until-favorable, post-result expansion of the attempt budget, deletion, overwrite, or renumbering of attempts is forbidden.

## Custody and deduplication

Store query hash, request/completion times, locator and redirects, retrieved byte count, SHA-256, capture timestamp, content type, duplicate relation, contract result, retained prior status, and notes.
Hash retrieved bytes without normalization. Same digest/capture/locator is a duplicate, not independent corroboration. Multiple URLs do not establish source independence.

## State retention and future supersession

BLOCKED remains until every relevant success contract passes in a new frozen review. NOT_REVIEWED remains until explicit review. UNKNOWN and NOT_PROVEN remain unless direct admissible evidence resolves the exact unit.
DISPUTED is preserved unless directly resolved by source-bound evidence; it is never averaged away. Supersession requires a new version, immutable inputs and attempt-ledger hashes, and explicit old-to-new state mapping before HUMAN coding.

## Execution boundary

This version ends before retrieval. The empty ledger is prospective and does not prove future executor compliance. Any executed recovery must produce a new append-only ledger and a separately frozen admission decision.
Publication, release, deployment, merge, HUMAN coding, adjudication, and Calculation Core execution are outside this protocol freeze.

## Reproduction

Run `validate_recovery_protocol.py` from the repository root with Python 3.10+ and jsonschema installed. The validator replays PR-14 in an isolated detached worktree, verifies all base blobs and pins, checks all 53 units and 160 planned queries, and fails closed on scope or state drift.
