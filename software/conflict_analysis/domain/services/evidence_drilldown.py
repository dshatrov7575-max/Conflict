"""Deterministic, read-only evidence drilldown for multilingual Facts.

This service deliberately does not infer a counterpart by offset, sentence
number, language name, or text similarity.  An ORIGINAL excerpt is emitted
only when an exact PROJECT_PRIMARY fragment is connected to exact ORIGINAL
sentences by a stored, complete, checksum-bound alignment graph.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping


ROLE_ORIGINAL = "ORIGINAL"
ROLE_PROJECT_PRIMARY = "PROJECT_PRIMARY"
SYNC_YES = True
ANCHOR_EXACT = "EXACT"
CARDINALITIES = frozenset({"ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE"})


class EvidenceDrilldownCode(StrEnum):
    """Typed read outcomes; none of them implies truth or source independence."""

    DOCUMENT_EVIDENCE = "DOCUMENT_EVIDENCE"
    DOCUMENT_EVIDENCE_REQUIRED = "DOCUMENT_EVIDENCE_REQUIRED"
    NO_DOCUMENT_EVIDENCE = "NO_DOCUMENT_EVIDENCE"
    ALIGNMENT_NOT_GUARANTEED = "ALIGNMENT_NOT_GUARANTEED"


@dataclass(frozen=True, slots=True)
class EvidenceDrilldown:
    """A stable read result for one Fact without any mutation side effect."""

    code: EvidenceDrilldownCode
    fact_id: str
    fact_type: str
    fact: Mapping[str, Any]
    category: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "fact_id": self.fact_id,
            "fact_type": self.fact_type,
            # The original top-level identity fields remain compatibility
            # fields.  This complete immutable Fact snapshot is additive and
            # deliberately contains no assessment or truth inference.
            "fact": dict(self.fact),
            "category": dict(self.category),
            "evidence": [dict(item) for item in self.evidence],
        }


def _models() -> Any:
    """Resolve Django models lazily; importing this module is always read-only."""

    from domain import models as domain_models

    return domain_models


def _fact_payload(fact: Any) -> dict[str, Any]:
    """Return the exact persisted Fact state exposed by this read contract."""

    return {
        "id": str(fact.pk),
        "code": fact.code,
        "version": fact.version,
        "fact_type": fact.fact_type,
        "statement": fact.statement,
        "origin": fact.origin,
        "directness": fact.directness,
        "status": fact.status,
        "temporal_status": fact.temporal_status,
    }


def _variant_payload(variant: Any) -> dict[str, Any]:
    """Expose an immutable variant identity without reinterpreting its text."""

    return {
        "variant_id": str(variant.pk),
        "language_tag": variant.language_tag,
        "content_sha256": variant.content_sha256,
        "segmentation_version": variant.segmentation_version,
    }


def _sentence_payload(sentences: Iterable[Any]) -> list[dict[str, Any]]:
    """Serialize only exact stored sentence identities and coordinates."""

    return [
        {
            "id": str(sentence.pk),
            "code": sentence.code,
            "sentence_number": sentence.sentence_number,
            "start_offset": sentence.start_offset,
            "end_offset": sentence.end_offset,
            "text": sentence.text,
            "text_sha256": sentence.text_sha256,
        }
        for sentence in sentences
    ]


def _stored_sentence_ranges_are_complete(
    sentences: Iterable[Any], *, variant: Any
) -> bool:
    """Fail closed unless stored ranges exactly cover non-whitespace text.

    The canonical writer normally guarantees this invariant.  Rechecking it
    at disclosure time prevents a corrupt or otherwise invalid persisted graph
    from being mistaken for a safely aligned original counterpart.
    """

    ordered = list(sentences)
    if not ordered:
        return False
    cursor = 0
    normalized_text = variant.normalized_text
    for sentence in ordered:
        start_offset = sentence.start_offset
        end_offset = sentence.end_offset
        if (
            start_offset < cursor
            or end_offset <= start_offset
            or end_offset > len(normalized_text)
            or normalized_text[start_offset:end_offset] != sentence.text
            or hashlib.sha256(sentence.text.encode("utf-8")).hexdigest()
            != sentence.text_sha256
        ):
            return False
        if any(
            not code_point.isspace()
            for code_point in normalized_text[cursor:start_offset]
        ):
            return False
        cursor = end_offset
    return not any(not code_point.isspace() for code_point in normalized_text[cursor:])


def _translation_provenance_payload(
    *, document_version: Any, project_primary_variant: Any | None
) -> dict[str, Any] | None:
    """Expose one exact stored provenance row, never a synthesized account."""

    if project_primary_variant is None:
        return None
    models = _models()
    rows = list(
        models.TranslationProvenance.objects.filter(
            document_version=document_version,
            project_primary_variant=project_primary_variant,
        ).order_by("code", "pk")
    )
    # A canonical version has one primary-role binding.  More than one matching
    # provenance row is corruption, not a reason to pick an arbitrary row.
    if len(rows) != 1:
        return None
    provenance = rows[0]
    return {
        "id": str(provenance.pk),
        "code": provenance.code,
        "version": provenance.version,
        "document_version_id": str(provenance.document_version_id),
        "project_primary_variant_id": str(provenance.project_primary_variant_id),
        "source_document_version_id": str(provenance.source_document_version_id),
        "source_content_variant_id": str(provenance.source_content_variant_id),
        "source_language_tag": provenance.source_language_tag,
        "target_language_tag": provenance.target_language_tag,
        "translation_id": provenance.translation_id,
        "translation_version": provenance.translation_version,
        "translated_at": (
            provenance.translated_at.isoformat()
            if provenance.translated_at is not None
            else None
        ),
        "actor_type": provenance.actor_type,
        "actor_identifier": provenance.actor_identifier,
        "provider": provenance.provider,
        "model": provenance.model,
        "method_version": provenance.method_version,
        "knowledge": provenance.knowledge,
        "alignment_set_id": (
            str(provenance.alignment_set_id)
            if provenance.alignment_set_id is not None
            else None
        ),
    }


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _category_path(category: Any) -> tuple[list[dict[str, str]], str]:
    """Build a deterministic ancestor path without treating labels as identity."""

    path: list[dict[str, str]] = []
    current = category
    seen: set[Any] = set()
    while current is not None:
        marker = getattr(current, "pk", None)
        if marker is None or marker in seen:
            # The model layer rejects cycles.  A corrupted graph still must not
            # turn into an invented path or an unbounded read loop.
            return [], ""
        seen.add(marker)
        path.append(
            {
                "id": str(current.pk),
                "code": str(current.code),
                "version": str(current.version),
            }
        )
        current = getattr(current, "parent", None)
    path.reverse()
    return path, "/".join(item["code"] for item in path)


def _category_payload(fact: Any) -> dict[str, Any]:
    models = _models()
    assignment = (
        models.FactCategoryAssignment.objects.select_related("category__parent")
        .filter(fact=fact)
        .order_by("code", "pk")
        .first()
    )
    if assignment is None:
        return {
            "assignment_id": None,
            "classification_status": "UNCLASSIFIED",
            "category": None,
            "ancestor_path": [],
            "full_path": "",
        }
    category = assignment.category
    if category is None:
        # An explicit legacy-compatible assignment record may intentionally
        # preserve the separate UNCLASSIFIED state without fabricating a
        # taxonomy node.  It remains distinct from an entirely absent row.
        return {
            "assignment_id": str(assignment.pk),
            "classification_status": assignment.classification_status,
            "category": None,
            "ancestor_path": [],
            "full_path": "",
        }
    path, full_path = _category_path(category)
    return {
        "assignment_id": str(assignment.pk),
        "classification_status": assignment.classification_status,
        "category": {
            "id": str(category.pk),
            "code": category.code,
            "version": category.version,
        },
        "ancestor_path": path,
        "full_path": full_path,
    }


def _role_bindings(document_version: Any) -> tuple[Any | None, Any | None]:
    models = _models()
    bindings = {
        binding.role: binding
        for binding in models.DocumentContentRoleBinding.objects.select_related(
            "content_variant"
        )
        .filter(
            document_version=document_version,
            role__in=(ROLE_ORIGINAL, ROLE_PROJECT_PRIMARY),
        )
    }
    return bindings.get(ROLE_ORIGINAL), bindings.get(ROLE_PROJECT_PRIMARY)


def _alignment_components_from_edges(
    *,
    edges: Iterable[Any],
    original_sentence_ids: set[Any],
    primary_sentence_ids: set[Any],
) -> tuple[bool, list[tuple[list[Any], list[Any]]]]:
    """Validate graph components, not merely each stored edge independently."""

    adjacency: dict[tuple[str, Any], set[tuple[str, Any]]] = {}
    seen_pairs: set[tuple[Any, Any]] = set()
    valid = True
    for edge in edges:
        original_id = edge.original_sentence_id
        primary_id = edge.project_primary_sentence_id
        if (
            original_id not in original_sentence_ids
            or primary_id not in primary_sentence_ids
            or edge.cardinality not in CARDINALITIES
            or (original_id, primary_id) in seen_pairs
        ):
            valid = False
            continue
        seen_pairs.add((original_id, primary_id))
        original_key = ("o", original_id)
        primary_key = ("p", primary_id)
        adjacency.setdefault(original_key, set()).add(primary_key)
        adjacency.setdefault(primary_key, set()).add(original_key)
    expected_nodes = {
        ("o", identifier) for identifier in original_sentence_ids
    } | {
        ("p", identifier) for identifier in primary_sentence_ids
    }
    if set(adjacency) != expected_nodes:
        return False, []

    components: list[tuple[list[Any], list[Any]]] = []
    pending = set(adjacency)
    while pending:
        start = min(pending, key=lambda item: (item[0], str(item[1])))
        stack = [start]
        members: set[tuple[str, Any]] = set()
        while stack:
            node = stack.pop()
            if node in members:
                continue
            members.add(node)
            stack.extend(adjacency[node] - members)
        pending -= members
        originals = sorted(
            (identifier for side, identifier in members if side == "o"), key=str
        )
        primaries = sorted(
            (identifier for side, identifier in members if side == "p"), key=str
        )
        if not originals or not primaries or (len(originals) > 1 and len(primaries) > 1):
            valid = False
        expected_cardinality = (
            "ONE_TO_ONE"
            if len(originals) == 1 and len(primaries) == 1
            else "ONE_TO_MANY"
            if len(originals) == 1
            else "MANY_TO_ONE"
        )
        for original_id in originals:
            for primary_id in primaries:
                # A component is valid only if it records the entire complete
                # bipartite relation, rather than a misleading sparse subset.
                if (original_id, primary_id) not in seen_pairs:
                    valid = False
        components.append((originals, primaries))
        for edge in edges:
            if (
                edge.original_sentence_id in originals
                and edge.project_primary_sentence_id in primaries
                and edge.cardinality != expected_cardinality
            ):
                valid = False
    return valid, components


def _alignment_checksum_matches(
    alignment_set: Any,
    *,
    original_variant: Any,
    primary_variant: Any,
    original_sentences: list[Any],
    primary_sentences: list[Any],
    edges: list[Any],
) -> bool:
    """Recompute the checksum from exact IDs/hashes/segmentations and edges."""

    edge_records = sorted(
        (
            {
                "original_sentence_id": str(edge.original_sentence_id),
                "original_sentence_sha256": edge.original_sentence.text_sha256,
                "project_primary_sentence_id": str(edge.project_primary_sentence_id),
                "project_primary_sentence_sha256": edge.project_primary_sentence.text_sha256,
                "cardinality": edge.cardinality,
            }
            for edge in edges
        ),
        key=lambda item: (
            item["original_sentence_id"],
            item["project_primary_sentence_id"],
            item["cardinality"],
        ),
    )
    expected = _canonical_sha256(
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
                for sentence in sorted(
                    original_sentences,
                    key=lambda sentence: (sentence.sentence_number, str(sentence.pk)),
                )
            ],
            "project_primary_sentences": [
                {
                    "id": str(sentence.pk),
                    "number": sentence.sentence_number,
                    "sha256": sentence.text_sha256,
                }
                for sentence in sorted(
                    primary_sentences,
                    key=lambda sentence: (sentence.sentence_number, str(sentence.pk)),
                )
            ],
            "edges": edge_records,
        }
    )
    return expected == getattr(alignment_set, "alignment_sha256", "")


def _synchronized_alignment_payload(fragment: Any) -> dict[str, Any] | None:
    """Return both exact role sides only for a fully verified graph.

    This never derives a counterpart from offsets, numbering or text.  The
    primary sentence list is the stored set that intersects the exact fragment;
    the original list is reached exclusively through persisted alignment edges.
    """

    models = _models()
    document_version = fragment.document_version
    document = document_version.document
    if (
        document.translation_synchronized != SYNC_YES
        or fragment.anchor_status != ANCHOR_EXACT
        or fragment.content_variant_id is None
    ):
        return None
    original_binding, primary_binding = _role_bindings(document_version)
    if (
        original_binding is None
        or primary_binding is None
        or primary_binding.content_variant_id != fragment.content_variant_id
    ):
        return None
    original_variant = original_binding.content_variant
    primary_variant = primary_binding.content_variant
    alignment_set = (
        models.SentenceAlignmentSet.objects.select_related(
            "original_variant", "project_primary_variant"
        )
        .filter(
            document_version=document_version,
            original_variant=original_variant,
            project_primary_variant=primary_variant,
        )
        .order_by("code", "pk")
        .first()
    )
    if alignment_set is None:
        return None
    original_sentences = list(
        models.DocumentSentence.objects.filter(content_variant=original_variant).order_by(
            "sentence_number", "code", "pk"
        )
    )
    primary_sentences = list(
        models.DocumentSentence.objects.filter(content_variant=primary_variant).order_by(
            "sentence_number", "code", "pk"
        )
    )
    if not original_sentences or not primary_sentences:
        return None
    if not _stored_sentence_ranges_are_complete(
        original_sentences, variant=original_variant
    ) or not _stored_sentence_ranges_are_complete(
        primary_sentences, variant=primary_variant
    ):
        return None
    if (
        fragment.start_offset is None
        or fragment.end_offset is None
        or fragment.end_offset <= fragment.start_offset
        or primary_variant.normalized_text[
            fragment.start_offset : fragment.end_offset
        ]
        != fragment.exact_text
        or hashlib.sha256(fragment.exact_text.encode("utf-8")).hexdigest()
        != fragment.text_sha256
    ):
        return None
    edges = list(
        models.SentenceAlignmentEdge.objects.select_related(
            "original_sentence", "project_primary_sentence"
        )
        .filter(alignment_set=alignment_set)
        .order_by("original_sentence__sentence_number", "project_primary_sentence__sentence_number", "code", "pk")
    )
    if original_variant.pk == primary_variant.pk and any(
        edge.cardinality != "ONE_TO_ONE"
        or edge.original_sentence_id != edge.project_primary_sentence_id
        for edge in edges
    ):
        # A shared monolingual coordinate system can only witness each stored
        # sentence against itself.  Even a checksum-valid cross-sentence graph
        # would be an invented translation relationship.
        return None
    graph_valid, _ = _alignment_components_from_edges(
        edges=edges,
        original_sentence_ids={sentence.pk for sentence in original_sentences},
        primary_sentence_ids={sentence.pk for sentence in primary_sentences},
    )
    if not graph_valid or not _alignment_checksum_matches(
        alignment_set,
        original_variant=original_variant,
        primary_variant=primary_variant,
        original_sentences=original_sentences,
        primary_sentences=primary_sentences,
        edges=edges,
    ):
        return None
    primary_for_fragment = {
        sentence.pk
        for sentence in primary_sentences
        if sentence.start_offset < fragment.end_offset
        and sentence.end_offset > fragment.start_offset
    }
    if not primary_for_fragment:
        return None
    original_for_fragment = {
        edge.original_sentence
        for edge in edges
        if edge.project_primary_sentence_id in primary_for_fragment
    }
    if not original_for_fragment:
        return None
    exact_sentences = sorted(
        original_for_fragment,
        key=lambda sentence: (sentence.sentence_number, sentence.code, str(sentence.pk)),
    )
    exact_primary_sentences = [
        sentence for sentence in primary_sentences if sentence.pk in primary_for_fragment
    ]
    original_sentence_payload = _sentence_payload(exact_sentences)
    primary_sentence_payload = _sentence_payload(exact_primary_sentences)
    original_payload = _variant_payload(original_variant)
    original_payload.update(
        {
            "sentences": original_sentence_payload,
            # This is formed only from stored ORIGINAL sentence identities
            # reached by persisted edges; it is never an offset/number/text
            # guess.
            "excerpt": "\n".join(item["text"] for item in original_sentence_payload),
            # Retain the established nested compatibility fields while the
            # evidence-level fields below make the shared alignment identity
            # explicit for both role sides.
            "alignment_set_id": str(alignment_set.pk),
            "alignment_sha256": alignment_set.alignment_sha256,
        }
    )
    primary_payload = _variant_payload(primary_variant)
    primary_payload.update(
        {
            "sentences": primary_sentence_payload,
            "alignment_set_id": str(alignment_set.pk),
            "alignment_sha256": alignment_set.alignment_sha256,
        }
    )
    return {
        "original": original_payload,
        "project_primary": primary_payload,
        "alignment_set_id": str(alignment_set.pk),
        "alignment_sha256": alignment_set.alignment_sha256,
    }


def _document_payload(document: Any) -> dict[str, Any]:
    source = document.source
    return {
        "id": str(document.pk),
        "code": document.code,
        "version": document.version,
        "root_document_id": (
            str(document.root_document_id)
            if document.root_document_id is not None
            else None
        ),
        "predecessor_document_id": (
            str(document.predecessor_document_id)
            if document.predecessor_document_id is not None
            else None
        ),
        "lineage_kind": document.lineage_kind,
        "translation_synchronized": document.translation_synchronized,
        "source": {
            "id": str(source.pk),
            "code": source.code,
            "name": source.name,
            "publisher": source.publisher,
            "independence_group": source.independence_group,
            "independence_status": source.independence_status,
        },
    }


def _evidence_payload(link: Any) -> tuple[dict[str, Any], bool]:
    """Return one exact evidence link and whether it can prove alignment."""

    fragment = link.fragment
    document_version = fragment.document_version
    primary_variant = fragment.content_variant
    primary: dict[str, Any] = {
        "fragment_id": str(fragment.pk),
        "fragment_code": fragment.code,
        "content_variant_id": (
            str(fragment.content_variant_id)
            if fragment.content_variant_id is not None
            else None
        ),
        "anchor_status": fragment.anchor_status,
        "start_offset": fragment.start_offset,
        "end_offset": fragment.end_offset,
        "exact_text": fragment.exact_text,
        "text_sha256": fragment.text_sha256,
    }
    if primary_variant is not None:
        # This additive identity is useful even for unsynchronised evidence;
        # it does not imply that an ORIGINAL counterpart is available.
        primary.update(_variant_payload(primary_variant))
    payload: dict[str, Any] = {
        "fact_evidence_id": str(link.pk),
        "fact_evidence_code": link.code,
        "relation": link.relation,
        "temporal_status": link.temporal_status,
        "learned_on": link.learned_on.isoformat() if link.learned_on else None,
        "rationale": link.rationale,
        "document_version": {
            "id": str(document_version.pk),
            "code": document_version.code,
            "version": document_version.version,
            "content_sha256": document_version.content_sha256,
        },
        "document": _document_payload(document_version.document),
        "project_primary": primary,
        "translation_provenance": _translation_provenance_payload(
            document_version=document_version,
            project_primary_variant=primary_variant,
        ),
    }
    synchronized = _synchronized_alignment_payload(fragment)
    if synchronized is None:
        # Deliberately omit both `original` and `original_excerpt`: a null or
        # copied offset is too easy for downstream code to misread as a match.
        return payload, False
    primary.update(synchronized["project_primary"])
    payload["original"] = synchronized["original"]
    payload["original_excerpt"] = synchronized["original"]["excerpt"]
    payload["alignment_set_id"] = synchronized["alignment_set_id"]
    payload["alignment_sha256"] = synchronized["alignment_sha256"]
    return payload, True


def build_evidence_drilldown(fact: Any) -> EvidenceDrilldown:
    """Build deterministic evidence for a Fact with no mutation or inference.

    Callers are responsible for the authorization-before-disclosure admission
    sequence.  This function only reads a Fact that has already passed that
    boundary.
    """

    if fact is None or getattr(fact, "pk", None) is None:
        raise ValueError("A persisted Fact is required for evidence drilldown.")
    fact_payload = _fact_payload(fact)
    category = _category_payload(fact)
    links = list(
        fact.evidence_links.select_related(
            "fragment__content_variant",
            "fragment__document_version__document__source",
        ).order_by("code", "pk")
    )
    if not links:
        code = (
            EvidenceDrilldownCode.DOCUMENT_EVIDENCE_REQUIRED
            if fact.origin == "DOCUMENT_DERIVED"
            else EvidenceDrilldownCode.NO_DOCUMENT_EVIDENCE
        )
        return EvidenceDrilldown(
            code=code,
            fact_id=str(fact.pk),
            fact_type=fact.fact_type,
            fact=fact_payload,
            category=category,
            evidence=(),
        )
    payloads: list[Mapping[str, Any]] = []
    all_aligned = True
    for link in links:
        payload, aligned = _evidence_payload(link)
        payloads.append(payload)
        all_aligned = all_aligned and aligned
    return EvidenceDrilldown(
        code=(
            EvidenceDrilldownCode.DOCUMENT_EVIDENCE
            if all_aligned
            else EvidenceDrilldownCode.ALIGNMENT_NOT_GUARANTEED
        ),
        fact_id=str(fact.pk),
        fact_type=fact.fact_type,
        fact=fact_payload,
        category=category,
        evidence=tuple(payloads),
    )
