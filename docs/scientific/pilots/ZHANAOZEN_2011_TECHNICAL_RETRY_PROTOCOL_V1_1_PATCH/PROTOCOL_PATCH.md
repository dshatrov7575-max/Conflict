# Technical retry protocol V1.1 budget clarification

**Patch only. No network access or retry execution occurred.**

## Why this patch exists

V1 correctly froze four logical retry IDs and the per-unit execution stages, but the field `total_maximum_future_http_attempts: 4` was misnamed and conflicts with those stages. An initial CDX failure can require two HTTP subrequests inside one logical retry execution: the exact CDX lookup and, only if candidates are returned, one deterministic replay. A replay-after-candidate failure requires one replay subrequest.

Therefore the maximum is:

- four logical retry executions total;
- one execution per retry ID;
- two initial-failure units × at most two subrequests = four;
- two replay-failure units × one subrequest = two;
- **maximum six HTTP subrequests total**;
- zero automatic library retries;
- zero query expansion or extra subrequests beyond the frozen stage.

## Supersession

Only the V1 field `future_retry_budget.total_maximum_future_http_attempts` is deprecated. All exact query, locator, candidate, timeout, custody, stop, NOT_PROVEN, Mapping, target-time and no-carry-forward rules remain unchanged.

Future execution must read V1 together with this V1.1 patch. Execution based on V1 alone is forbidden.

## Scientific boundaries

This patch changes no scientific state. It creates no factor value, HUMAN response, HistoricalAssessment, ValidationRecord, UNO, prediction, probability, risk, country rating, publication, release or deployment.
