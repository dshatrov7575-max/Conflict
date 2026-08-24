from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from domain.enums import PublicationStatus
from domain.models import Actor, AuditEvent, ImportRun, ProjectDefinitionVersion, ProjectWorkspace
from domain.services.foundation_packages import (
    FoundationPackageConflictError,
    attempt_foundation_import,
    canonical_json,
    commit_foundation_package,
    preview_foundation_package,
    seal_foundation_package,
)
from domain.tests.test_v4_foundation_contracts import (
    FoundationFactoryMixin,
    clean_save,
    manifest_hash,
    minimal_foundation_package,
)


class FoundationP1ImportCorrectionTests(FoundationFactoryMixin, TestCase):
    actor_id = "41000000-0000-4000-8000-000000000001"

    def setUp(self) -> None:
        self.make_foundation(suffix="P1")

    def package_with_intended_actor_create(self) -> dict:
        package = minimal_foundation_package(self.workspace)
        package["actors"] = [
            {
                "id": self.actor_id,
                "code": "ACTOR-P1-INTENDED",
                "version": "4.0.0",
                "metadata": {"fixture": "p1-lock-conflict"},
                "parent_code": None,
                "actor_type": "GROUP",
                "label": "P1 intended create",
                "description": "Must not be written after preview drift.",
                "order": 0,
            }
        ]
        return seal_foundation_package(package)

    def test_commit_rejects_workspace_code_changed_after_preview_before_any_write(self):
        preview = preview_foundation_package(
            self.package_with_intended_actor_create(),
            workspace=self.workspace,
        )
        ProjectWorkspace.objects.filter(pk=self.workspace.pk).update(
            code="WORKSPACE-P1-DRIFT"
        )
        before = (Actor.objects.count(), ImportRun.objects.count(), AuditEvent.objects.count())

        with self.assertRaisesRegex(
            FoundationPackageConflictError,
            "Locked workspace identity differs",
        ):
            commit_foundation_package(
                preview,
                workspace=self.workspace,
                actor_identifier="fixture:p1-stale-code",
            )

        self.assertEqual(
            (Actor.objects.count(), ImportRun.objects.count(), AuditEvent.objects.count()),
            before,
        )
        self.assertFalse(Actor.objects.filter(pk=self.actor_id).exists())
        self.assertFalse(ImportRun.objects.filter(status="COMMITTED").exists())

    def test_commit_rejects_workspace_definition_pin_drift_after_preview_before_any_write(self):
        preview = preview_foundation_package(
            self.package_with_intended_actor_create(),
            workspace=self.workspace,
        )
        next_manifest = {
            "ontology_version": "4.0.1",
            "project": self.project.code,
        }
        lifecycle_time = timezone.now()
        next_definition = clean_save(
            ProjectDefinitionVersion(
                project=self.project,
                code="DEF-P1-DRIFT",
                version="4.0.1",
                publication_status=PublicationStatus.PUBLISHED,
                manifest=next_manifest,
                manifest_hash=manifest_hash(next_manifest),
                validated_at=lifecycle_time,
                validated_by="fixture:p1-owner",
                validation_result={"valid": True},
                published_at=lifecycle_time,
                published_by="fixture:p1-owner",
                supersedes=self.definition,
            )
        )
        ProjectWorkspace._base_manager.filter(pk=self.workspace.pk).update(
            definition_version=next_definition,
            definition_manifest_hash=next_definition.manifest_hash,
        )
        before = (Actor.objects.count(), ImportRun.objects.count(), AuditEvent.objects.count())

        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package(
                preview,
                workspace=self.workspace,
                actor_identifier="fixture:p1-definition-drift",
            )

        self.assertEqual(
            (Actor.objects.count(), ImportRun.objects.count(), AuditEvent.objects.count()),
            before,
        )
        self.assertFalse(Actor.objects.filter(pk=self.actor_id).exists())
        self.assertFalse(ImportRun.objects.filter(status="COMMITTED").exists())

    def test_no_drift_commit_succeeds_with_mapping_provenance(self):
        package = minimal_foundation_package(self.workspace)
        expected_raw_sha256 = hashlib.sha256(
            canonical_json(package).encode("utf-8")
        ).hexdigest()
        preview = preview_foundation_package(
            package,
            workspace=self.workspace,
            selected_input={
                "raw_input_kind": "PATH_BYTES",
                "raw_input_sha256": "0" * 64,
            },
        )

        receipt = commit_foundation_package(
            preview,
            workspace=self.workspace,
            actor_identifier="fixture:p1-no-drift",
        )

        self.assertEqual(preview.raw_input_kind, "CANONICAL_MAPPING")
        self.assertEqual(preview.raw_input_sha256, expected_raw_sha256)
        self.assertEqual(receipt.raw_input_kind, "CANONICAL_MAPPING")
        self.assertEqual(receipt.raw_input_sha256, expected_raw_sha256)
        self.assertEqual(receipt.checksum, preview.checksum)
        run = ImportRun.objects.get(pk=receipt.id)
        self.assertEqual(run.status, "COMMITTED")
        self.assertEqual(run.selected_input["raw_input_kind"], "CANONICAL_MAPPING")
        self.assertEqual(run.selected_input["raw_input_sha256"], expected_raw_sha256)

    def test_text_whitespace_changes_raw_sha_but_not_semantic_checksum(self):
        package = minimal_foundation_package(self.workspace)
        pretty = json.dumps(package, ensure_ascii=False, indent=2)
        compact = json.dumps(
            package,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        pretty_preview = preview_foundation_package(pretty, workspace=self.workspace)
        compact_preview = preview_foundation_package(compact, workspace=self.workspace)

        self.assertEqual(pretty_preview.checksum, compact_preview.checksum)
        self.assertEqual(pretty_preview.raw_input_kind, "TEXT")
        self.assertEqual(compact_preview.raw_input_kind, "TEXT")
        self.assertEqual(
            pretty_preview.raw_input_sha256,
            hashlib.sha256(pretty.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            compact_preview.raw_input_sha256,
            hashlib.sha256(compact.encode("utf-8")).hexdigest(),
        )
        self.assertNotEqual(
            pretty_preview.raw_input_sha256,
            compact_preview.raw_input_sha256,
        )

        receipt = commit_foundation_package(
            pretty_preview,
            workspace=self.workspace,
            actor_identifier="fixture:p1-text-provenance",
        )
        self.assertEqual(receipt.checksum, pretty_preview.checksum)
        self.assertEqual(receipt.raw_input_kind, "TEXT")
        self.assertEqual(receipt.raw_input_sha256, pretty_preview.raw_input_sha256)

    def test_bytes_and_path_capture_exact_bytes_and_commit_uses_frozen_snapshot(self):
        raw_bytes = json.dumps(
            minimal_foundation_package(self.workspace),
            ensure_ascii=False,
            indent=1,
        ).encode("utf-8")
        expected_raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        bytes_preview = preview_foundation_package(raw_bytes, workspace=self.workspace)

        with tempfile.TemporaryDirectory() as temporary_directory:
            package_path = Path(temporary_directory) / "foundation-p1.json"
            package_path.write_bytes(raw_bytes)
            path_preview = preview_foundation_package(
                package_path,
                workspace=self.workspace,
            )
            string_path_preview = preview_foundation_package(
                str(package_path),
                workspace=self.workspace,
            )

            self.assertEqual(bytes_preview.checksum, path_preview.checksum)
            self.assertEqual(path_preview.checksum, string_path_preview.checksum)
            self.assertEqual(bytes_preview.raw_input_kind, "BYTES")
            self.assertEqual(path_preview.raw_input_kind, "PATH_BYTES")
            self.assertEqual(string_path_preview.raw_input_kind, "PATH_BYTES")
            self.assertEqual(bytes_preview.raw_input_sha256, expected_raw_sha256)
            self.assertEqual(path_preview.raw_input_sha256, expected_raw_sha256)
            self.assertEqual(string_path_preview.raw_input_sha256, expected_raw_sha256)
            self.assertEqual(path_preview.raw_input_name, package_path.name)

            package_path.write_text("not the previewed package", encoding="utf-8")
            receipt = commit_foundation_package(
                path_preview,
                workspace=self.workspace,
                actor_identifier="fixture:p1-path-snapshot",
            )

        self.assertEqual(receipt.checksum, path_preview.checksum)
        self.assertEqual(receipt.raw_input_kind, "PATH_BYTES")
        self.assertEqual(receipt.raw_input_sha256, expected_raw_sha256)
        self.assertEqual(receipt.raw_input_name, "foundation-p1.json")
        run = ImportRun.objects.get(pk=receipt.id)
        self.assertEqual(run.selected_input["raw_input_sha256"], expected_raw_sha256)
        self.assertEqual(run.selected_input["raw_input_kind"], "PATH_BYTES")

    def test_bytes_commit_receipt_preserves_exact_supplied_bytes_provenance(self):
        raw_bytes = json.dumps(
            minimal_foundation_package(self.workspace),
            ensure_ascii=False,
            indent=3,
        ).encode("utf-8")
        expected_raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        preview = preview_foundation_package(raw_bytes, workspace=self.workspace)

        receipt = commit_foundation_package(
            preview,
            workspace=self.workspace,
            actor_identifier="fixture:p1-bytes-provenance",
        )

        self.assertEqual(receipt.checksum, preview.checksum)
        self.assertEqual(receipt.raw_input_kind, "BYTES")
        self.assertEqual(receipt.raw_input_sha256, expected_raw_sha256)
        self.assertEqual(receipt.selected_input["raw_input_kind"], "BYTES")
        self.assertEqual(
            receipt.selected_input["raw_input_sha256"],
            expected_raw_sha256,
        )

    def test_rejected_string_path_receipt_uses_file_bytes_not_path_text(self):
        invalid_bytes = b'{"format":"not-a-foundation-package"}\n'
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_path = Path(temporary_directory) / "invalid-foundation-p1.json"
            package_path.write_bytes(invalid_bytes)

            attempt = attempt_foundation_import(
                str(package_path),
                workspace=self.workspace,
                actor_identifier="fixture:p1-rejected-path",
            )

        self.assertEqual(attempt.status, "REJECTED")
        self.assertIsNotNone(attempt.receipt)
        assert attempt.receipt is not None
        self.assertEqual(attempt.receipt.raw_input_kind, "PATH_BYTES")
        self.assertEqual(
            attempt.receipt.raw_input_sha256,
            hashlib.sha256(invalid_bytes).hexdigest(),
        )

    def test_post_rollback_receipt_keeps_preview_raw_sha_separate_from_semantic_sha(self):
        raw_text = json.dumps(
            self.package_with_intended_actor_create(),
            ensure_ascii=False,
            indent=4,
        )
        expected_raw_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        attempt = attempt_foundation_import(
            raw_text,
            workspace=self.workspace,
            actor_identifier="fixture:p1-rollback-receipt",
            inject_failure_after=1,
        )

        self.assertEqual(attempt.status, "REJECTED")
        self.assertIsNotNone(attempt.report.preview)
        self.assertIsNotNone(attempt.receipt)
        assert attempt.report.preview is not None
        assert attempt.receipt is not None
        self.assertEqual(attempt.report.preview.raw_input_kind, "TEXT")
        self.assertEqual(attempt.report.preview.raw_input_sha256, expected_raw_sha256)
        self.assertEqual(attempt.receipt.raw_input_kind, "TEXT")
        self.assertEqual(attempt.receipt.raw_input_sha256, expected_raw_sha256)
        self.assertEqual(attempt.receipt.checksum, attempt.report.preview.checksum)
        self.assertNotEqual(attempt.receipt.raw_input_sha256, attempt.receipt.checksum)
        self.assertFalse(Actor.objects.filter(pk=self.actor_id).exists())
        self.assertFalse(ImportRun.objects.filter(status="COMMITTED").exists())
