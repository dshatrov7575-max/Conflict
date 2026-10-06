# Zhanaozen 2011 technical-failure retry protocol V1

**Protocol freeze only. No network access or retry execution occurred in PR-20.**

## Scope

The exact-edition consolidation contains 54 frozen query attempts. Only four archive-route attempts are technical failures and may receive one future technical retry each:

- 2 × `INITIAL_ARCHIVE_QUERY_FAILURE`;
- 2 × `REPLAY_AFTER_CANDIDATE_FAILURE`.

The other 50 attempts are explicitly ineligible: 35 completed nonadmissible and 15 finite no-result. They cannot be rerun merely to seek a more favorable result.

## Frozen identity

- base: `127f682beba758be36d07ce6ee8a7e8166ecd72d`;
- tree: `7aa4d2a022e99496ae64ee6a7941a00d52e8386c`;
- protocol ID: `6384e953-8c88-58e2-ac31-cc9ee18ee6d1`;
- case ID: `292d238f-9fee-578f-bddd-6f923163788a`;
- target cutoff: `2011-12-15T23:59:59Z`;
- future retry IDs: deterministic UUIDv5 values bound to the four immutable failed attempt IDs.

## Retry semantics

An initial archive-query failure may repeat the exact frozen CDX locator once. If that exact response yields candidates, the same execution may choose only the latest candidate at or before cutoff and issue one replay request.

A replay-after-candidate failure may not repeat CDX discovery. It may retry only the already selected latest pre-cutoff replay URL. It may not switch to an older candidate, mirror, publisher route, changed URL or expanded query.

No automatic client retry is permitted. One protocol retry ID equals one future execution. Any second attempt is forbidden.

## Deterministic technical contract

- HTTP GET;
- connect timeout 15 seconds;
- read timeout 45 seconds;
- maximum 5 redirects;
- TLS verification enabled;
- no library retry adapter;
- fixed User-Agent;
- exact cutoff and fields;
- exact logging of URL, redirects, status, type, byte count, hashes and errors;
- no response body or full article text stored in Git.

## Fail-closed scientific rule

A technically successful response does not prove `EXACT_EDITION`. Exact admission still requires the complete frozen exact-edition contract and exact binding to the DocumentVersion. Until a separate admission task proves every gate, all four states remain `NOT_PROVEN`, Mapping remains unchanged, target time remains `UNKNOWN`, and carry-forward remains forbidden.

## Boundaries

No factor value, anchor, HUMAN response, HistoricalAssessment, ValidationRecord, outcome classification, UNO, probability, risk, country rating, publication, release or deployment is created. Future execution is forbidden until a separate explicit task is authorized after independent validation of this protocol.
