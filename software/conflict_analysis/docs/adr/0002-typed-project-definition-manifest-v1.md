# ADR 0002: Typed project-definition manifest V1

Status: accepted for `FOUNDATION-STUDIO-CONTRACT-ADDENDUM-001`

## Context

Studio must author a project before a workspace exists. The existing Foundation
already has the versioned aggregate and lifecycle owner:
`ProjectDefinitionVersion.manifest`. Creating Studio-specific actor, element,
parameter, draft, or publication records would establish a competing domain
authority and make later workspace pins ambiguous.

Historical Foundation 2.0 packages and non-typed definition manifests also have
established checksum semantics. A new canonicalizer must not silently alter
those bytes.

## Decision

`ProjectDefinitionVersion.manifest` remains the sole persisted definition
aggregate. Typed input is recognized only by this exact envelope:

```text
$schema       = https://conflictology.invalid/schemas/project-definition-manifest-1.0.0.schema.json
format        = conflict-analysis-project-definition
format_version = 1.0.0
```

The schema contains the exact Project identity and snapshot descriptions,
structure-lock policy, stable actors and analytical elements, cross-reference
roles, parameter definitions and exact Studio HelpTopic references. Structural
identities are UUIDs. Codes and sibling orders are controlled locally;
hierarchies must be acyclic and all references must resolve inside the same
manifest. Cardinality is unrestricted: the deterministic contract vectors
include both 3×4 and 6×8 definitions but neither is a domain limit.

Manifest `project.id`, `project.code`, and `project.version` must match the
persisted Project exactly. Descriptive values are immutable snapshot bytes.
Creating, saving, validating, or publishing a definition never copies those
descriptions into the mutable Project row.

Typed V1 canonical bytes are UTF-8 without BOM or terminal newline, with
recursively sorted object keys, compact separators, `ensure_ascii=false`, and
array order preserved. NaN and Infinity are forbidden. Values are neither
trimmed, case-folded, Unicode-normalized, defaulted, nor reordered. The manifest
hash is lowercase SHA-256 over those exact bytes. Controlled decimal scales are
strings so runtimes cannot introduce binary-float serialization differences.

Validation returns an immutable
`PROJECT_DEFINITION_MANIFEST_VALIDATION_V1` object with schema identity, exact
hash, validity, and complete ordered diagnostics. Diagnostic codes and JSON
pointers are stable; library-specific schema messages are not exposed as the
contract. DRAFT storage requires an exact envelope, JSON/schema shape, exact
Project identity, and absence of forbidden aggregate fields. Semantic problems
such as a broken parent may remain as deterministic DRAFT diagnostics but block
validation/publication.

The canonical DRAFT service exposes create, open, clone, and optimistic save.
Every operation requires a server-side Studio capability. Save locks the row
and requires the exact prior manifest hash. Clone creates a new DRAFT successor
and never modifies the source. Validated and published bytes remain immutable
and can be changed only through a successor definition.

All public manifest and Foundation 2.1 JSON ingress uses the shared bounded
raw-byte parser before DRF or a package adapter materializes a mapping. The
transport contract is `application/json` with no charset or the exact
`charset=utf-8`, with a 2 MiB byte budget. It rejects a UTF-8 BOM, invalid
UTF-8, duplicate keys at any depth, NaN/Infinity, a second/trailing JSON
document and a non-object root without echoing input bytes. File `Path`, byte,
UTF-8 text and explicitly identified canonical-mapping adapters all route
through this same parser; only the transport identity kind differs.

Public DRAFT save accepts exactly one strong validator form:

```http
If-Match: "<64 lowercase hexadecimal manifest SHA-256>"
```

Missing, weak (`W/`), wildcard, unquoted, uppercase, multiple or malformed
validators fail before body materialization and cannot be replaced by a body,
query or custom-header hash. The service then repeats the stale-hash comparison
against the locked persisted row.

Help bindings carry exact application, UI key, locale, topic stable key,
version, and sanitized-content checksum. Binding version and topic version must
match. Publication-grade validation supplies the shared exact HelpTopic
resolver; the manifest layer does not create a parallel help registry.

Formulae, scalar or total Power, POW, POW×SAL, calculated risk, prediction, and
recommendation keys are outside this schema and fail closed.

## Compatibility

Typed-vs-legacy dispatch is explicit. The V1 parser, canonicalizer, and hash
functions reject any input without the complete exact envelope. Existing
non-typed manifests, Foundation 2.0 packages, V1 compatibility input, and
append-only receipts retain their historical bytes and checksums. Conversion
to typed V1 is an explicit successor operation with new provenance; it is never
an implicit read or migration.

## Consequences

- Studio can edit arbitrary definition cardinalities before a workspace exists
  without domain-table duplication.
- Workspace materialization can later consume one exact published definition ID
  and hash.
- Stable diagnostics and deterministic vectors are reusable by service, HTTP,
  package, PostgreSQL, and SQLite gates.
- The typed schema can be referenced by Foundation package 2.1 without changing
  the Foundation 2.0 validator or checksum path.
