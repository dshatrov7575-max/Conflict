from __future__ import annotations

import hashlib
import io
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import HelpTopic, UIHelpBinding
from domain.services import studio_help_catalog as studio_help_catalog_service
from domain.services.help_topics import HelpTopicResolutionError, resolve_help_topic
from domain.services.studio_help_catalog import (
    CATALOG_APPLICATION_SCOPE,
    CATALOG_BYTE_LENGTH,
    CATALOG_ID,
    CATALOG_LOCALE,
    CATALOG_SHA256,
    CATALOG_VERSION,
    StudioHelpCatalogError,
    load_studio_help_catalog,
    provision_studio_help,
)


CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "content" / "studio_help_ru_v1.json"
)
EXPECTED_CATALOG_ID = "FOUNDATION_STUDIO_HELP_RU_V1"
EXPECTED_CATALOG_VERSION = "1.0.0"
EXPECTED_CATALOG_SCOPE = "STUDIO"
EXPECTED_CATALOG_LOCALE = "ru"
EXPECTED_CATALOG_SHA256 = (
    "1ca03e1672737101e10780135ec228b4ba0b8812d272c3a0d6cb00dd2de2d81e"
)
EXPECTED_CATALOG_BYTE_LENGTH = 4742

EXPECTED_TOPICS = (
    (
        "studio.welcome",
        "991e01b1-d16e-5d80-9283-30e608ae8d67",
        "bf505770e9263c9b5d86012b7533a71fe24f57d740303463c4e0b9a8328a407a",
    ),
    (
        "studio.project.create",
        "a263df63-6577-57e4-88b4-4c7bc16cdb8b",
        "a24bdc2f0404f52d25b9a4ec62ba6cc68cc5099adc1d045409147c30a6c50ccf",
    ),
    (
        "studio.definition.validation",
        "cb2bf202-d177-583d-8385-400240873470",
        "4aed60801612f269109d162706418409e1d46e0c034bc6f502e5584c48320587",
    ),
    (
        "studio.definition.publication",
        "f8b65540-3335-5c82-9824-a4185f54dcc3",
        "a171a7178a8a9e085a3f61f92ac9e9eebd552132f979fd3b780485de3ba523d4",
    ),
)

EXPECTED_BINDINGS = (
    ("studio.welcome", "1b097286-ac02-5c4c-9853-a6f4b2811d1d"),
    ("studio.project.create", "cb7b8045-1ce5-57b1-abad-cb0fa022d15f"),
    (
        "studio.definition.validation",
        "ff0f539d-b159-501a-ad10-090d0e389531",
    ),
    (
        "studio.definition.publication",
        "11521788-65e2-5b3e-977e-c54cf51ae7d2",
    ),
)


class FoundationStudioHelpProvisioningTests(TestCase):
    maxDiff = None

    @staticmethod
    def _topic_from_spec(spec, **overrides) -> HelpTopic:
        values = {
            "id": spec.id,
            "code": spec.code,
            "version": spec.version,
            "stable_key": spec.stable_key,
            "title": spec.title,
            "application_scope": spec.application_scope,
            "construct_version": spec.construct_version,
            "term_version": spec.term_version,
            "locale": spec.locale,
            "sanitized_html": spec.sanitized_html,
            "content_sha256": spec.content_sha256,
            "publication_status": spec.publication_status,
            "published_at": spec.published_at,
        }
        values.update(overrides)
        return HelpTopic(**values)

    def test_catalog_identity_bytes_schema_and_checksum_are_exact(self):
        raw = CATALOG_PATH.read_bytes()
        self.assertEqual(len(raw), EXPECTED_CATALOG_BYTE_LENGTH)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_CATALOG_SHA256)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertFalse(raw.endswith(b"\n\n"))

        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(
            set(payload),
            {
                "catalog",
                "catalog_version",
                "application_scope",
                "locale",
                "published_at",
                "topics",
                "bindings",
            },
        )
        catalog = load_studio_help_catalog(CATALOG_PATH)
        self.assertEqual(load_studio_help_catalog(raw), catalog)
        self.assertEqual(load_studio_help_catalog(bytearray(raw)), catalog)
        self.assertEqual(load_studio_help_catalog(memoryview(raw)), catalog)
        self.assertEqual(
            (
                catalog.catalog_id,
                catalog.catalog_version,
                catalog.application_scope,
                catalog.locale,
                catalog.source_sha256,
                catalog.source_byte_length,
            ),
            (
                EXPECTED_CATALOG_ID,
                EXPECTED_CATALOG_VERSION,
                EXPECTED_CATALOG_SCOPE,
                EXPECTED_CATALOG_LOCALE,
                EXPECTED_CATALOG_SHA256,
                EXPECTED_CATALOG_BYTE_LENGTH,
            ),
        )
        self.assertEqual(
            (
                CATALOG_ID,
                CATALOG_VERSION,
                CATALOG_APPLICATION_SCOPE,
                CATALOG_LOCALE,
                CATALOG_SHA256,
                CATALOG_BYTE_LENGTH,
            ),
            (
                EXPECTED_CATALOG_ID,
                EXPECTED_CATALOG_VERSION,
                EXPECTED_CATALOG_SCOPE,
                EXPECTED_CATALOG_LOCALE,
                EXPECTED_CATALOG_SHA256,
                EXPECTED_CATALOG_BYTE_LENGTH,
            ),
        )
        self.assertEqual(
            tuple(
                (topic.stable_key, str(topic.id), topic.content_sha256)
                for topic in catalog.topics
            ),
            EXPECTED_TOPICS,
        )
        self.assertEqual(
            tuple((binding.ui_key, str(binding.id)) for binding in catalog.bindings),
            EXPECTED_BINDINGS,
        )
        for topic, binding in zip(catalog.topics, catalog.bindings, strict=True):
            self.assertEqual(binding.topic_id, topic.id)
            self.assertEqual(binding.topic_stable_key, topic.stable_key)
            self.assertEqual(binding.topic_content_sha256, topic.content_sha256)
            self.assertEqual(binding.workspace_id, None)
            self.assertTrue(binding.is_global)
            self.assertEqual(binding.topic_publication_status, PublicationStatus.PUBLISHED)
            self.assertEqual(hashlib.sha256(topic.content_bytes).hexdigest(), topic.content_sha256)

        with self.assertRaises(FrozenInstanceError):
            catalog.catalog_id = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            load_studio_help_catalog(str(CATALOG_PATH))  # type: ignore[arg-type]
        with self.assertRaisesRegex(StudioHelpCatalogError, "byte length"):
            load_studio_help_catalog(raw[:-1])
        drift = bytes([raw[0] ^ 1]) + raw[1:]
        with self.assertRaisesRegex(StudioHelpCatalogError, "SHA-256"):
            load_studio_help_catalog(drift)
        self.assertEqual((HelpTopic.objects.count(), UIHelpBinding.objects.count()), (0, 0))

    def test_first_provision_and_exact_repeat_are_idempotent(self):
        first = provision_studio_help(CATALOG_PATH)
        self.assertEqual(
            (
                first.catalog_id,
                first.catalog_version,
                first.source_sha256,
                first.source_byte_length,
                first.topics_created,
                first.bindings_created,
                first.topics_total,
                first.bindings_total,
            ),
            (CATALOG_ID, CATALOG_VERSION, CATALOG_SHA256, CATALOG_BYTE_LENGTH, 4, 4, 4, 4),
        )
        before = {
            "topics": list(
                HelpTopic.objects.order_by("pk").values_list("pk", "created_at", "updated_at")
            ),
            "bindings": list(
                UIHelpBinding.objects.order_by("pk").values_list(
                    "pk", "created_at", "updated_at"
                )
            ),
        }

        repeat = provision_studio_help(CATALOG_PATH.read_bytes())
        self.assertEqual(
            (repeat.topics_created, repeat.bindings_created, repeat.topics_total, repeat.bindings_total),
            (0, 0, 4, 4),
        )
        with patch(
            "domain.services.studio_help_catalog._provision_exact_catalog",
            side_effect=IntegrityError("simulated concurrent exact winner"),
        ):
            reconciled = provision_studio_help(CATALOG_PATH)
        self.assertEqual(
            (reconciled.topics_created, reconciled.bindings_created),
            (0, 0),
        )
        real_topic_candidates = studio_help_catalog_service._topic_candidates
        topic_candidate_calls = 0

        def split_snapshot_once(catalog):
            nonlocal topic_candidate_calls
            topic_candidate_calls += 1
            if topic_candidate_calls == 1:
                return []
            return real_topic_candidates(catalog)

        with patch.object(
            studio_help_catalog_service,
            "_topic_candidates",
            side_effect=split_snapshot_once,
        ):
            post_split_repeat = provision_studio_help(CATALOG_PATH)
        self.assertEqual(topic_candidate_calls, 2)
        self.assertEqual(
            (post_split_repeat.topics_created, post_split_repeat.bindings_created),
            (0, 0),
        )
        after = {
            "topics": list(
                HelpTopic.objects.order_by("pk").values_list("pk", "created_at", "updated_at")
            ),
            "bindings": list(
                UIHelpBinding.objects.order_by("pk").values_list(
                    "pk", "created_at", "updated_at"
                )
            ),
        }
        self.assertEqual(after, before)

        catalog = load_studio_help_catalog(CATALOG_PATH)
        for spec in catalog.topics:
            row = HelpTopic.objects.get(pk=spec.id)
            self.assertEqual(
                (
                    row.code,
                    row.version,
                    row.stable_key,
                    row.title,
                    row.application_scope,
                    row.construct_version,
                    row.term_version,
                    row.locale,
                    row.sanitized_html,
                    row.content_sha256,
                    row.publication_status,
                    row.published_at,
                ),
                (
                    spec.code,
                    spec.version,
                    spec.stable_key,
                    spec.title,
                    spec.application_scope,
                    spec.construct_version,
                    spec.term_version,
                    spec.locale,
                    spec.sanitized_html,
                    spec.content_sha256,
                    spec.publication_status,
                    spec.published_at,
                ),
            )
        for spec in catalog.bindings:
            row = UIHelpBinding.objects.get(pk=spec.id)
            self.assertEqual(
                (
                    row.code,
                    row.version,
                    row.workspace_id,
                    row.application_scope,
                    row.ui_key,
                    row.locale,
                    row.help_topic_id,
                ),
                (
                    spec.code,
                    spec.version,
                    None,
                    spec.application_scope,
                    spec.ui_key,
                    spec.locale,
                    spec.topic_id,
                ),
            )

    def test_management_command_requires_explicit_catalog_and_reports_exact_counts(self):
        with self.assertRaises(CommandError):
            call_command("provision_studio_help", stdout=io.StringIO())
        self.assertEqual((HelpTopic.objects.count(), UIHelpBinding.objects.count()), (0, 0))

        first_out = io.StringIO()
        call_command("provision_studio_help", CATALOG_PATH, stdout=first_out)
        self.assertEqual(
            first_out.getvalue().strip(),
            f"{CATALOG_ID} {CATALOG_VERSION} sha256={CATALOG_SHA256} "
            f"bytes={CATALOG_BYTE_LENGTH} topics=4 topics_created=4 "
            "bindings=4 bindings_created=4",
        )
        repeat_out = io.StringIO()
        call_command("provision_studio_help", CATALOG_PATH, stdout=repeat_out)
        self.assertEqual(
            repeat_out.getvalue().strip(),
            f"{CATALOG_ID} {CATALOG_VERSION} sha256={CATALOG_SHA256} "
            f"bytes={CATALOG_BYTE_LENGTH} topics=4 topics_created=0 "
            "bindings=4 bindings_created=0",
        )

    def test_topic_identity_or_content_collision_is_atomic(self):
        catalog = load_studio_help_catalog(CATALOG_PATH)
        first = catalog.topics[0]
        cases = (
            (
                "identity collision",
                {
                    "id": uuid4(),
                    "code": "FD02-FOREIGN-TOPIC",
                },
                "HelpTopic collision",
            ),
            (
                "content drift",
                {
                    "title": f"{first.title} drift",
                },
                "HelpTopic drift",
            ),
            (
                "exact partial membership",
                {},
                "persisted catalog membership is partial",
            ),
        )
        for label, overrides, expected_error in cases:
            with self.subTest(label=label):
                with transaction.atomic():
                    self._topic_from_spec(first, **overrides).save(force_insert=True)
                    before = (HelpTopic.objects.count(), UIHelpBinding.objects.count())
                    with self.assertRaisesRegex(StudioHelpCatalogError, expected_error):
                        provision_studio_help(CATALOG_PATH)
                    self.assertEqual(
                        (HelpTopic.objects.count(), UIHelpBinding.objects.count()),
                        before,
                    )
                    transaction.set_rollback(True)
        self.assertEqual((HelpTopic.objects.count(), UIHelpBinding.objects.count()), (0, 0))

    def test_binding_identity_collision_and_injected_failure_roll_back(self):
        catalog = load_studio_help_catalog(CATALOG_PATH)
        topic_spec = catalog.topics[0]
        binding_spec = catalog.bindings[0]
        with transaction.atomic():
            topic = self._topic_from_spec(topic_spec)
            topic.save(force_insert=True)
            UIHelpBinding(
                id=uuid4(),
                code="FD02-FOREIGN-BINDING",
                version=binding_spec.version,
                workspace=None,
                application_scope=binding_spec.application_scope,
                ui_key=binding_spec.ui_key,
                locale=binding_spec.locale,
                help_topic=topic,
            ).save(force_insert=True)
            before = (HelpTopic.objects.count(), UIHelpBinding.objects.count())
            with self.assertRaisesRegex(StudioHelpCatalogError, "UIHelpBinding collision"):
                provision_studio_help(CATALOG_PATH)
            self.assertEqual((HelpTopic.objects.count(), UIHelpBinding.objects.count()), before)
            transaction.set_rollback(True)

        original_save = UIHelpBinding.save
        calls = 0

        def fail_second_binding(instance, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected binding failure")
            return original_save(instance, *args, **kwargs)

        with patch.object(UIHelpBinding, "save", new=fail_second_binding):
            with self.assertRaisesRegex(StudioHelpCatalogError, "atomic provisioning failed"):
                provision_studio_help(CATALOG_PATH)
        self.assertEqual(calls, 2)
        self.assertEqual((HelpTopic.objects.count(), UIHelpBinding.objects.count()), (0, 0))

    def test_exact_resolver_and_http_return_bytes_or_exact_404(self):
        catalog = load_studio_help_catalog(CATALOG_PATH)
        provision_studio_help(CATALOG_PATH)
        user = get_user_model().objects.create_user(username="fd02-help-reader")
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
                codename="studio_read_definition",
            )
        )
        api = APIClient()
        api.force_authenticate(user)
        before = (HelpTopic.objects.count(), UIHelpBinding.objects.count())
        topic_specs = {topic.id: topic for topic in catalog.topics}

        for spec in catalog.bindings:
            with self.subTest(ui_key=spec.ui_key):
                self.assertEqual(
                    (
                        spec.application_scope,
                        spec.ui_key,
                        spec.locale,
                        spec.version,
                        spec.topic_stable_key,
                        spec.topic_content_sha256,
                    ),
                    (
                        HelpApplicationScope.STUDIO,
                        spec.ui_key,
                        CATALOG_LOCALE,
                        CATALOG_VERSION,
                        spec.ui_key,
                        topic_specs[spec.topic_id].content_sha256,
                    ),
                )
                topic = resolve_help_topic(
                    workspace=None,
                    application_scope=HelpApplicationScope.STUDIO,
                    ui_key=spec.ui_key,
                    locale=CATALOG_LOCALE,
                    version=CATALOG_VERSION,
                )
                self.assertEqual(topic.pk, spec.topic_id)
                expected_content = topic_specs[spec.topic_id].content_bytes
                self.assertEqual(
                    topic.sanitized_html.encode("utf-8"),
                    expected_content,
                )
                response = api.get(
                    f"/api/foundation/help/{spec.ui_key}/"
                    f"?application=STUDIO&locale={CATALOG_LOCALE}&version={CATALOG_VERSION}"
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(
                    response.data,
                    {
                        "stable_key": topic.stable_key,
                        "version": topic.version,
                        "locale": topic.locale,
                        "title": topic.title,
                        "sanitized_html": topic.sanitized_html,
                        "content_sha256": topic.content_sha256,
                    },
                )
                self.assertEqual(
                    hashlib.sha256(response.data["sanitized_html"].encode("utf-8")).hexdigest(),
                    response.data["content_sha256"],
                )
                self.assertEqual(
                    response.data["sanitized_html"].encode("utf-8"),
                    expected_content,
                )
                self.assertEqual(
                    response.data["content_sha256"],
                    topic_specs[spec.topic_id].content_sha256,
                )

        exact_ui_key = catalog.bindings[0].ui_key
        missing_cases = (
            (
                "wrong version",
                HelpApplicationScope.STUDIO,
                exact_ui_key,
                CATALOG_LOCALE,
                "9.9.9",
                {"code": "HELP_TOPIC_NOT_FOUND", "errors": ["No exact HelpTopic binding."]},
            ),
            (
                "wrong locale",
                HelpApplicationScope.STUDIO,
                exact_ui_key,
                "ru-RU",
                CATALOG_VERSION,
                {"code": "HELP_TOPIC_NOT_FOUND", "errors": ["No exact HelpTopic binding."]},
            ),
            (
                "missing ui_key",
                HelpApplicationScope.STUDIO,
                "studio.missing",
                CATALOG_LOCALE,
                CATALOG_VERSION,
                {"code": "HELP_TOPIC_NOT_FOUND", "errors": ["No exact HelpTopic binding."]},
            ),
            (
                "wrong application",
                HelpApplicationScope.PLAYER,
                exact_ui_key,
                CATALOG_LOCALE,
                CATALOG_VERSION,
                {"code": "STUDIO_RESOURCE_NOT_FOUND", "errors": ["Resource not found."]},
            ),
        )
        for label, application, ui_key, locale, version, expected_body in missing_cases:
            with self.subTest(label=label):
                with self.assertRaises(HelpTopicResolutionError):
                    resolve_help_topic(
                        workspace=None,
                        application_scope=application,
                        ui_key=ui_key,
                        locale=locale,
                        version=version,
                    )
                missing = api.get(
                    f"/api/foundation/help/{ui_key}/"
                    f"?application={application}&locale={locale}&version={version}"
                )
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(missing.data, expected_body)
        self.assertEqual((HelpTopic.objects.count(), UIHelpBinding.objects.count()), before)
