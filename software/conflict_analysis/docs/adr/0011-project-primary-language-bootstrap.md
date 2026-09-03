# ADR 0011: Project primary-language bootstrap

- Status: accepted implementation contract
- Scope: `CA-SUITE-I1-PROJECT-LANGUAGE-BOOTSTRAP-F0L-001`
- Base: `710b88f0db9ec2f0e2fae65c7e0c77025115771a`
- Decision source: OD-0031 and the accepted F0L G0

## Context

Foundation did not persist one authoritative primary language for a Project. The
atomic first-project bootstrap, the clean-database demo seed, project packages,
and the real Production Studio caller could consequently create the same
Project identity without a stable language. Multilingual evidence and the
lifecycle/publication product slice both depend on that identity, so they stay
blocked until this prerequisite is independently accepted.

This ADR does not authorize evidence lineage, translation alignment,
FactCategory, drilldown, lifecycle/publication behavior, Monitoring,
calculation, Power aggregation, prediction, ranking, or recommendations.

## Decision

### Language tags

Foundation owns one deterministic RFC 5646 well-formedness parser and
canonicalizer. It recognizes langtag, grandfathered, and private-use forms; it
does not claim IANA registration checks or preferred-value replacement.
Canonical tags are at most 255 characters. Language, extlang, variant,
extension, and private-use subtags are lower case; script is title case;
alphabetic region is upper case; numeric region is unchanged. Underscores,
whitespace, empty or misordered subtags, oversized subtags, duplicate variants
or singletons, and free text fail closed.

`und` is syntactically valid. Ordinary Project creation nevertheless rejects it;
it is reserved for an explicit restored/migrated legacy-unknown identity.

### Persisted Project identity

Project persists the immutable pair:

```text
EXPLICIT       -> canonical primary_language_tag != und
LEGACY_UNKNOWN -> primary_language_tag == und
```

The pair is protected by model and database constraints. Instance saves,
`save(update_fields=...)`, queryset updates, bulk updates, create/get-or-create,
update-or-create, and bulk-create/conflict modes cannot omit, forge, or change
the pair. Other Project fields retain their existing mutability and deletion
semantics.

The sole production entry point for a legacy-unknown insert is
`Project.objects.restore_legacy_unknown_from_package(...)`. It accepts only a
schema- and checksum-validated project-package 1.1 identity, performs one
insert into an empty target identity, and cannot update an existing Project.
Its sole production caller is the project-package service. There is no generic
context flag, metadata flag, raw-SQL path, or alternate manager bypass.

### Migration and seed

`domain.0016_project_primary_language` depends only on
`0015_foundation_studio_contract_constraints`. The exact Project UUID
`3de70d1d-f4cf-535a-95b9-94c0a65e60e3` together with code
`KZ-ZHANAOZEN-DEMO` becomes `ru + EXPLICIT`; every other pre-existing Project
becomes `und + LEGACY_UNKNOWN`. No Kyrgyzstan or Uzbekistan Project identity is
guessed. Reverse-to-0015 and reapplication are deterministic and do not change
unrelated identities, hashes, values, or links.

On a clean migrated database, the Zhanaozen seed creates and replays the same
Project as `ru + EXPLICIT`. A pre-existing matching identity with a different
language fails without rewriting it.

### Project packages

Project-package 1.0.0 bytes remain frozen. Version 1.1.0 requires
`primary_language_tag` and `primary_language_assignment`, includes both fields
in its checksum, and is the current export format. The exact KZ 1.0 identity is
upgraded deterministically to `ru + EXPLICIT`; all other 1.0 imports fail with
`PROJECT_PACKAGE_PRIMARY_LANGUAGE_REQUIRED` until an explicit bounded upgrade
supplies either non-`und + EXPLICIT` or exactly `und + LEGACY_UNKNOWN`.
Foundation-package 2.x remains unchanged because it addresses an already
existing Project.

### Atomic bootstrap and Product caller

The bootstrap envelope requires the top-level member
`project_primary_language`. Assignment state is never accepted from the
request. Missing, malformed, and runtime-`und` values are rejected before any
Project, Group, Definition, or Audit write. The canonical tag and its
`EXPLICIT` assignment are returned in the service result, immutable receipt,
and HTTP response.

`BOOTSTRAP_DRAFT` uses semantic request identity V2: first-attempt raw byte
provenance is retained, while replay comparison uses the canonical envelope
hash including the canonical tag. Case-only equivalents replay the original
immutable receipt; a genuinely different language under the same operation
key is `WRITE_OPERATION_KEY_REUSED`. Other HUMAN operations retain V1 identity.

Production Studio presents an empty required language input with Russian
examples and no preselected language. Client validation/canonicalization occurs
before the immutable attempt is prepared. Existing CSRF, receipt, storage,
no-auto-retry, and unavailable-function boundaries are unchanged.

### Delivery and successors

The corrected F0L delivery is exactly 26 paths. Its workflow/verifier enforce
the exact FD07 base, 22 existing base blobs, four new paths, frozen objects, the
line-bounded `en + EXPLICIT` delta in three required-suite fixtures, one
ordinary merge-free commit, the fixed test registries, the package-restore
caller registry, and positive/negative self-checks.

Future F1 and C2A routes are declarations only. Each must use externally
accepted `F0L_ACCEPTED_HEAD` and `F0L_ACCEPTED_TREE` pins and a fresh branch from
that exact commit. F1 owns its frozen nine-path evidence scope; C2A retains its
frozen 17-path lifecycle/publication scope. Missing, partial, malformed, or
mismatched pins fail closed. This ADR grants neither successor code authority.

## Consequences

- Project language becomes a stable, auditable prerequisite instead of an
  inferred locale.
- Unknown legacy meaning stays explicit and cannot enter ordinary runtime
  creation.
- Package restore is possible without opening a general ORM bypass.
- Case-only tag changes do not create false bootstrap conflicts.
- F1 and C2A remain blocked until MAIN independently accepts the exact F0L
  delivery HEAD/TREE.

Merge, release, rebase, cherry-pick, and force-push are outside this decision.
