# PR-32 — ParameterValue database metadata guard

## Purpose

Close the confirmed mismatch between `ParameterValue.clean()` and the database
boundary. A present value may be admitted only when it has either:

1. explicit numeric `confidence` plus a non-empty `rationale`; or
2. an exact inherited `ActorElementAssessment` header:
   - `LOW`, `MEDIUM`, or `HIGH` assessment confidence plus a non-empty reference statement;
     or
   - `UNKNOWN` assessment confidence, an exact two-key `POS`/`SAL` categorical
     confidence map, and a value-level rationale.

A non-null foreign key by itself is no longer sufficient.

## Database behavior

Migration `0020_parameter_value_db_metadata_guard` installs fail-closed INSERT
and UPDATE triggers on SQLite and PostgreSQL. It also verifies existing rows,
rejects cross-workspace/time-slice/assessment-set header references, and blocks
later assessment-header or parameter-code updates that would invalidate an
already admitted inherited value.

The migration does not change Calculation Core, formulas, statuses, scientific
admission, HUMAN/AI lanes or historical results.

## Tests

The focused regression surface bypasses `full_clean()` deliberately and proves
that the database:

- rejects an incomplete inherited header;
- rejects a cross-context assessment header even with explicit value metadata;
- accepts explicit confidence plus rationale;
- accepts a complete inherited assessment header;
- accepts only an exact POS/SAL categorical confidence map;
- blocks a raw UPDATE that removes required metadata;
- blocks an assessment-header UPDATE that invalidates inherited metadata;
- rejects an unrecognized assessment-confidence token; and
- blocks a parameter-definition code UPDATE that invalidates categorical metadata.

## Boundaries

This closes one data-integrity finding only. It does not close the separate
least-privilege PostgreSQL role / FD08 projection-authority issue, generic-case
coupling, host/SSO integration, deployment operations or scientific validity.
