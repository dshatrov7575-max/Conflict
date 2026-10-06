# PR-35 — production PostgreSQL role separation

## Purpose

Complete the trust boundary started by PR-34. The migration/owner PostgreSQL
credential is not available to the web process. Runtime receives a separate
non-owner role with bounded DML privileges.

## Deployment graph

1. PostgreSQL starts under the migration/owner credential.
2. `migrate` runs with that credential.
3. `db-runtime-role` provisions or rotates a distinct runtime role and verifies
   its attributes and grants.
4. `web` starts only after provisioning succeeds and receives only runtime
   credentials.

The runtime role is `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
NOREPLICATION NOBYPASSRLS`, has no memberships or object ownership, has no
CREATE privilege on `public`, has no database CREATE/TEMP privilege, and cannot
UPDATE/DELETE/TRUNCATE or install triggers on `domain_auditevent`. Its
`search_path` is pinned to `pg_catalog, public`; production revokes PUBLIC
TEMP/CREATE paths so `pg_temp` cannot be used for object-shadowing. It also
cannot mutate `django_migrations`. Direct grants are reset and recalculated
after every migration; no broad default privileges are left behind for future
objects.

## Boundary

The database owner/migration credential remains a trusted administrative
authority and must not be exposed to the web runtime. PostgreSQL superusers and
database administrators remain outside the append-only threat boundary.

This PR does **not** close FD08 canonical-projection authorization. The current
PostgreSQL projection trigger still trusts the session-set custom GUC
`domain.fd08_projection_write_authorized`; a normal session can self-set that
value. That confirmed P1 remains isolated for PR-36 and must not be described as
closed by runtime-role separation.

This change does not establish scientific validity, host/SSO integration,
backup/restore readiness or a full production E2E result.
