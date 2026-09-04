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
    category: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "fact_id": self.fact_id,
            "fact_type": self.fact_type,
            "category": dict(self.category),
            "evidence": [dict(item) for item in self.evidence],
        }


def _models() -> Any:
    """Resolve Django models lazily; importing this module is always read-only."""

    from domain import models as domain_models

    return domain_models


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


def _synchronized_original_payload(fragment: Any) -> dict[str, Any] | None:
    """Return exact original sentences only for a fully verified graph."""

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
    edges = list(
        models.SentenceAlignmentEdge.objects.select_related(
            "original_sentence", "project_primary_sentence"
        )
        .filter(alignment_set=alignment_set)
        .order_by("original_sentence__sentence_number", "project_primary_sentence__sentence_number", "code", "pk")
    )
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
    sentence_payload = [
        {
            "id": str(sentence.pk),
            "code": sentence.code,
            "sentence_number": sentence.sentence_number,
            "text": sentence.text,
            "text_sha256": sentence.text_sha256,
        }
        for sentence in exact_sentences
    ]
    return {
        "variant_id": str(original_variant.pk),
        "language_tag": original_variant.language_tag,
        "sentences": sentence_payload,
        # This is formed only from stored ORIGINAL sentence identities reached
        # by persisted edges; it is never an offset/number/text guess.
        "excerpt": "\n".join(item["text"] for item in sentence_payload),
        "alignment_set_id": str(alignment_set.pk),
        "alignment_sha256": alignment_set.alignment_sha256,
    }


def _document_payload(document: Any) -> dict[str, Any]:
    source = document.source
    return {
        "id": str(document.pk),
        "code": document.code,
        "version": document.version,
        "root_document_id": str(document.root_document_id),
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
            "independence_status": source.independence_status,
        },
    }


def _evidence_payload(link: Any) -> tuple[dict[str, Any], bool]:
    """Return one exact evidence link and whether it can prove alignment."""

    fragment = link.fragment
    document_version = fragment.document_version
    primary = {
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
    }
    original = _synchronized_original_payload(fragment)
    if original is None:
        # Deliberately omit both `original` and `original_excerpt`: a null or
        # copied offset is too easy for downstream code to misread as a match.
        return payload, False
    payload["original"] = original
    payload["original_excerpt"] = original["excerpt"]
    return payload, True


def build_evidence_drilldown(fact: Any) -> EvidenceDrilldown:
    """Build deterministic evidence for a Fact with no mutation or inference.

    Callers are responsible for the authorization-before-disclosure admission
    sequence.  This function only reads a Fact that has already passed that
    boundary.
    """

    if fact is None or getattr(fact, "pk", None) is None:
        raise ValueError("A persisted Fact is required for evidence drilldown.")
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
        category=category,
        evidence=tuple(payloads),
    )
