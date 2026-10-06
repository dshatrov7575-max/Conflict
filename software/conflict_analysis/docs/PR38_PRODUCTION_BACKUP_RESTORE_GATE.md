# PR-38 — production backup/restore gate

## Purpose

Add a fail-closed disaster-recovery acceptance path to the production CI gate.
The production profile must prove that a database backup can be restored into a
fresh database and that the restored application remains migration-clean and
least-privilege compatible.

## Gate

While the exact production Compose stack is running, CI:

1. creates a deterministic application sentinel through the running web service;
2. creates a PostgreSQL custom-format dump with the migration role;
3. computes dump size and SHA-256 locally;
4. creates a fresh restore database owned by the migration role;
5. restores the dump with no owner/grant replay;
6. requires `django migrate --check` to pass against the restored database;
7. reapplies the canonical runtime-role provisioning to the restored database;
8. verifies the sentinel exists exactly once;
9. runs the production DB-authority probe against the restored database;
10. deletes the raw dump before artifact upload.

The raw dump is deliberately **not** uploaded as an artifact because it contains
application data and the protected FD08 capability value. CI uploads only
machine-readable non-secret evidence: dump SHA-256, byte count, restore database
identity, sentinel identity and DB-authority results.

## Restore authority

The restored runtime connection must retain the same fail-closed boundary:

- no database TEMP privilege;
- no runtime object/schema ownership;
- no FD08 capability-table privileges;
- no AuditEvent UPDATE/DELETE/TRUNCATE/TRIGGER;
- no migration-table mutation;
- no sequence UPDATE / `setval`.

## Boundary

This proves backup/restore mechanics for the repository's pinned PostgreSQL 18
production graph in ephemeral CI. It does not by itself prove:

- retention policy;
- off-host or geographically separate backup storage;
- encryption-key custody;
- scheduled backup execution;
- recovery-point objective or recovery-time objective in a real deployment;
- external-host rollback orchestration;
- host/SSO integration.

Scientific validity, HUMAN reliability, historical admission, historical area
UNO and predictive/probability/risk validity remain outside this PR.
