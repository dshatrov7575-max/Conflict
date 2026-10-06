# PR-34 — PostgreSQL AuditEvent DB immutability

## Purpose

Close the concrete gap demonstrated by the receipt tamper test: ORM-level
immutability and drift detection did not prevent a direct SQL UPDATE of
`domain_auditevent`.

## Change

Migration `0021_audit_event_db_immutability` installs a PostgreSQL trigger that
rejects every UPDATE and DELETE affecting `AuditEvent`. INSERT remains allowed.
TRUNCATE is intentionally deferred to the separate least-privilege runtime-role
layer: Django's PostgreSQL test isolation legitimately uses TRUNCATE while the
production web role must not receive that privilege.

SQLite remains unchanged. Production settings already reject SQLite; the
portable SQLite lane continues to exercise ORM immutability and receipt
drift-detection behavior.

## Claim boundary

This PR alone is **PARTIAL**, not a complete append-only trust boundary.

A PostgreSQL table owner or superuser can alter/drop triggers. The production
Compose profile currently uses the same PostgreSQL credentials for migration
and web runtime. A separate follow-up must split migration/owner authority from
the runtime role and verify runtime grants before the project may claim
database-enforced append-only audit integrity.

Calculation Core, formulas, scientific admission, HUMAN/AI isolation and
historical results are unchanged.
