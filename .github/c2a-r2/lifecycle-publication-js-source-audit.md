# C2A R2 lifecycle_publication.js source audit

Immutable R1 source audit against Issue #68 binding corrections.

Observed R1 defects:
- `prepareAttempt()` reads CSRF at prepare time, freezes `X-CSRFToken` in `attempt.headers`, and `performSealedAttempt()` later sends those frozen headers.
- `importValidationTicket()` again freezes current CSRF in restored `attempt.headers`.
- `downloadTicket()` immediately calls `retainTicket("download")`, unlocking POST without byte-exact retention proof.
- R1 uses one `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` shape for validation and publication.
- only validation tickets are importable; publication recovery depends on surviving in-memory `sealedAttempt`.
- no binding exists in R1 JS for corrected template controls `ticket-file-proof`, `acknowledge-ticket-file`, or `import-publication-ticket-action`.

Required correction is fully specified in `lifecycle-publication-js-execution-oracle.md` on the same recovery branch. This audit is governance evidence only; it does not modify Product code and does not count path 9/12.
