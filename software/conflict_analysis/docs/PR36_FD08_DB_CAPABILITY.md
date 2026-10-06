# PR-36 — FD08 PostgreSQL projection capability

## Purpose

Close the confirmed FD08 PostgreSQL authority bypass left explicit by PR-35.
The previous database triggers trusted the custom session setting
`domain.fd08_projection_write_authorized=1`. Any client holding ordinary
runtime database credentials could set that custom GUC itself, so the database
could not distinguish the canonical projection service from arbitrary SQL.

## Change

PostgreSQL projection authority now uses a transaction-local capability instead
of a boolean flag.

- the application presents `domain.fd08_projection_write_capability` only
  inside the canonical projection context;
- migration `0022_fd08_projection_capability` stores the authoritative
  capability in an owner-controlled singleton table;
- FD08 trigger functions are `SECURITY DEFINER`, use a pinned
  `pg_catalog, public` search path, and authorize only an exact match between
  the transaction-local capability and the protected database value;
- PUBLIC receives no access to the capability table;
- the production runtime role receives no SELECT/INSERT/UPDATE/DELETE/TRUNCATE/
  REFERENCES/TRIGGER privileges on that table;
- production requires `FD08_PROJECTION_LEASE_SECRET` and rejects the
  development placeholder;
- runtime-role provisioning rotates the protected database value to the exact
  deployment capability after migrations.

The old boolean GUC no longer grants authority. An arbitrary value placed in the
new capability GUC also grants no authority.

## Verification

The focused database tests prove:

- a direct canonical INSERT without the private projection context is rejected;
- `domain.fd08_projection_write_authorized=1` does not authorize a canonical
  INSERT or workspace projection-evidence update;
- an attacker-controlled value in
  `domain.fd08_projection_write_capability` does not authorize either path;
- the canonical projection context continues to create the deterministic
  projection successfully;
- the runtime role cannot read or mutate the protected capability table;
- the existing runtime least-privilege contract remains intact;
- Django TransactionTestCase teardown restores the currently applied 0022
  capability generation after flush instead of silently reinstalling the
  superseded 0019 boolean-GUC functions, and repopulates the protected singleton
  erased by flush.

SQLite retains its process-local ContextVar-backed guard and does not use the
PostgreSQL capability table.

## Boundary

This closes the specific raw-runtime-DB-session self-authorization bypass. The
capability is also present in the application process environment because the
canonical projection service must use it. Compromise of the trusted application
process, migration/database-owner credential, or PostgreSQL superuser remains
outside this database-credential threat boundary.

Deployments must generate an independent random capability of at least 32
characters. It must not be reused as the Django secret or either PostgreSQL
password.

This PR does not change Calculation Core, formulas, HUMAN/AI isolation,
scientific admission, historical results or scientific claims.
