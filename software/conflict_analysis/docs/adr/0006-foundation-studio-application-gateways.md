# ADR 0006: Foundation Studio application gateways

- Status: accepted for the bounded Foundation dependency
- Task: `FOUNDATION-STUDIO-APPLICATION-GATEWAYS-001`
- Base: `b8a543c09cc89b1b7378f21215f70afa586b248d`
- Scope: HTTP/application composition only; no model, enum, schema or migration

## Decision

The canonical `/api/foundation/` boundary exposes the accepted typed-definition
services without adding a Studio persistence or lifecycle authority. Authenticated
Django users are converted to HUMAN `StudioPrincipal` values. Existing project
groups named `studio-project:<Project UUID>` are the only object-scope grants.
Inaccessible objects are resolved as 404 before capability disclosure.

The exact added operations are:

| Method and path | Django route name | Authority |
| --- | --- | --- |
| `POST definitions/<definition_id>/publish-successor/` | `foundation-definition-publish-successor` | canonical ordinary publication, no workspace |
| `GET definitions/<definition_id>/` | existing `foundation-definition-open` | typed DRAFT, VALIDATED, PUBLISHED or RETIRED read |
| `POST projects/<project_id>/definition-packages/2.1/preview/` | `foundation-definition-package-21-preview` | non-mutating server preview |
| `POST projects/<project_id>/definition-packages/2.1/attempt/` | `foundation-definition-package-21-attempt` | durable canonical import attempt |
| `GET definitions/<definition_id>/package/2.1/` | `foundation-definition-package-21-export` | existing package exporter plus HTTP representation |
| `POST projects/bootstrap-first-draft/` | `foundation-project-bootstrap-first-draft` | atomic Project, scope, DRAFT and CREATE audit |

There is no `/api/studio` alias.

## Lifecycle and conflict contract

Lifecycle reads refetch and validate the exact persisted typed manifest and hash.
PUBLISHED and RETIRED DTOs are read-only. The DRAFT-only opener remains available
to internal callers whose precondition is specifically DRAFT.

Successor publication accepts only `{}` or one bounded `locale`; it delegates to
the canonical ordinary publication service with `workspace_spec=None`. It creates
no workspace and never repins an existing workspace. A retry or changed-current
race is classified from persisted identities by
`FoundationStudioApplicationConflict`, never exception prose, and returns stable
409 `SUCCESSOR_PUBLICATION_CONFLICT`.

First-project bootstrap accepts exactly:

```text
{
  project: {id, code, version, name, description, metadata},
  definition: {id, code, version, manifest, semantic_version, construct_version}
}
```

One transaction creates the Project, the derived scope group, creator membership,
the canonical first DRAFT and one trusted HUMAN definition CREATE audit. Project
UUID/code, group-name and first-definition UUID collisions have explicit 409 codes.
Any failure rolls back every row and membership.

## Package ingress and authorization

Preview and attempt admit and capture at most one immutable HTTP byte stream. A
successfully admitted body is consumed once, preserves exact `HTTP_BYTES`, full
SHA-256 and actual byte length, and is parsed without a second body read or JSON
reserialization. The transport budget limits bytes consumed from the request,
not merely bytes retained in memory: a known numeric `Content-Length` over the
limit is rejected before any read, and an absent, untrusted or mismatched length
can consume at most `max_bytes + 1` before rejection. Invalid media type, charset
or Content-Length is rejected at HTTP admission without a durable receipt.
Over-budget HTTP bodies likewise have no receipt and no claimed full-body raw
identity because their remainder is intentionally never consumed. Admitted
malformed or schema-invalid attempts still reach the canonical durable REJECTED
receipt path. The same limit applies when Django already exposes a private
preloaded `_body`: its size is checked before hashing or copying, and an
oversized preloaded body never becomes an exact `HTTP_BYTES` identity.

Before package work, the adapter requires all of:

1. authenticated HUMAN user;
2. exact project object scope;
3. Django `domain.add_importrun` entry permission;
4. HUMAN `DEFINITION_READ`.

Attempt performs the same non-mutating server preview and then checks the HUMAN
capability for the server-selected action:

| Intended action | Additional HUMAN check | Sealed SERVICE capability set |
| --- | --- | --- |
| malformed/unparseable | none beyond entry/read | `FOUNDATION_IMPORT` |
| `CREATE_DRAFT` | `DRAFT_CREATE` | `FOUNDATION_IMPORT`, `DRAFT_CREATE` |
| `BOOTSTRAP_PUBLISHED` | `DEFINITION_VALIDATE`, `DEFINITION_PUBLISH` | import, create, validate, publish |
| `REUSE_EXACT` | none beyond read | `FOUNDATION_IMPORT` |

Unknown actions fail closed. Only after HUMAN checks does the server construct a
sealed SERVICE principal. Public body, query and headers cannot select its actor,
role, capabilities, purpose or stale token.

Preview accepts no query. Attempt accepts the exact single-valued query set
`locale`, `initial_workspace_id`, `initial_workspace_code`,
`initial_workspace_version`, `initial_workspace_name` and
`initial_workspace_is_default` only when its own preview returns
`BOOTSTRAP_PUBLISHED`; otherwise every workspace query is rejected. Boolean text
is exactly `true` or `false`, and workspace metadata is server-fixed `{}`.

Preview returns the immutable action plus raw and semantic identities without a
write. Every admitted attempt returns HTTP 200 with REJECTED, FAILED or COMMITTED,
its canonical result and a projection of the single durable `ImportRun`. Auth,
scope and HTTP-admission failures create no receipt.

## Exact export representation

The HTTP adapter calls only
`export_project_definition_package_2_1(definition)`. It constructs:

```text
response_bytes = (canonical_json(package) + "\n").encode("utf-8")
representation_sha256 = sha256(response_bytes)
ETag = quoted representation_sha256
semantic_payload_sha256 = package.manifest.payload_sha256
```

The response is the exact byte sequence with terminal newline, not a DRF JSON
render. The representation validator and semantic payload checksum remain distinct
and are tested independently by exact byte-for-byte reimport.

## Security and verification

Basic authentication precedes session authentication. Anonymous requests are 401;
in-scope users missing an exact permission are 403; missing or inaccessible objects
are 404. Unsafe session requests require real CSRF. Explicit body/query/header
spoof vectors include actor, role, capability, service context/purpose, project
authority and stale-token authority.

For an authenticated unsafe session request, the adapter first applies only the
canonical non-consuming JSON media/charset gate. Media admission failures return
bounded HTTP 400 before CSRF and before body I/O, so unsupported form-urlencoded or
multipart media can never make Django parse `request.POST`. For admitted
`application/json`, the adapter then runs Django's real cookie/header check
against the underlying `HttpRequest`; missing or invalid CSRF returns 403 without
a body read. Only after CSRF succeeds may the view apply `Content-Length`, byte
budget and body capture/parser authority. Basic authentication reaches that same
view authority without session CSRF.

Acceptance preserves all accepted FSA tests and adds SQLite and PostgreSQL 18
route, lifecycle, conflict, raw-byte, receipt, rollback and concurrency gates.
`makemigrations --check --dry-run` must report no changes.

## FD01 structured validation preview

`CA-SUITE-I1-FOUNDATION-FD01-001` adds one Foundation-owned non-mutating route:

```text
POST /api/foundation/definitions/<definition_id>/validation-preview/
body = {"manifest": <one JSON object>}
```

It is available only for an exact accessible DRAFT and requires HUMAN
`DRAFT_SAVE`. Query parameters, `If-Match`, `Idempotency-Key` and public authority
headers are forbidden. The existing 2 MiB raw HTTP ingress limit, nesting limit,
strict UTF-8 JSON parser, real session CSRF, indistinguishable object-scope 404 and
capability ordering are reused rather than copied.

The sole semantic composition is
`validate_project_definition_manifest_policy()`. That policy calls the existing
`validate_project_definition_manifest_v1()` with the existing exact published
Help resolver. The HTTP preview and the typed DRAFT -> VALIDATED lifecycle service
both use the same public policy helper. `domain/services/project_definitions.py`
remains frozen and is still the only manifest validator; the API has no schema,
Help or diagnostic-ordering implementation of its own.

Valid and semantic-invalid candidates both return HTTP 200 using canonical UTF-8
JSON plus exactly one terminal LF. The `PROJECT_DEFINITION_MANIFEST_VALIDATION_V1`
representation binds the exact request-byte SHA/length, canonical candidate hash,
base and candidate manifest identities, full ordered diagnostic hash, bounded
projection, report hash and an ETag over the exact response bytes. The projection
returns at most 1000 diagnostics. Path and display message are bounded to 512 UTF-8
bytes; any truncation uses fixed `<TRUNCATED>` while preserving the SHA-256 of the
untruncated text. Diagnostic identity remains `(diagnostics_sha256, ordinal)` and
only the stable diagnostic `code` is semantic UI branch authority.

Preview has a strict all-table zero-write contract: no definition lifecycle or
hash/timestamp update, no `AuditEvent`, no session mutation, no auth-row update and
no receipt. Repeating byte-identical input against unchanged definition/Project/
Help snapshots must return byte-identical body and ETag. SQLite verifies sequential
semantics only; PostgreSQL 18 is the authoritative database regression target.

The RC1 boundary makes that contract true even on denied transport paths. An
outer wrapper returns one empty `405` with `Allow: POST` before DRF
authentication, permission evaluation or body access. Preview alone uses a
read-only Basic verifier: it checks stored password bytes without a setter, so
an upgrade-eligible hash cannot be persisted. After real session CSRF has made
its decision, the wrapper suppresses response-only session/CSRF cookie repair,
deletion and rotation; it does not bypass valid-session CSRF. Finally, parsed
JSON is recursively checked for Unicode scalar values before policy invocation
or canonical hashing. A lone surrogate in any nested key or string value returns
the fixed `RAW_JSON_UNICODE_SCALAR_INVALID` raw-ingress contract with zero writes.

RC1 delivery is also bound to the separately authorized start commit/tree. The
allowlist verifier requires the final head to descend from that exact start,
retains the exact eight FD01 test names and still freezes every non-FD01 surface.

FD01 changes no model, enum, permission, schema or migration. It does not authorize
FD05, C1, any SERVICE substitution for HUMAN authoring, scalar Power, formula,
prediction, recommendation, ranking or risk output. The accepted C0
`production_studio` subtree remains byte-for-byte frozen.
