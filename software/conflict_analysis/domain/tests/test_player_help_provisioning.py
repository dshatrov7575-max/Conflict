"""Reusable G7 PLAYER-help assertions.

This module intentionally contains no collected test nodes.  RC4 and RC7 put
the provisioning, exact-replay and version-namespace assertions inside the
frozen Foundation node ``test_player_help_is_exact_versioned_sanitized_and_scope_hidden``.
Keeping the helpers here lets the Product tests reuse the same Foundation
oracle without increasing the literal 12 + 2 registry.
"""

from __future__ import annotations

__test__ = False

import hashlib
import json
from io import StringIO
from typing import Any
from uuid import uuid4

from django.core.management import call_command
from django.utils import timezone

from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import HelpTopic, ProjectWorkspace, UIHelpBinding
from domain.services.player_help_catalog import (
    CATALOG_LOCALE,
    CATALOG_VERSION,
    PLAYER_HELP_KEYS,
    PlayerHelpCatalogError,
    require_player_help_catalog,
    verify_player_help_bindings,
)


def player_help_binding_rows(workspace: ProjectWorkspace):
    """Return only the frozen G7 catalogue namespace in deterministic order."""

    return list(
        UIHelpBinding.objects.select_related("help_topic")
        .filter(
            workspace=workspace,
            application_scope=HelpApplicationScope.PLAYER,
            locale=CATALOG_LOCALE,
            version=CATALOG_VERSION,
        )
        .order_by("ui_key", "pk")
    )


def player_help_snapshot(workspace: ProjectWorkspace) -> tuple[tuple[Any, ...], ...]:
    """A write-sensitive snapshot used before/after provision and replay."""

    return tuple(
        (
            str(binding.pk),
            binding.code,
            binding.version,
            binding.ui_key,
            binding.locale,
            str(binding.help_topic_id),
            binding.help_topic.code,
            binding.help_topic.version,
            binding.help_topic.stable_key,
            binding.help_topic.content_sha256,
            binding.help_topic.sanitized_html,
        )
        for binding in player_help_binding_rows(workspace)
    )


def _run_provision_player_help_command(case) -> dict[str, Any]:
    """Run the deployable command, retaining its canonical receipt as an oracle."""

    stdout = StringIO()
    call_command("provision_player_help", stdout=stdout)
    payload = json.loads(stdout.getvalue())
    case.assertEqual(
        set(payload),
        {
            "catalog",
            "version",
            "locale",
            "catalog_sha256",
            "topics_created",
            "bindings_created",
            "topics_total",
            "workspaces_total",
        },
    )
    case.assertEqual(payload["version"], CATALOG_VERSION)
    case.assertEqual(payload["locale"], CATALOG_LOCALE)
    case.assertEqual(payload["topics_total"], len(PLAYER_HELP_KEYS))
    return payload


def assert_player_help_provisioning_contract(case, workspace: ProjectWorkspace) -> None:
    """Exercise RC4's explicit command and require an exact idempotent replay.

    The command is the only allowed historical-workspace binding mechanism.
    A second execution must neither repair nor append a row.  The Foundation
    service verifier is also invoked explicitly: normal GET paths are tested
    separately and may never call this provisioning helper.
    """

    # The verifier is deliberately read-only.  On a brand-new Foundation
    # database it must reject the absent persisted catalog; it must not turn
    # into a lazy initializer merely because a Player request touched it.
    if not HelpTopic.objects.filter(
        application_scope=HelpApplicationScope.PLAYER,
        locale=CATALOG_LOCALE,
        version=CATALOG_VERSION,
    ).exists():
        with case.assertRaises(PlayerHelpCatalogError):
            require_player_help_catalog()

    # RC4 requires the actual management-command surface, twice: the first
    # run provisions only the frozen catalog/bindings and the second is an
    # exact zero-write replay.  Service calls are intentionally not used as a
    # shortcut here.
    first_command = _run_provision_player_help_command(case)
    case.assertGreaterEqual(first_command["topics_created"], 0)
    case.assertGreaterEqual(first_command["bindings_created"], 0)

    catalog = require_player_help_catalog()
    case.assertEqual(len(catalog), len(PLAYER_HELP_KEYS))
    case.assertEqual(
        tuple(topic.stable_key for topic in catalog),
        tuple(PLAYER_HELP_KEYS),
    )
    case.assertTrue(
        all(
            topic.version == CATALOG_VERSION and topic.locale == CATALOG_LOCALE
            for topic in catalog
        )
    )

    first = player_help_snapshot(workspace)
    case.assertEqual(len(first), len(PLAYER_HELP_KEYS))
    case.assertEqual(
        tuple(row[3] for row in first),
        tuple(sorted(PLAYER_HELP_KEYS)),
    )
    case.assertEqual(len({row[0] for row in first}), len(PLAYER_HELP_KEYS))
    case.assertEqual(len({row[5] for row in first}), len(PLAYER_HELP_KEYS))

    for binding in player_help_binding_rows(workspace):
        topic = binding.help_topic
        case.assertEqual(binding.workspace_id, workspace.pk)
        case.assertEqual(binding.application_scope, HelpApplicationScope.PLAYER)
        case.assertEqual(binding.version, CATALOG_VERSION)
        case.assertEqual(binding.locale, CATALOG_LOCALE)
        case.assertEqual(topic.application_scope, HelpApplicationScope.PLAYER)
        case.assertEqual(topic.version, CATALOG_VERSION)
        case.assertEqual(topic.locale, CATALOG_LOCALE)
        case.assertEqual(
            topic.content_sha256,
            hashlib.sha256(topic.sanitized_html.encode("utf-8")).hexdigest(),
        )

    verified = verify_player_help_bindings(workspace)
    case.assertIsNotNone(verified)

    replay_command = _run_provision_player_help_command(case)
    case.assertEqual(replay_command["topics_created"], 0)
    case.assertEqual(replay_command["bindings_created"], 0)
    case.assertEqual(player_help_snapshot(workspace), first)


def add_valid_future_player_help_binding(case, workspace: ProjectWorkspace) -> UIHelpBinding:
    """Add a distinct later version to prove RC7 namespace isolation.

    This models an independently valid future catalogue row.  It deliberately
    does not alter the frozen 1.0.0 namespace; G7 replay must keep accepting
    its own exact rows without treating this row as an ``extra`` conflict.
    """

    current = player_help_binding_rows(workspace)[0]
    future_version = "2.0.0"
    html = "<p>Будущая неизменяемая справка Player.</p>"
    topic = HelpTopic.objects.create(
        id=uuid4(),
        code=f"PLAYER-FUTURE-{uuid4().hex[:16]}",
        version=future_version,
        stable_key=f"{current.help_topic.stable_key}.future",
        title="Будущая справка Player",
        application_scope=HelpApplicationScope.PLAYER,
        construct_version=future_version,
        term_version=future_version,
        locale=CATALOG_LOCALE,
        sanitized_html=html,
        content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        publication_status=PublicationStatus.PUBLISHED,
        published_at=timezone.now(),
    )
    future = UIHelpBinding.objects.create(
        id=uuid4(),
        workspace=workspace,
        application_scope=HelpApplicationScope.PLAYER,
        code=f"PLAYER-FUTURE-BINDING-{uuid4().hex[:16]}",
        version=future_version,
        ui_key=current.ui_key,
        locale=CATALOG_LOCALE,
        help_topic=topic,
    )
    case.assertEqual(future.version, future_version)
    return future


def assert_player_help_http_payload(
    case,
    payload: dict[str, Any],
    *,
    ui_key: str,
    version: str = CATALOG_VERSION,
) -> None:
    """Verify the bounded API DTO without creating a second Help resolver."""

    case.assertEqual(
        set(payload),
        {
            "contract",
            "version",
            "response_sha256",
            "workspace_id",
            "ui_key",
            "locale",
            "help_topic",
        },
    )
    topic = payload["help_topic"]
    case.assertEqual(
        set(topic),
        {
            "id",
            "version",
            "stable_key",
            "title",
            "locale",
            "sanitized_html",
            "content_sha256",
            "construct_version",
            "term_version",
        },
    )
    case.assertEqual(topic["stable_key"], ui_key)
    case.assertEqual(topic["version"], version)
    case.assertEqual(topic["locale"], CATALOG_LOCALE)
    case.assertEqual(payload["ui_key"], ui_key)
    case.assertEqual(payload["locale"], CATALOG_LOCALE)
    case.assertEqual(
        topic["content_sha256"],
        hashlib.sha256(topic["sanitized_html"].encode("utf-8")).hexdigest(),
    )
