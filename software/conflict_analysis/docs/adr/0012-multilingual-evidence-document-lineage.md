# ADR 0012: Multilingual evidence and document lineage

- Status: accepted implementation contract
- Scope: `CA-SUITE-I1-EVIDENCE-MULTILINGUAL-F1-001`
- Controlling base: `codex/ca-suite-i1-project-language-bootstrap-f0l`
  (`bfbd6b94c98ad27378c1452e38a69bf8b1fb169f`, tree
  `4806308745d46726c71eec38b3acac71f31b1542`)
- Decision source: Issue #84 MAIN architecture freeze V3 and owner-authorized
  F1 dispatch

## Context

Foundation already has immutable captured `Document`, `DocumentVersion`,
`DocumentContent`, `TextFragment`, `Fact`, and `FactEvidence` identities.
`DocumentContent` is a legacy OneToOne capture payload and hash authority;
`DocumentVersion.content_sha256` is its capture hash.  A multilingual layer
must make supported claims about language, translation, sentence alignment and
evidence without retroactively changing what a legacy capture meant.

The accepted F0L Project primary-language pair remains an inherited,
independent prerequisite.  This decision adds neither a new Project-language
rule nor a second source of language authority.

## Decision

### Immutable multilingual captures

Each new multilingual capture uses immutable `DocumentContentVariant` rows and
immutable `DocumentContentRoleBinding` rows.  The only semantic content roles
are `ORIGINAL` and `PROJECT_PRIMARY`; one monolingual variant may occupy both
roles.  A variant records its exact document version, captured-content link,
canonical language tag, normalized text checksum, and normalization/segmentation
identities.  Its coordinate checksum does not replace the legacy byte capture
hash: `DocumentContent` remains the payload/byte/hash authority.  A variant is
never a reinterpretation of the legacy `DocumentContent` payload.

Both role tags are canonicalized before any multilingual comparison or write.
`PROJECT_PRIMARY` must equal the canonical, non-`und`
`workspace.project.primary_language_tag`.  If canonical role tags are equal,
their normalized text and segmentation must also be equal and exactly one
shared variant is created; same-language divergent text is rejected rather
than presented as a translation.  A shared variant may only be self-aligned
sentence-by-sentence.

Legacy content is migrated to one `LEGACY_UNSPECIFIED`, `und` variant which
retains the exact legacy normalized text, while the legacy capture checksum
remains attached to its `DocumentContent` authority.  It receives no role
binding.  In particular, migration does not label legacy rows `ORIGINAL` or
`PROJECT_PRIMARY`.

The legacy successor UUID is deterministically derived from immutable legacy
`DocumentContent` identity.  Migration never decodes `original_bytes` or
replaces an empty `normalized_text`; it validates an exact fragment's version,
offsets, text and hash before pinning.  An unprovable exact anchor (including a
missing capture or mismatch) aborts the whole migration with a deterministic
typed blocker rather than leaving a null or guessed pin.

`TextFragment.content_variant` pins every canonical new `EXACT` fragment to a
concrete variant belonging to its exact `DocumentVersion`.  An exact fragment
with no such pin, or a pin that crosses version/workspace/document scope, is
rejected.  Migration binds legacy exact fragments to their version's legacy
variant; it does not invent a role, translation, sentence or alignment claim.

### Sentence identities and alignment

`DocumentSentence`, `SentenceAlignmentSet`, and `SentenceAlignmentEdge` are
append-only identities.  Sentence identity includes the exact content variant,
ordinal, text and text hash.  An alignment-set checksum binds the precise
variant IDs and hashes, sentence IDs and hashes, segmentation versions, and
the sorted edge set.

For a synchronized claim, sentence ranges are ordered, non-overlapping and
resolve exactly against both normalized role texts.  Every non-whitespace code
point is covered exactly once; uncovered separators may be whitespace only.
Every stored sentence participates in one complete 1:1, 1:N or N:1 component.
For a shared monolingual variant, that is restricted further to exact 1:1
self-edges for each stored sentence.  Partial, positional, crossed,
overlapping, duplicated, M:N or checksum-recomputed corrupt graphs fail
closed and cannot justify original-side disclosure.

`translation_synchronized=yes` is permitted only for a complete,
checksum-bound alignment covering both sentence sets.  Its connected
components may be only 1:1, 1:N, or N:1.  M:N, partial, positional-only,
guessed, contradictory, orphaned, duplicated, cross-document, cross-workspace
or checksum-drifting alignment is never synchronized.  No payload may infer an
original excerpt where this contract is absent.

### Translation provenance and document lineage

`TranslationProvenance` is immutable and explicit.  Known provider, model and
method values are retained exactly; when any such fact is not known, the
corresponding provenance state is explicitly `UNKNOWN` rather than filled with
a plausible value.

HUMAN, AI and HYBRID provenance requires a nonblank actor identifier; UNKNOWN
is explicitly blank-capable.  Every derivative command receives one persisted
predecessor `DocumentVersion`, verifies that it belongs to the exact
predecessor `Document` and records that version and its bound ORIGINAL variant
as the provenance source.  It never selects a latest/current version
implicitly.  A translation edit additionally proves that its supplied ORIGINAL
text, canonical language and segmentation equal that exact predecessor
ORIGINAL before it writes; only the project-primary role may change.

Documents carry immutable cross-document lineage:

```text
predecessor_document -> immediate prior Document or null
root_document        -> original lineage root
lineage_kind         -> immutable lineage reason
translation_synchronized -> claim for this Document identity
```

The sole runtime mutation boundary is
`domain.services.document_lineage`.  It creates an initial synchronized
ingest, an unsynchronized translation-edit derivative, or a new synchronized
realignment derivative.  Editing any persisted translation always creates a
new unsynchronized `Document`, preserving every prior identity.  Completing a
real alignment always creates another new synchronized `Document`.  Direct
instance, manager, queryset, bulk or raw-style paths that bypass this boundary
for protected lineage, role bindings, sentences, provenance or alignment fail
closed.  Migration historical models are not a runtime bypass.

### Fact categories remain a classification layer

`FactCategory` is an immutable Project-scoped taxonomy, shared by that
Project's Workspaces but never Workspace-owned.  Its parent chain is
same-Project, acyclic and deletion-restricted.  `FactCategoryAssignment` is an
immutable, explicit Fact-to-category record; its `classification_status`
belongs to the assignment rather than the category node.  `Fact.fact_type`
remains a distinct compatibility field.

Legacy Facts are `UNCLASSIFIED` unless an explicit assignment is made.  The
migration creates no category or assignment without evidence.  Category,
category depth and evidence-link count never assert truth, source
independence, guilt, causality, score correctness, or automatic numeric
influence.

### Read-only evidence drilldown

The canonical drilldown is:

```text
GET /api/foundation/projects/<project_id>/workspaces/<workspace_id>/facts/<fact_id>/evidence/
```

Admission is strictly ordered: read-only authentication with no password-hash
upgrade; server-derived Project access; Workspace membership in Project; Fact
membership in Workspace; visibility; and only then evidence query and payload.
Absent and unauthorized resources return the same non-fingerprinting `404`.
`WORKSPACE_SHARED` requires Project access.  `OWNER_ONLY` and
`EXPERIMENT_PRIVATE` additionally require a superuser or exact
`django-user:<pk>` equality with `Fact.coder_identifier`; `UNSPECIFIED` grants
no private access.

The GET is zero-write: it does not update password hashes, sessions, CSRF,
cookies or any evidence identity.  It sends `Cache-Control: no-store` and
`Vary: Cookie, Authorization`.  Ordering and representation are deterministic.
Memory-origin Facts return typed `NO_DOCUMENT_EVIDENCE`.  Unsynchronized
document evidence returns `ALIGNMENT_NOT_GUARANTEED` and no guessed original
excerpt.  A synchronized result resolves only the exact primary and original
fragments proven by its variant and alignment identities.

Drilldown retains its compatibility `fact_id`, `fact_type`, category and
evidence fields and additively serializes the exact Fact ID/code/version/type,
statement, origin, directness, status and temporal status.  It exposes stored
source `independence_group`, never an inferred independence claim.  A proven
synchronized pair carries both variants' language/hash/segmentation identity,
both sides' sentence ID/code/number/range/text/hash and the alignment-set
ID/hash.  It serializes stored translation provenance as stored; an absent
root is typed `null`, never the string `"None"`.

### Migration compatibility

Migration `0017_multilingual_evidence_lineage` is the successor to `0016` and
does not repeat or mutate Project primary-language logic.  It first creates the
successor tables and nullable lineage/content-variant fields, then backfills
legacy Documents as `root=self`, `predecessor=null`, `LEGACY_CAPTURE`, and
unsynchronized.  It backfills one exact legacy variant per `DocumentContent`
and pins each legacy exact fragment.  Only after that backfill are final
constraints installed.

Upgrade, reverse and reapply preserve every legacy UUID, byte payload, hash,
Document/Version/Fragment/FactEvidence identity, assessment/value/Power link,
and Project language pair.  The migration must not fabricate role bindings,
sentences, alignment, provenance, categories or assignments.

## Consequences

- Multilingual evidence can be precise without treating captured legacy text as
  a guessed original or primary translation.
- Translation edits and realignments are auditable successor Documents rather
  than destructive corrections.
- Consumers distinguish missing document evidence from evidence whose alignment
  cannot safely support a translated/original comparison.
- Project-level taxonomy supports consistent classification across Workspaces
  while preserving Fact type compatibility and explicit assignment state.
- The ADR itself is immutable Git evidence at this path, not a wheel payload.
  The wheel must instead expose migration `0017`, the two services, and the
  evidence API import without a source-tree fallback.
- This decision does not authorize workflow, package, seed/bootstrap,
  Production Studio, Calculation, Power, Monitoring, country-data, merge,
  release, rebase, cherry-pick, amend, or force-push work.
