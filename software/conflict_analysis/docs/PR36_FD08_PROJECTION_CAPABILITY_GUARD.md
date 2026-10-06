# PR-36 — FD08 PostgreSQL projection capability guard

## Purpose

Close the confirmed P1 in the PostgreSQL FD08 projection guard. The previous
trigger trusted the session-set boolean-like GUC
`domain.fd08_projection_write_authorized=1`, which any ordinary database
session could set for itself.

## Change

PostgreSQL now authorizes the bounded FD08 projection lease only when the
transaction-local capability value matches the server-side capability stored in
`domain_fd08_projection_capability`.

The capability table is owned by the migration authority and is inaccessible to
the production runtime role. Runtime provisioning rotates/upserts the capability
after migrations, then revokes all table access from the runtime role.

Production requires a separate `FD08_PROJECTION_CAPABILITY_TOKEN` of at least
32 characters. The service context sets that token transaction-locally; it is
not a database credential and is not readable through the runtime database
role.

For trusted owner/dev/test databases with no configured capability, the private
service context may initialize the capability row. Raw SQL outside that context
remains unauthorized.

## Regression evidence

PostgreSQL 18 targeted:
- runtime-role authorization boundary;
- direct raw canonical insert rejection;
- workspace projection evidence guard;
- explicit proof that setting the legacy value `1` does not authorize;
- correct capability authorizes the helper;
- runtime role cannot SELECT the capability table.

Result: 3 passed / 0 failed.

Portable/production targeted:
- migration graph / makemigrations check;
- production settings/runtime checks;
- FD08 database guard tests.

Result: 8 passed / 14 intentionally deselected / 0 failed.

## Boundaries

This closes the self-set custom-GUC projection-authority bypass. It does not
expand scientific claims, change Calculation Core/formulas, or establish
external SSO, backup/restore or observability readiness.
