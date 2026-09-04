"""Canonical write boundary for multilingual document evidence.

The F1 schema intentionally keeps :class:`DocumentContent` as the immutable
capture authority.  This module is the *only* runtime writer for the second
layer of multilingual identity: variants, role bindings, sentence identity,
translation provenance, alignment and document-to-document lineage.  The
migration uses historical models and therefore deliberately does not use this
runtime boundary.

The public functions are intentionally small, explicit construction commands:

``ingest_initial_synchronized_document``
    creates one initial document with a validated complete alignment;
``create_translation_edit_derivative``
    creates a new unsynchronised document for every persisted primary-text or
    segmentation edit; and
``create_complete_realignment_derivative``
    creates a further document only after a complete alignment has been
    supplied, without combining it with a primary-text edit.

No function here modifies an existing captured row.  That makes a historical
``FactEvidence -> TextFragment`` link stable even when a translation is later
corrected or re-aligned.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


# These persisted spellings are the F1 vocabulary.  Keeping the service on
# strings (rather than importing a TextChoices member) makes the authoritative
# boundary resilient during app loading and still lets model choices reject an
# accidental spelling drift.
ROLE_ORIGINAL = "ORIGINAL"
ROLE_PROJECT_PRIMARY = "PROJECT_PRIMARY"
SYNC_YES = True
SYNC_NO = False
LINEAGE_INITIAL_INGEST = "INITIAL_INGEST"
LINEAGE_TRANSLATION_EDIT = "TRANSLATION_EDIT"
LINEAGE_REALIGNMENT = "REALIGNMENT"
VARIANT_CAPTURED_ORIGINAL = "DECLARED"
VARIANT_PROJECT_PRIMARY = "TRANSLATED"
ALIGNMENT_ONE_TO_ONE = "ONE_TO_ONE"
ALIGNMENT_ONE_TO_MANY = "ONE_TO_MANY"
ALIGNMENT_MANY_TO_ONE = "MANY_TO_ONE"
PROVENANCE_UNKNOWN = "UNKNOWN"


class DocumentLineageError(ValidationError):
    """A fail-closed canonical document-lineage construction error."""


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    """The immutable identity and capture metadata for one new Document."""

    code: str
    title: str
    version: str = "1.0.0"
    document_version_code: str | None = None
    document_version_version: str = "1.0.0"
    captured_content_code: str | None = None
    captured_content_version: str = "1.0.0"
    canonical_url: str = ""
    capture_url: str = ""
    publication_date: date | None = None
    accessed_on: date | None = None
    captured_at: datetime | None = None
    media_type: str = "text/plain"
    encoding: str = "utf-8"
    normalization_version: str = "f1-normalized-text-v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def resolved_document_version_code(self) -> str:
        return self.document_version_code or f"{self.code}-VERSION"

    @property
    def resolved_captured_content_code(self) -> str:
        return self.captured_content_code or f"{self.code}-CONTENT"


@dataclass(frozen=True, slots=True)
class ContentVariantSpec:
    """One immutable coordinate system inside a captured document version."""

    language_tag: str
    normalized_text: str
    segmentation_version: str
    code: str | None = None
    version: str = "1.0.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SentenceSpec:
    """A stable sentence identity in one exact content variant."""

    text: str
    start_offset: int
    end_offset: int
    sentence_number: int | None = None
    code: str | None = None
    version: str = "1.0.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlignmentComponentSpec:
    """A stored connected component, never a positional alignment hint."""

    original_sentence_numbers: tuple[int, ...]
    project_primary_sentence_numbers: tuple[int, ...]
    code: str | None = None
    version: str = "1.0.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranslationProvenanceSpec:
    """Explicit provenance for translated (rather than monolingual) content.

    ``knowledge`` is ``UNKNOWN`` when provider/model/method facts are not
    known.  Blank optional values in that state are an explicit absence, not a
    fabricated provider claim.
    """

    translation_id: str = ""
    translation_version: str = ""
    translated_at: datetime | None = None
    actor_type: str = "UNKNOWN"
    actor_identifier: str = ""
    provider: str = ""
    model: str = ""
    method_version: str = ""
    knowledge: str = PROVENANCE_UNKNOWN
    code: str | None = None
    version: str = "1.0.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FragmentSpec:
    """An exact PROJECT_PRIMARY fragment created against one variant."""

    code: str
    start_offset: int
    end_offset: int
    selector: Mapping[str, Any]
    version: str = "1.0.0"
    page: str = ""
    section: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentLineageResult:
    """Exact rows created by one canonical document-lineage command."""

    document: Any
    document_version: Any
    captured_content: Any
    original_variant: Any
    primary_variant: Any
    original_role_binding: Any
    primary_role_binding: Any
    sentences: tuple[Any, ...]
    alignment_set: Any | None
    alignment_edges: tuple[Any, ...]
    translation_provenance: Any | None


def _domain_models() -> Any:
    """Resolve models lazily so importing the wheel never triggers DB work."""

    from domain import models as domain_models

    return domain_models


def _canonical_write_context():
    """Fail closed if a model layer accidentally omits the F1 write guard."""

    authority = getattr(_domain_models(), "_canonical_document_lineage_write", None)
    if authority is None:
        raise DocumentLineageError(
            "Document lineage runtime writes require the canonical model authority."
        )
    # The model layer exposes deliberately granular internal authority labels;
    # all are entered only by this one public service boundary.
    return authority(
        "document",
        "variant",
        "role_binding",
        "sentence",
        "alignment",
        "provenance",
        "fragment",
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _raise(field: str, message: str) -> None:
    raise DocumentLineageError({field: message})


def _ensure_persisted(value: Any, *, field_name: str) -> None:
    if value is None or getattr(value, "pk", None) is None:
        _raise(field_name, "A persisted object is required.")


def _require_same_workspace(*, workspace: Any, values: Iterable[tuple[str, Any]]) -> None:
    for name, value in values:
        if value is None:
            continue
        if getattr(value, "workspace_id", None) != workspace.pk:
            _raise(name, "The object belongs to another workspace.")


def _role_binding_for(document_version: Any, role: str) -> Any | None:
    models = _domain_models()
    return (
        models.DocumentContentRoleBinding.objects.select_related("content_variant")
        .filter(document_version=document_version, role=role)
        .first()
    )


def _assert_distinct_or_monolingual(
    original: ContentVariantSpec,
    primary: ContentVariantSpec,
    provenance: TranslationProvenanceSpec | None,
) -> bool:
    """Return whether one variant may safely serve both role bindings."""

    monolingual = (
        original.language_tag == primary.language_tag
        and original.normalized_text == primary.normalized_text
        and original.segmentation_version == primary.segmentation_version
    )
    if monolingual and provenance is not None:
        _raise(
            "translation_provenance",
            "Monolingual role views must not fabricate translation provenance.",
        )
    if not monolingual and provenance is None:
        _raise(
            "translation_provenance",
            "Distinct ORIGINAL and PROJECT_PRIMARY content requires explicit provenance.",
        )
    return monolingual


def _normalise_sentences(
    sentences: Sequence[SentenceSpec],
    *,
    variant: ContentVariantSpec,
    role: str,
) -> tuple[SentenceSpec, ...]:
    """Validate exact sentence coordinates before persistent writes begin."""

    if not sentences:
        _raise(role, "A synchronized role requires at least one stored sentence.")
    normalized: list[SentenceSpec] = []
    seen_numbers: set[int] = set()
    seen_coordinates: set[tuple[int, int]] = set()
    for index, sentence in enumerate(sentences, start=1):
        number = sentence.sentence_number if sentence.sentence_number is not None else index
        if number < 1 or number in seen_numbers:
            _raise(role, "Sentence numbers must be unique positive identities.")
        if sentence.start_offset < 0 or sentence.end_offset <= sentence.start_offset:
            _raise(role, "Sentence offsets must be a non-empty exact range.")
        if sentence.end_offset > len(variant.normalized_text):
            _raise(role, "Sentence offsets exceed the exact variant text.")
        if (
            variant.normalized_text[sentence.start_offset : sentence.end_offset]
            != sentence.text
        ):
            _raise(role, "Sentence text must resolve against its exact variant.")
        coordinates = (sentence.start_offset, sentence.end_offset)
        if coordinates in seen_coordinates:
            _raise(role, "Duplicate sentence coordinate identities are forbidden.")
        seen_numbers.add(number)
        seen_coordinates.add(coordinates)
        normalized.append(
            SentenceSpec(
                text=sentence.text,
                start_offset=sentence.start_offset,
                end_offset=sentence.end_offset,
                sentence_number=number,
                code=sentence.code,
                version=sentence.version,
                metadata=sentence.metadata,
            )
        )
    return tuple(normalized)


def _validate_components(
    components: Sequence[AlignmentComponentSpec],
    *,
    original_sentences: Sequence[SentenceSpec],
    primary_sentences: Sequence[SentenceSpec],
) -> tuple[AlignmentComponentSpec, ...]:
    """Reject partial, duplicate, positional and M:N synchronization claims."""

    if not components:
        _raise("alignment", "Synchronized content requires stored alignment components.")
    original_numbers = {sentence.sentence_number for sentence in original_sentences}
    primary_numbers = {sentence.sentence_number for sentence in primary_sentences}
    used_original: set[int] = set()
    used_primary: set[int] = set()
    normalized: list[AlignmentComponentSpec] = []
    for component in components:
        originals = tuple(sorted(set(component.original_sentence_numbers)))
        primaries = tuple(sorted(set(component.project_primary_sentence_numbers)))
        if not originals or not primaries:
            _raise("alignment", "An alignment component cannot be orphaned.")
        if len(originals) != len(component.original_sentence_numbers):
            _raise("alignment", "Duplicate original sentence identities are forbidden.")
        if len(primaries) != len(component.project_primary_sentence_numbers):
            _raise("alignment", "Duplicate primary sentence identities are forbidden.")
        if not set(originals).issubset(original_numbers):
            _raise("alignment", "An alignment references an unknown original sentence.")
        if not set(primaries).issubset(primary_numbers):
            _raise("alignment", "An alignment references an unknown primary sentence.")
        if len(originals) > 1 and len(primaries) > 1:
            _raise("alignment", "Many-to-many alignment is never synchronized.")
        if used_original.intersection(originals) or used_primary.intersection(primaries):
            _raise("alignment", "Sentences may belong to only one alignment component.")
        used_original.update(originals)
        used_primary.update(primaries)
        normalized.append(
            AlignmentComponentSpec(
                original_sentence_numbers=originals,
                project_primary_sentence_numbers=primaries,
                code=component.code,
                version=component.version,
                metadata=component.metadata,
            )
        )
    if used_original != original_numbers or used_primary != primary_numbers:
        _raise("alignment", "Synchronization requires complete coverage of both sentence sets.")
    return tuple(normalized)


def _variant_code(document: DocumentSpec, role: str) -> str:
    return f"{document.code}-{role}-VARIANT"


def _sentence_code(document: DocumentSpec, role: str, number: int) -> str:
    return f"{document.code}-{role}-S{number:04d}"


def _component_code(document: DocumentSpec, position: int) -> str:
    return f"{document.code}-ALIGNMENT-E{position:04d}"


def _alignment_set_code(document: DocumentSpec) -> str:
    return f"{document.code}-ALIGNMENT"


def _provenance_code(document: DocumentSpec) -> str:
    return f"{document.code}-TRANSLATION-PROVENANCE"


def _document_scoped_code(
    document: DocumentSpec,
    supplied: str | None,
    fallback: str,
) -> str:
    """Keep explicitly supplied child identities unique for every derivative.

    A caller may deliberately reuse a ``ContentVariantSpec`` (and its sentence
    specs) while asking for a *new* realignment Document.  Its immutable child
    records still need new workspace-wide codes.  Codes already namespaced by
    this new Document stay readable; all other explicit codes gain the new
    document prefix.  The digest tail preserves a deterministic valid identity
    if a legal but long input would otherwise exceed the 128-character model
    bound.
    """

    base = supplied or fallback
    prefix = f"{document.code}-"
    candidate = base if base.startswith(prefix) else f"{prefix}{base}"
    if len(candidate) <= 128:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16]
    available = 128 - len(digest) - 1
    return f"{candidate[:available]}-{digest}"


def _document_content_bytes(text: str, encoding: str) -> bytes:
    try:
        return text.encode(encoding)
    except LookupError as exc:
        _raise("encoding", "Captured content encoding is not available.")
        raise AssertionError("unreachable") from exc


def _alignment_checksum(
    *,
    original_variant: Any,
    primary_variant: Any,
    original_sentences: Mapping[int, Any],
    primary_sentences: Mapping[int, Any],
    components: Sequence[AlignmentComponentSpec],
) -> str:
    """Bind concrete IDs, hashes, segmentation and sorted edge components."""

    edges: list[dict[str, Any]] = []
    for component in components:
        if len(component.original_sentence_numbers) == 1 and len(
            component.project_primary_sentence_numbers
        ) == 1:
            cardinality = ALIGNMENT_ONE_TO_ONE
        elif len(component.original_sentence_numbers) == 1:
            cardinality = ALIGNMENT_ONE_TO_MANY
        else:
            cardinality = ALIGNMENT_MANY_TO_ONE
        for original_number in component.original_sentence_numbers:
            for primary_number in component.project_primary_sentence_numbers:
                edges.append(
                    {
                        "original_sentence_id": str(original_sentences[original_number].pk),
                        "original_sentence_sha256": original_sentences[
                            original_number
                        ].text_sha256,
                        "project_primary_sentence_id": str(
                            primary_sentences[primary_number].pk
                        ),
                        "project_primary_sentence_sha256": primary_sentences[
                            primary_number
                        ].text_sha256,
                        "cardinality": cardinality,
                    }
                )
    edges.sort(
        key=lambda edge: (
            edge["original_sentence_id"],
            edge["project_primary_sentence_id"],
            edge["cardinality"],
        )
    )
    return _canonical_json_sha256(
        {
            "original_variant_id": str(original_variant.pk),
            "original_variant_sha256": original_variant.content_sha256,
            "original_segmentation_version": original_variant.segmentation_version,
            "project_primary_variant_id": str(primary_variant.pk),
            "project_primary_variant_sha256": primary_variant.content_sha256,
            "project_primary_segmentation_version": primary_variant.segmentation_version,
            "original_sentences": [
                {
                    "id": str(sentence.pk),
                    "number": sentence.sentence_number,
                    "sha256": sentence.text_sha256,
                }
                for _, sentence in sorted(original_sentences.items())
            ],
            "project_primary_sentences": [
                {
                    "id": str(sentence.pk),
                    "number": sentence.sentence_number,
                    "sha256": sentence.text_sha256,
                }
                for _, sentence in sorted(primary_sentences.items())
            ],
            "edges": edges,
        }
    )


def _create_result(
    *,
    workspace: Any,
    source: Any,
    document_spec: DocumentSpec,
    original: ContentVariantSpec,
    primary: ContentVariantSpec,
    original_sentences: Sequence[SentenceSpec],
    primary_sentences: Sequence[SentenceSpec],
    alignment_components: Sequence[AlignmentComponentSpec],
    provenance: TranslationProvenanceSpec | None,
    predecessor_document: Any | None,
    lineage_kind: str,
    synchronized: bool,
) -> DocumentLineageResult:
    """Create one complete immutable graph under the canonical authority."""

    models = _domain_models()
    _ensure_persisted(workspace, field_name="workspace")
    _ensure_persisted(source, field_name="source")
    _require_same_workspace(workspace=workspace, values=(("source", source),))
    if predecessor_document is not None:
        _ensure_persisted(predecessor_document, field_name="predecessor_document")
        _require_same_workspace(
            workspace=workspace,
            values=(("predecessor_document", predecessor_document),),
        )
    monolingual = _assert_distinct_or_monolingual(original, primary, provenance)
    if provenance is not None:
        if not provenance.translation_id.strip():
            _raise(
                "translation_provenance",
                "Translation provenance requires an exact translation identity.",
            )
        if not provenance.translation_version.strip():
            _raise(
                "translation_provenance",
                "Translation provenance requires an exact translation version.",
            )
        if provenance.translated_at is None:
            _raise(
                "translation_provenance",
                "Translation provenance requires the recorded translation time.",
            )
    if synchronized:
        normalized_original_sentences = _normalise_sentences(
            original_sentences, variant=original, role=ROLE_ORIGINAL
        )
        normalized_primary_sentences = (
            normalized_original_sentences
            if monolingual
            else _normalise_sentences(
                primary_sentences,
                variant=primary,
                role=ROLE_PROJECT_PRIMARY,
            )
        )
        components = _validate_components(
            alignment_components,
            original_sentences=normalized_original_sentences,
            primary_sentences=normalized_primary_sentences,
        )
    else:
        if alignment_components:
            _raise(
                "alignment",
                "Unsynchronized translation edits cannot carry a complete alignment claim.",
            )
        normalized_original_sentences = tuple(
            _normalise_sentences(
                original_sentences, variant=original, role=ROLE_ORIGINAL
            )
            if original_sentences
            else ()
        )
        normalized_primary_sentences = tuple(
            _normalise_sentences(
                primary_sentences, variant=primary, role=ROLE_PROJECT_PRIMARY
            )
            if primary_sentences
            else ()
        )
        components = ()

    capture_bytes = _document_content_bytes(original.normalized_text, document_spec.encoding)
    capture_sha256 = hashlib.sha256(capture_bytes).hexdigest()
    document_id = uuid4()
    root_document_id = (
        getattr(predecessor_document, "root_document_id", None)
        if predecessor_document is not None
        else document_id
    )
    if root_document_id is None:
        _raise("predecessor_document", "The predecessor must have an exact root document.")

    with _canonical_write_context():
        document = models.Document(
            id=document_id,
            workspace=workspace,
            source=source,
            code=document_spec.code,
            version=document_spec.version,
            title=document_spec.title,
            canonical_url=document_spec.canonical_url,
            publication_date=document_spec.publication_date,
            accessed_on=document_spec.accessed_on,
            metadata=dict(document_spec.metadata),
            predecessor_document=predecessor_document,
            root_document_id=root_document_id,
            lineage_kind=lineage_kind,
            translation_synchronized=SYNC_YES if synchronized else SYNC_NO,
        )
        document.full_clean()
        document.save(force_insert=True)

        document_version = models.DocumentVersion(
            workspace=workspace,
            document=document,
            code=document_spec.resolved_document_version_code,
            version=document_spec.document_version_version,
            status="CONTENT_CAPTURED",
            capture_url=document_spec.capture_url,
            captured_at=document_spec.captured_at or timezone.now(),
            content_sha256=capture_sha256,
            media_type=document_spec.media_type,
            metadata={},
        )
        document_version.full_clean()
        document_version.save(force_insert=True)

        captured_content = models.DocumentContent(
            workspace=workspace,
            document_version=document_version,
            code=document_spec.resolved_captured_content_code,
            version=document_spec.captured_content_version,
            normalized_text=original.normalized_text,
            original_bytes=capture_bytes,
            encoding=document_spec.encoding,
            normalization_version=document_spec.normalization_version,
            content_sha256=capture_sha256,
        )
        captured_content.full_clean()
        captured_content.save(force_insert=True)

        original_variant = models.DocumentContentVariant(
            workspace=workspace,
            document_version=document_version,
            document_content=captured_content,
            code=_document_scoped_code(
                document_spec,
                original.code,
                _variant_code(document_spec, ROLE_ORIGINAL),
            ),
            version=original.version,
            language_tag=original.language_tag,
            normalized_text=original.normalized_text,
            content_sha256=_sha256_text(original.normalized_text),
            segmentation_version=original.segmentation_version,
            variant_kind=VARIANT_CAPTURED_ORIGINAL,
            metadata=dict(original.metadata),
        )
        original_variant.full_clean()
        original_variant.save(force_insert=True)
        if monolingual:
            primary_variant = original_variant
        else:
            primary_variant = models.DocumentContentVariant(
                workspace=workspace,
                document_version=document_version,
                document_content=None,
                code=_document_scoped_code(
                    document_spec,
                    primary.code,
                    _variant_code(document_spec, ROLE_PROJECT_PRIMARY),
                ),
                version=primary.version,
                language_tag=primary.language_tag,
                normalized_text=primary.normalized_text,
                content_sha256=_sha256_text(primary.normalized_text),
                segmentation_version=primary.segmentation_version,
                variant_kind=VARIANT_PROJECT_PRIMARY,
                metadata=dict(primary.metadata),
            )
            primary_variant.full_clean()
            primary_variant.save(force_insert=True)

        original_binding = models.DocumentContentRoleBinding(
            workspace=workspace,
            document_version=document_version,
            content_variant=original_variant,
            code=f"{document_spec.code}-{ROLE_ORIGINAL}-ROLE",
            version="1.0.0",
            role=ROLE_ORIGINAL,
        )
        original_binding.full_clean()
        original_binding.save(force_insert=True)
        primary_binding = models.DocumentContentRoleBinding(
            workspace=workspace,
            document_version=document_version,
            content_variant=primary_variant,
            code=f"{document_spec.code}-{ROLE_PROJECT_PRIMARY}-ROLE",
            version="1.0.0",
            role=ROLE_PROJECT_PRIMARY,
        )
        primary_binding.full_clean()
        primary_binding.save(force_insert=True)

        stored_original: dict[int, Any] = {}
        stored_primary: dict[int, Any] = {}
        for sentence in normalized_original_sentences:
            assert sentence.sentence_number is not None
            stored = models.DocumentSentence(
                workspace=workspace,
                content_variant=original_variant,
                code=_document_scoped_code(
                    document_spec,
                    sentence.code,
                    _sentence_code(
                        document_spec, ROLE_ORIGINAL, sentence.sentence_number
                    ),
                ),
                version=sentence.version,
                sentence_number=sentence.sentence_number,
                text=sentence.text,
                start_offset=sentence.start_offset,
                end_offset=sentence.end_offset,
                text_sha256=_sha256_text(sentence.text),
                segmentation_version=original_variant.segmentation_version,
                metadata=dict(sentence.metadata),
            )
            stored.full_clean()
            stored.save(force_insert=True)
            stored_original[sentence.sentence_number] = stored
        if monolingual:
            stored_primary = stored_original
        else:
            for sentence in normalized_primary_sentences:
                assert sentence.sentence_number is not None
                stored = models.DocumentSentence(
                    workspace=workspace,
                    content_variant=primary_variant,
                    code=_document_scoped_code(
                        document_spec,
                        sentence.code,
                        _sentence_code(
                            document_spec,
                            ROLE_PROJECT_PRIMARY,
                            sentence.sentence_number,
                        ),
                    ),
                    version=sentence.version,
                    sentence_number=sentence.sentence_number,
                    text=sentence.text,
                    start_offset=sentence.start_offset,
                    end_offset=sentence.end_offset,
                    text_sha256=_sha256_text(sentence.text),
                    segmentation_version=primary_variant.segmentation_version,
                    metadata=dict(sentence.metadata),
                )
                stored.full_clean()
                stored.save(force_insert=True)
                stored_primary[sentence.sentence_number] = stored

        alignment_set = None
        stored_edges: list[Any] = []
        if synchronized:
            alignment_set = models.SentenceAlignmentSet(
                workspace=workspace,
                document_version=document_version,
                original_variant=original_variant,
                project_primary_variant=primary_variant,
                code=_alignment_set_code(document_spec),
                version="1.0.0",
                original_segmentation_version=original_variant.segmentation_version,
                project_primary_segmentation_version=primary_variant.segmentation_version,
                alignment_sha256=_alignment_checksum(
                    original_variant=original_variant,
                    primary_variant=primary_variant,
                    original_sentences=stored_original,
                    primary_sentences=stored_primary,
                    components=components,
                ),
            )
            alignment_set.full_clean()
            alignment_set.save(force_insert=True)
            edge_position = 0
            for component in components:
                if len(component.original_sentence_numbers) == 1 and len(
                    component.project_primary_sentence_numbers
                ) == 1:
                    cardinality = ALIGNMENT_ONE_TO_ONE
                elif len(component.original_sentence_numbers) == 1:
                    cardinality = ALIGNMENT_ONE_TO_MANY
                else:
                    cardinality = ALIGNMENT_MANY_TO_ONE
                for original_number in component.original_sentence_numbers:
                    for primary_number in component.project_primary_sentence_numbers:
                        edge_position += 1
                        edge_code = _document_scoped_code(
                            document_spec,
                            (
                                f"{component.code}-{edge_position:04d}"
                                if component.code
                                else None
                            ),
                            _component_code(document_spec, edge_position),
                        )
                        edge = models.SentenceAlignmentEdge(
                            workspace=workspace,
                            alignment_set=alignment_set,
                            original_sentence=stored_original[original_number],
                            project_primary_sentence=stored_primary[primary_number],
                            code=edge_code,
                            version=component.version,
                            cardinality=cardinality,
                            metadata=dict(component.metadata),
                        )
                        edge.full_clean()
                        edge.save(force_insert=True)
                        stored_edges.append(edge)

        stored_provenance = None
        if provenance is not None:
            source_variant = original_variant
            source_document_version = document_version
            if predecessor_document is not None:
                source_variant = _predecessor_original_variant(predecessor_document)
                source_document_version = source_variant.document_version
            stored_provenance = models.TranslationProvenance(
                workspace=workspace,
                document_version=document_version,
                project_primary_variant=primary_variant,
                source_document_version=source_document_version,
                source_content_variant=source_variant,
                code=_document_scoped_code(
                    document_spec,
                    provenance.code,
                    _provenance_code(document_spec),
                ),
                version=provenance.version,
                source_language_tag=source_variant.language_tag,
                target_language_tag=primary_variant.language_tag,
                translation_id=provenance.translation_id,
                translation_version=provenance.translation_version,
                translated_at=provenance.translated_at,
                actor_type=provenance.actor_type,
                actor_identifier=provenance.actor_identifier,
                provider=provenance.provider,
                model=provenance.model,
                method_version=provenance.method_version,
                knowledge=provenance.knowledge,
                alignment_set=alignment_set,
                metadata=dict(provenance.metadata),
            )
            stored_provenance.full_clean()
            stored_provenance.save(force_insert=True)

    all_sentence_by_id = {
        sentence.pk: sentence
        for sentence in (*stored_original.values(), *stored_primary.values())
    }
    all_sentences = tuple(
        sorted(
            all_sentence_by_id.values(),
            key=lambda sentence: (sentence.content_variant_id, sentence.sentence_number),
        )
    )
    return DocumentLineageResult(
        document=document,
        document_version=document_version,
        captured_content=captured_content,
        original_variant=original_variant,
        primary_variant=primary_variant,
        original_role_binding=original_binding,
        primary_role_binding=primary_binding,
        sentences=all_sentences,
        alignment_set=alignment_set,
        alignment_edges=tuple(stored_edges),
        translation_provenance=stored_provenance,
    )


@transaction.atomic
def ingest_initial_synchronized_document(
    *,
    workspace: Any,
    source: Any,
    document: DocumentSpec,
    original: ContentVariantSpec,
    project_primary: ContentVariantSpec,
    original_sentences: Sequence[SentenceSpec],
    project_primary_sentences: Sequence[SentenceSpec],
    alignment_components: Sequence[AlignmentComponentSpec],
    translation_provenance: TranslationProvenanceSpec | None = None,
) -> DocumentLineageResult:
    """Create a first immutable document only with complete alignment evidence."""

    return _create_result(
        workspace=workspace,
        source=source,
        document_spec=document,
        original=original,
        primary=project_primary,
        original_sentences=original_sentences,
        primary_sentences=project_primary_sentences,
        alignment_components=alignment_components,
        provenance=translation_provenance,
        predecessor_document=None,
        lineage_kind=LINEAGE_INITIAL_INGEST,
        synchronized=True,
    )


def _predecessor_primary_variant(predecessor_document: Any) -> Any:
    models = _domain_models()
    document_version = (
        models.DocumentVersion.objects.filter(document=predecessor_document)
        .order_by("created_at", "code", "pk")
        .last()
    )
    if document_version is None:
        _raise("predecessor_document", "The predecessor has no captured document version.")
    binding = _role_binding_for(document_version, ROLE_PROJECT_PRIMARY)
    if binding is None:
        _raise(
            "predecessor_document",
            "The predecessor has no authoritative PROJECT_PRIMARY role binding.",
        )
    return binding.content_variant


def _predecessor_original_variant(predecessor_document: Any) -> Any:
    models = _domain_models()
    document_version = (
        models.DocumentVersion.objects.filter(document=predecessor_document)
        .order_by("created_at", "code", "pk")
        .last()
    )
    if document_version is None:
        _raise("predecessor_document", "The predecessor has no captured document version.")
    binding = _role_binding_for(document_version, ROLE_ORIGINAL)
    if binding is None:
        _raise(
            "predecessor_document",
            "The predecessor has no authoritative ORIGINAL role binding.",
        )
    return binding.content_variant


@transaction.atomic
def create_translation_edit_derivative(
    *,
    predecessor_document: Any,
    document: DocumentSpec,
    original: ContentVariantSpec,
    project_primary: ContentVariantSpec,
    original_sentences: Sequence[SentenceSpec] = (),
    project_primary_sentences: Sequence[SentenceSpec] = (),
    translation_provenance: TranslationProvenanceSpec | None = None,
) -> DocumentLineageResult:
    """Create an unsynchronised derivative for every persisted primary edit.

    The function rejects an exact primary text/segmentation no-op.  It never
    carries an alignment forward, even if the predecessor had a complete one.
    """

    _ensure_persisted(predecessor_document, field_name="predecessor_document")
    predecessor_primary = _predecessor_primary_variant(predecessor_document)
    if (
        predecessor_primary.normalized_text == project_primary.normalized_text
        and predecessor_primary.language_tag == project_primary.language_tag
        and predecessor_primary.segmentation_version == project_primary.segmentation_version
    ):
        _raise(
            "project_primary",
            "A translation edit requires a real primary text or segmentation change.",
        )
    return _create_result(
        workspace=predecessor_document.workspace,
        source=predecessor_document.source,
        document_spec=document,
        original=original,
        primary=project_primary,
        original_sentences=original_sentences,
        primary_sentences=project_primary_sentences,
        alignment_components=(),
        provenance=translation_provenance,
        predecessor_document=predecessor_document,
        lineage_kind=LINEAGE_TRANSLATION_EDIT,
        synchronized=False,
    )


@transaction.atomic
def create_complete_realignment_derivative(
    *,
    predecessor_document: Any,
    document: DocumentSpec,
    original: ContentVariantSpec,
    project_primary: ContentVariantSpec,
    original_sentences: Sequence[SentenceSpec],
    project_primary_sentences: Sequence[SentenceSpec],
    alignment_components: Sequence[AlignmentComponentSpec],
    translation_provenance: TranslationProvenanceSpec | None,
) -> DocumentLineageResult:
    """Create a new synchronized identity only after explicit complete alignment.

    Re-alignment is intentionally unable to smuggle in a primary content edit:
    both role texts and segmentation versions must equal the predecessor's
    exact role variants.  A subsequent edit must instead use the unsynced
    derivative command above.
    """

    _ensure_persisted(predecessor_document, field_name="predecessor_document")
    predecessor_original = _predecessor_original_variant(predecessor_document)
    predecessor_primary = _predecessor_primary_variant(predecessor_document)
    for field_name, prior, requested in (
        ("original", predecessor_original, original),
        ("project_primary", predecessor_primary, project_primary),
    ):
        if (
            prior.normalized_text != requested.normalized_text
            or prior.language_tag != requested.language_tag
            or prior.segmentation_version != requested.segmentation_version
        ):
            _raise(
                field_name,
                "Complete re-alignment cannot combine a role text or segmentation edit.",
            )
    return _create_result(
        workspace=predecessor_document.workspace,
        source=predecessor_document.source,
        document_spec=document,
        original=original,
        primary=project_primary,
        original_sentences=original_sentences,
        primary_sentences=project_primary_sentences,
        alignment_components=alignment_components,
        provenance=translation_provenance,
        predecessor_document=predecessor_document,
        lineage_kind=LINEAGE_REALIGNMENT,
        synchronized=True,
    )


@transaction.atomic
def create_exact_project_primary_fragment(
    *,
    document_version: Any,
    content_variant: Any,
    fragment: FragmentSpec,
) -> Any:
    """Create one exact extraction fragment pinned to PROJECT_PRIMARY text.

    This helper prevents a caller from using primary offsets against an
    ORIGINAL (or legacy-unspecified) coordinate system.  It does not create a
    FactEvidence row; that existing immutable authority remains separate.
    """

    models = _domain_models()
    _ensure_persisted(document_version, field_name="document_version")
    _ensure_persisted(content_variant, field_name="content_variant")
    if content_variant.document_version_id != document_version.pk:
        _raise("content_variant", "The content variant belongs to another document version.")
    binding = _role_binding_for(document_version, ROLE_PROJECT_PRIMARY)
    if binding is None or binding.content_variant_id != content_variant.pk:
        _raise(
            "content_variant",
            "New analytical fragments must pin the PROJECT_PRIMARY role variant.",
        )
    if fragment.start_offset < 0 or fragment.end_offset <= fragment.start_offset:
        _raise("fragment", "Exact fragment offsets must form a non-empty range.")
    exact_text = content_variant.normalized_text[
        fragment.start_offset : fragment.end_offset
    ]
    if not exact_text:
        _raise("fragment", "Exact fragment offsets do not resolve in the primary variant.")
    with _canonical_write_context():
        result = models.TextFragment(
            workspace=document_version.workspace,
            document_version=document_version,
            content_variant=content_variant,
            code=fragment.code,
            version=fragment.version,
            anchor_status="EXACT",
            start_offset=fragment.start_offset,
            end_offset=fragment.end_offset,
            selector=dict(fragment.selector),
            page=fragment.page,
            section=fragment.section,
            exact_text=exact_text,
            text_sha256=_sha256_text(exact_text),
            metadata=dict(fragment.metadata),
        )
        result.full_clean()
        result.save(force_insert=True)
    return result
