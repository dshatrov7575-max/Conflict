# PR-37 — production Compose end-to-end gate

## Purpose

Turn the production profile from a static/image contract into an executable CI
contract. The required gate must prove that the exact production graph can start:

`db -> migrate -> db-runtime-role -> web`.

## Gate

The production-image job now:

1. builds the locked production image;
2. starts the production Compose graph with `--no-build`;
3. requires the database, migrations, runtime-role provisioning and web
   healthcheck to complete successfully;
4. verifies the public HTTP boundary:
   - plain HTTP redirects to HTTPS;
   - an HTTPS-proxy-marked unauthenticated Player request returns 401;
5. executes `conflict_analysis.production_db_probe` inside the running web
   container and verifies that the live database session is the bounded
   `conflict_runtime` role;
6. captures Compose status, logs, HTTP evidence and DB-authority evidence as CI
   artifacts;
7. tears the ephemeral stack and volume down even on failure.

## Runtime authority assertions

The live web session must prove:

- it is not database or AuditEvent owner;
- it has no role memberships;
- it owns no application relations or schemas;
- it cannot CREATE in `public`;
- migration credentials are absent from the web environment;
- it can SELECT/INSERT AuditEvent rows but cannot
  UPDATE/DELETE/TRUNCATE/TRIGGER them;
- it cannot mutate `django_migrations`;
- it has no sequence UPDATE / `setval` authority.

The probe is required to be present in the built application wheel.

## Boundary

This gate proves the repository's production Compose graph on the pinned
GitHub-hosted Linux runner and pinned PostgreSQL/image dependencies. It does not
prove a particular external host, reverse proxy, SSO provider, backup system,
monitoring stack or rollback procedure.

Scientific validation, HUMAN reliability, historical admission, historical
area UNO and predictive/probability/risk validity remain outside this PR.
