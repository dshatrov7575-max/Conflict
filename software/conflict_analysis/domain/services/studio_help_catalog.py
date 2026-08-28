"""Exact-byte provisioning for the Foundation-owned Russian Studio Help catalog.

The catalog is an explicit input artifact.  Nothing in this module embeds a
second copy of its content or searches the current working directory for it.
Only bytes matching the pinned committed artifact can reach the database.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import HelpTopic, UIHelpBinding
from domain.services.help_topics import sanitize_help_html, sanitized_help_checksum


CATALOG_ID: Final = "FOUNDATION_STUDIO_HELP_RU_V1"
CATALOG_VERSION: Final = "1.0.0"
CATALOG_APPLICATION_SCOPE: Final = HelpApplicationScope.STUDIO
CATALOG_LOCALE: Final = "ru"
CATALOG_SHA256: Final = (
    "1ca03e1672737101e10780135ec228b4ba0b8812d272c3a0d6cb00dd2de2d81e"
)
CATALOG_BYTE_LENGTH: Final = 4742
CATALOG_IDENTITY_PREFIX: Final = (
    "https://conflictology.invalid/foundation/studio-help/ru/v1/"
)
_DATABASE_ALIAS: Final = "default"

_CATALOG_KEYS: Final = frozenset(
    {
        "catalog",
        "catalog_version",
        "application_scope",
        "locale",
        "published_at",
        "topics",
        "bindings",
    }
)
_TOPIC_KEYS: Final = frozenset(
    {
        "id",
        "code",
        "stable_key",
        "version",
        "title",
        "construct_version",
        "term_version",
        "sanitized_html",
        "content_sha256",
    }
)
_BINDING_KEYS: Final = frozenset(
    {"id", "code", "ui_key", "version", "topic_id"}
)


class StudioHelpCatalogError(ValueError):
    """The catalog bytes or persisted exact identity failed closed."""


@dataclass(frozen=True, slots=True)
class StudioHelpTopicSpec:
    id: UUID
    code: str
    stable_key: str
    application_scope: str
    locale: str
    version: str
    title: str
    construct_version: str
    term_version: str
    sanitized_html: str
    content_sha256: str
    publication_status: str
    published_at: datetime

    @property
    def content_bytes(self) -> bytes:
        return self.sanitized_html.encode("utf-8")


@dataclass(frozen=True, slots=True)
class StudioHelpBindingSpec:
    id: UUID
    code: str
    ui_key: str
    application_scope: str
    locale: str
    version: str
    topic_id: UUID
    topic_stable_key: str
    topic_content_sha256: str
    workspace_id: None = None
    is_global: bool = True
    topic_publication_status: str = PublicationStatus.PUBLISHED


@dataclass(frozen=True, slots=True)
class StudioHelpCatalog:
    catalog_id: str
    catalog_version: str
    application_scope: str
    locale: str
    published_at: datetime
    source_bytes: bytes
    source_sha256: str
    source_byte_length: int
    topics: tuple[StudioHelpTopicSpec, ...]
    bindings: tuple[StudioHelpBindingSpec, ...]

    @property
    def catalog_sha256(self) -> str:
        return self.source_sha256

    @property
    def catalog_byte_length(self) -> int:
        return self.source_byte_length


@dataclass(frozen=True, slots=True)
class StudioHelpProvisioningResult:
    catalog_id: str
    catalog_version: str
    source_sha256: str
    source_byte_length: int
    topics_created: int
    bindings_created: int
    topics_total: int
    bindings_total: int

    @property
    def catalog_sha256(self) -> str:
        return self.source_sha256

    @property
    def catalog_byte_length(self) -> int:
        return self.source_byte_length


CatalogSource = bytes | bytearray | memoryview | os.PathLike[str]


def _catalog_failure(reason: str) -> StudioHelpCatalogError:
    return StudioHelpCatalogError(f"Foundation Studio Help catalog rejected: {reason}.")


def _read_source(source: CatalogSource) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (bytearray, memoryview)):
        return bytes(source)
    if isinstance(source, os.PathLike):
        try:
            return Path(source).read_bytes()
        except OSError as exc:
            raise _catalog_failure("source bytes are unavailable") from exc
    raise TypeError("Studio Help catalog source must be bytes or an os.PathLike path.")


def _reject_json_constant(token: str) -> None:
    raise _catalog_failure(f"non-finite JSON number {token!r}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _catalog_failure("duplicate JSON member")
        result[key] = value
    return result


def _exact_keys(value: Any, expected: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise _catalog_failure(f"{label} has an unexpected shape")
    return value


def _text(value: Any, label: str, *, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise _catalog_failure(f"{label} must be non-empty text")
    if maximum is not None and len(value) > maximum:
        raise _catalog_failure(f"{label} exceeds its bound")
    return value


def _uuid(value: Any, label: str) -> UUID:
    try:
        parsed = UUID(_text(value, label))
    except (ValueError, AttributeError) as exc:
        raise _catalog_failure(f"{label} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise _catalog_failure(f"{label} must be a canonical lowercase UUID")
    return parsed


def _published_at(value: Any) -> datetime:
    text = _text(value, "published_at")
    if not text.endswith("Z"):
        raise _catalog_failure("published_at must use an exact UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as exc:
        raise _catalog_failure("published_at is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise _catalog_failure("published_at must be UTC")
    return parsed


def _expected_uuid(kind: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{CATALOG_IDENTITY_PREFIX}{kind}:{key}")


def load_studio_help_catalog(source: CatalogSource) -> StudioHelpCatalog:
    """Parse the one pinned catalog artifact without filesystem fallback."""

    raw = _read_source(source)
    if len(raw) != CATALOG_BYTE_LENGTH:
        raise _catalog_failure("byte length does not match the pinned artifact")
    source_sha256 = hashlib.sha256(raw).hexdigest()
    if source_sha256 != CATALOG_SHA256:
        raise _catalog_failure("SHA-256 does not match the pinned artifact")
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise _catalog_failure("the pinned artifact must end in exactly one LF")

    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise _catalog_failure("source is not strict UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise _catalog_failure("source is not one strict JSON document") from exc

    root = _exact_keys(payload, _CATALOG_KEYS, "catalog")
    if root["catalog"] != CATALOG_ID:
        raise _catalog_failure("catalog identity is not exact")
    if root["catalog_version"] != CATALOG_VERSION:
        raise _catalog_failure("catalog version is not exact")
    if root["application_scope"] != CATALOG_APPLICATION_SCOPE:
        raise _catalog_failure("application scope is not exact")
    if root["locale"] != CATALOG_LOCALE:
        raise _catalog_failure("locale is not exact")
    published_at = _published_at(root["published_at"])

    topic_rows = root["topics"]
    binding_rows = root["bindings"]
    if not isinstance(topic_rows, list) or not topic_rows:
        raise _catalog_failure("topics must be a non-empty ordered array")
    if not isinstance(binding_rows, list) or not binding_rows:
        raise _catalog_failure("bindings must be a non-empty ordered array")

    topics: list[StudioHelpTopicSpec] = []
    topic_ids: set[UUID] = set()
    topic_codes: set[str] = set()
    topic_identities: set[tuple[str, str, str, str]] = set()
    for index, raw_topic in enumerate(topic_rows):
        item = _exact_keys(raw_topic, _TOPIC_KEYS, f"topics[{index}]")
        stable_key = _text(item["stable_key"], f"topics[{index}].stable_key", maximum=128)
        topic_id = _uuid(item["id"], f"topics[{index}].id")
        if topic_id != _expected_uuid("topic", stable_key):
            raise _catalog_failure(f"topics[{index}].id is not its deterministic identity")
        code = _text(item["code"], f"topics[{index}].code", maximum=128)
        version = _text(item["version"], f"topics[{index}].version", maximum=64)
        if version != CATALOG_VERSION:
            raise _catalog_failure(f"topics[{index}].version is not exact")
        sanitized_html = _text(item["sanitized_html"], f"topics[{index}].sanitized_html")
        if sanitize_help_html(sanitized_html) != sanitized_html:
            raise _catalog_failure(f"topics[{index}] is not canonically sanitized")
        content_sha256 = _text(
            item["content_sha256"],
            f"topics[{index}].content_sha256",
            maximum=64,
        )
        if sanitized_help_checksum(sanitized_html) != content_sha256:
            raise _catalog_failure(f"topics[{index}] content SHA-256 is not exact")
        identity = (
            CATALOG_APPLICATION_SCOPE,
            stable_key,
            CATALOG_LOCALE,
            version,
        )
        if topic_id in topic_ids or code in topic_codes or identity in topic_identities:
            raise _catalog_failure("topic identity is duplicated")
        topic_ids.add(topic_id)
        topic_codes.add(code)
        topic_identities.add(identity)
        topics.append(
            StudioHelpTopicSpec(
                id=topic_id,
                code=code,
                stable_key=stable_key,
                application_scope=CATALOG_APPLICATION_SCOPE,
                locale=CATALOG_LOCALE,
                version=version,
                title=_text(item["title"], f"topics[{index}].title", maximum=500),
                construct_version=_text(
                    item["construct_version"],
                    f"topics[{index}].construct_version",
                    maximum=64,
                ),
                term_version=_text(
                    item["term_version"],
                    f"topics[{index}].term_version",
                    maximum=64,
                ),
                sanitized_html=sanitized_html,
                content_sha256=content_sha256,
                publication_status=PublicationStatus.PUBLISHED,
                published_at=published_at,
            )
        )

    topics_by_id = {topic.id: topic for topic in topics}
    bindings: list[StudioHelpBindingSpec] = []
    binding_ids: set[UUID] = set()
    binding_codes: set[str] = set()
    binding_identities: set[tuple[str, str, str, str]] = set()
    bound_topic_ids: set[UUID] = set()
    for index, raw_binding in enumerate(binding_rows):
        item = _exact_keys(raw_binding, _BINDING_KEYS, f"bindings[{index}]")
        ui_key = _text(item["ui_key"], f"bindings[{index}].ui_key", maximum=255)
        binding_id = _uuid(item["id"], f"bindings[{index}].id")
        if binding_id != _expected_uuid("binding", ui_key):
            raise _catalog_failure(f"bindings[{index}].id is not its deterministic identity")
        code = _text(item["code"], f"bindings[{index}].code", maximum=128)
        version = _text(item["version"], f"bindings[{index}].version", maximum=64)
        topic_id = _uuid(item["topic_id"], f"bindings[{index}].topic_id")
        topic = topics_by_id.get(topic_id)
        if topic is None:
            raise _catalog_failure(f"bindings[{index}] references an unknown topic")
        if version != topic.version:
            raise _catalog_failure(f"bindings[{index}] version does not match its topic")
        identity = (
            CATALOG_APPLICATION_SCOPE,
            ui_key,
            CATALOG_LOCALE,
            version,
        )
        if (
            binding_id in binding_ids
            or code in binding_codes
            or identity in binding_identities
            or topic_id in bound_topic_ids
        ):
            raise _catalog_failure("binding identity is duplicated")
        binding_ids.add(binding_id)
        binding_codes.add(code)
        binding_identities.add(identity)
        bound_topic_ids.add(topic_id)
        bindings.append(
            StudioHelpBindingSpec(
                id=binding_id,
                code=code,
                ui_key=ui_key,
                application_scope=CATALOG_APPLICATION_SCOPE,
                locale=CATALOG_LOCALE,
                version=version,
                topic_id=topic.id,
                topic_stable_key=topic.stable_key,
                topic_content_sha256=topic.content_sha256,
            )
        )

    if bound_topic_ids != topic_ids:
        raise _catalog_failure("every catalog topic must have one declared global binding")

    return StudioHelpCatalog(
        catalog_id=CATALOG_ID,
        catalog_version=CATALOG_VERSION,
        application_scope=CATALOG_APPLICATION_SCOPE,
        locale=CATALOG_LOCALE,
        published_at=published_at,
        source_bytes=raw,
        source_sha256=source_sha256,
        source_byte_length=len(raw),
        topics=tuple(topics),
        bindings=tuple(bindings),
    )


def _topic_relevant(row: HelpTopic, spec: StudioHelpTopicSpec) -> bool:
    return (
        row.pk == spec.id
        or row.code == spec.code
        or (
            row.application_scope,
            row.stable_key,
            row.locale,
            row.version,
        )
        == (
            spec.application_scope,
            spec.stable_key,
            spec.locale,
            spec.version,
        )
    )


def _topic_exact(row: HelpTopic, spec: StudioHelpTopicSpec) -> bool:
    return (
        row.pk == spec.id
        and row.code == spec.code
        and row.stable_key == spec.stable_key
        and row.application_scope == spec.application_scope
        and row.locale == spec.locale
        and row.version == spec.version
        and row.title == spec.title
        and row.construct_version == spec.construct_version
        and row.term_version == spec.term_version
        and row.sanitized_html == spec.sanitized_html
        and row.content_sha256 == spec.content_sha256
        and row.publication_status == spec.publication_status
        and row.published_at == spec.published_at
    )


def _binding_relevant(row: UIHelpBinding, spec: StudioHelpBindingSpec) -> bool:
    return (
        row.pk == spec.id
        or row.code == spec.code
        or (
            row.workspace_id,
            row.application_scope,
            row.ui_key,
            row.locale,
            row.version,
        )
        == (
            None,
            spec.application_scope,
            spec.ui_key,
            spec.locale,
            spec.version,
        )
    )


def _binding_exact(row: UIHelpBinding, spec: StudioHelpBindingSpec) -> bool:
    return (
        row.pk == spec.id
        and row.code == spec.code
        and row.workspace_id is None
        and row.application_scope == spec.application_scope
        and row.ui_key == spec.ui_key
        and row.locale == spec.locale
        and row.version == spec.version
        and row.help_topic_id == spec.topic_id
    )


def _topic_candidates(
    catalog: StudioHelpCatalog,
) -> list[HelpTopic]:
    query = Q(pk__in=[item.id for item in catalog.topics]) | Q(
        code__in=[item.code for item in catalog.topics]
    )
    for item in catalog.topics:
        query |= Q(
            application_scope=item.application_scope,
            stable_key=item.stable_key,
            locale=item.locale,
            version=item.version,
        )
    return list(
        HelpTopic.objects.using(_DATABASE_ALIAS)
        .select_for_update()
        .filter(query)
        .order_by("pk")
    )


def _binding_candidates(
    catalog: StudioHelpCatalog,
) -> list[UIHelpBinding]:
    query = Q(pk__in=[item.id for item in catalog.bindings]) | Q(
        code__in=[item.code for item in catalog.bindings]
    )
    for item in catalog.bindings:
        query |= Q(
            workspace__isnull=True,
            application_scope=item.application_scope,
            ui_key=item.ui_key,
            locale=item.locale,
            version=item.version,
        )
    return list(
        UIHelpBinding.objects.using(_DATABASE_ALIAS)
        .select_for_update()
        .filter(query)
        .order_by("pk")
    )


def _assert_persisted_or_missing(
    catalog: StudioHelpCatalog,
    *,
    topic_candidates: list[HelpTopic],
    binding_candidates: list[UIHelpBinding],
) -> tuple[set[UUID], set[UUID]]:
    existing_topic_ids: set[UUID] = set()
    for spec in catalog.topics:
        matches = [row for row in topic_candidates if _topic_relevant(row, spec)]
        if not matches:
            continue
        if len(matches) != 1 or matches[0].pk != spec.id:
            raise _catalog_failure(f"HelpTopic collision for {spec.stable_key}")
        if not _topic_exact(matches[0], spec):
            raise _catalog_failure(f"HelpTopic drift for {spec.stable_key}")
        existing_topic_ids.add(spec.id)

    existing_binding_ids: set[UUID] = set()
    for spec in catalog.bindings:
        matches = [row for row in binding_candidates if _binding_relevant(row, spec)]
        if not matches:
            continue
        if len(matches) != 1 or matches[0].pk != spec.id:
            raise _catalog_failure(f"UIHelpBinding collision for {spec.ui_key}")
        if not _binding_exact(matches[0], spec):
            raise _catalog_failure(f"UIHelpBinding drift for {spec.ui_key}")
        existing_binding_ids.add(spec.id)
    return existing_topic_ids, existing_binding_ids


def _provision_exact_catalog(
    catalog: StudioHelpCatalog,
) -> StudioHelpProvisioningResult:
    with transaction.atomic(using=_DATABASE_ALIAS):
        topic_candidates = _topic_candidates(catalog)
        binding_candidates = _binding_candidates(catalog)
        existing_topic_ids, existing_binding_ids = _assert_persisted_or_missing(
            catalog,
            topic_candidates=topic_candidates,
            binding_candidates=binding_candidates,
        )
        complete_repeat = (
            len(existing_topic_ids) == len(catalog.topics)
            and len(existing_binding_ids) == len(catalog.bindings)
        )
        if (existing_topic_ids or existing_binding_ids) and not complete_repeat:
            raise _catalog_failure("persisted catalog membership is partial")

        topic_objects: dict[UUID, HelpTopic] = {
            row.pk: row for row in topic_candidates if row.pk in existing_topic_ids
        }
        topics_created = 0
        for spec in catalog.topics:
            if spec.id in existing_topic_ids:
                continue
            topic = HelpTopic(
                id=spec.id,
                code=spec.code,
                stable_key=spec.stable_key,
                application_scope=spec.application_scope,
                locale=spec.locale,
                version=spec.version,
                title=spec.title,
                construct_version=spec.construct_version,
                term_version=spec.term_version,
                sanitized_html=spec.sanitized_html,
                content_sha256=spec.content_sha256,
                publication_status=spec.publication_status,
                published_at=spec.published_at,
            )
            topic.save(using=_DATABASE_ALIAS, force_insert=True)
            topic_objects[spec.id] = topic
            topics_created += 1

        bindings_created = 0
        for spec in catalog.bindings:
            if spec.id in existing_binding_ids:
                continue
            binding = UIHelpBinding(
                id=spec.id,
                code=spec.code,
                workspace=None,
                application_scope=spec.application_scope,
                ui_key=spec.ui_key,
                locale=spec.locale,
                version=spec.version,
                help_topic=topic_objects[spec.topic_id],
            )
            binding.save(using=_DATABASE_ALIAS, force_insert=True)
            bindings_created += 1

        return StudioHelpProvisioningResult(
            catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            source_sha256=catalog.source_sha256,
            source_byte_length=catalog.source_byte_length,
            topics_created=topics_created,
            bindings_created=bindings_created,
            topics_total=len(catalog.topics),
            bindings_total=len(catalog.bindings),
        )


def _exact_repeat_result(catalog: StudioHelpCatalog) -> StudioHelpProvisioningResult | None:
    """Classify a raced insert only after the failed transaction has rolled back."""

    with transaction.atomic(using=_DATABASE_ALIAS):
        existing_topic_ids, existing_binding_ids = _assert_persisted_or_missing(
            catalog,
            topic_candidates=_topic_candidates(catalog),
            binding_candidates=_binding_candidates(catalog),
        )
        if (
            len(existing_topic_ids) != len(catalog.topics)
            or len(existing_binding_ids) != len(catalog.bindings)
        ):
            return None
        return StudioHelpProvisioningResult(
            catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            source_sha256=catalog.source_sha256,
            source_byte_length=catalog.source_byte_length,
            topics_created=0,
            bindings_created=0,
            topics_total=len(catalog.topics),
            bindings_total=len(catalog.bindings),
        )


def provision_studio_help(source: CatalogSource) -> StudioHelpProvisioningResult:
    """Provision the pinned catalog atomically or make an exact repeat a no-op."""

    catalog = load_studio_help_catalog(source)
    try:
        return _provision_exact_catalog(catalog)
    except StudioHelpCatalogError:
        # Under PostgreSQL READ COMMITTED another exact provision can commit
        # between the topic and binding candidate reads.  The first attempt
        # then observes an apparently partial catalog even though the winning
        # transaction has committed the complete exact 4+4 graph.  Reconcile
        # only after our atomic block has exited, and only from complete
        # persisted truth; otherwise preserve the original drift/collision.
        try:
            raced_repeat = _exact_repeat_result(catalog)
        except StudioHelpCatalogError:
            raise
        if raced_repeat is not None:
            return raced_repeat
        raise
    except (IntegrityError, ValidationError) as exc:
        # A concurrent exact provision may win after both callers observed an
        # empty identity.  Reconcile only from complete persisted truth and
        # never adopt a partial, drifted or colliding catalog.
        try:
            raced_repeat = _exact_repeat_result(catalog)
        except StudioHelpCatalogError as classification_error:
            raise classification_error from exc
        if raced_repeat is not None:
            return raced_repeat
        raise _catalog_failure("atomic provisioning failed") from exc
    except Exception as exc:
        raise _catalog_failure("atomic provisioning failed") from exc


__all__ = [
    "CATALOG_APPLICATION_SCOPE",
    "CATALOG_BYTE_LENGTH",
    "CATALOG_ID",
    "CATALOG_LOCALE",
    "CATALOG_SHA256",
    "CATALOG_VERSION",
    "StudioHelpBindingSpec",
    "StudioHelpCatalog",
    "StudioHelpCatalogError",
    "StudioHelpProvisioningResult",
    "StudioHelpTopicSpec",
    "load_studio_help_catalog",
    "provision_studio_help",
]
