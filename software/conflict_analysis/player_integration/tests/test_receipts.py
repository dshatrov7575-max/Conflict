from unittest.mock import patch
import json
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from calculation import CalculationSnapshot
from domain.models import AuditEvent
from domain.services.player_experiments import PlayerExperimentError
from domain.services.player_workspaces import canonical_receipt_bytes
from player_integration.receipts import (
    BASELINE_RECEIPT_CONTRACT,
    BASELINE_RECEIPT_CONTRACT_V1,
    RECEIPT_LIST_CONTRACT,
    SCENARIO_RECEIPT_CONTRACT,
    record_calculation_receipt,
)
from player_integration.replay_artifacts import _validate_input_metadata
from player_integration.services import (
    calculate_and_record_experiment,
    calculate_experiment,
    open_experiment,
)
from player_integration.tests.test_e2e import (
    PlayerIntegrationHTTPFixture,
    TEST_APPS,
)


@override_settings(ROOT_URLCONF="player_integration.project_urls", INSTALLED_APPS=TEST_APPS)
class CalculationRunReceiptTests(PlayerIntegrationHTTPFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.fill()

    @staticmethod
    def _keys(value):
        if isinstance(value, dict):
            result = set(value)
            for item in value.values():
                result.update(CalculationRunReceiptTests._keys(item))
            return result
        if isinstance(value, list):
            result = set()
            for item in value:
                result.update(CalculationRunReceiptTests._keys(item))
            return result
        return set()

    @staticmethod
    def _rehash_metadata(payload):
        core = deepcopy(payload)
        core.pop("sha256", None)
        return {
            **core,
            "sha256": sha256(canonical_receipt_bytes(core)).hexdigest(),
        }

    def receipt_list_url(self, experiment_id=None):
        return reverse("player_integration:receipts", kwargs={
            "experiment_id": experiment_id or self.experiment_id,
        })

    def receipt_url(self, operation_id, experiment_id=None):
        return reverse("player_integration:receipt", kwargs={
            "experiment_id": experiment_id or self.experiment_id,
            "operation_id": operation_id,
        })

    def test_create_exact_replay_list_detail_and_append_only_storage(self):
        operation_id = uuid4()
        first = self.run_json(operation_id=operation_id)
        second = self.run_json(
            operation_id=operation_id,
            expected_audit_inserts=0,
        )
        self.assertEqual(first["receipt"], second["receipt"])
        receipt = first["receipt"]
        self.assertEqual(receipt["contract"], BASELINE_RECEIPT_CONTRACT)
        self.assertEqual(receipt["snapshot_id"], first["snapshot"]["id"])
        self.assertEqual(receipt["input_digest"], first["snapshot"]["input_digest"])
        self.assertEqual(receipt["result_digest"], first["result_digest"])
        self.assertEqual(receipt["strategy_id"], first["run"]["strategy_id"])
        self.assertEqual(receipt["quality_contract"], "PLAYER_CALCULATION_QUALITY_V2")
        self.assertEqual(first["quality"]["contract"], "PLAYER_CALCULATION_QUALITY_V2")
        self.assertEqual(receipt["input_metadata_sha256"], first["input_metadata"]["sha256"])
        self.assertEqual(receipt["client_request_sha256"], first["receipt"]["client_request_sha256"])
        self.assertEqual(receipt["companion"]["contract"], "PLAYER_CALCULATION_REPLAY_ARTIFACT_V2")
        self.assertEqual(receipt["companion"]["version"], "2.0.0")
        self.assertIn("temporal_status_counts", first["quality"])
        self.assertEqual(receipt["context"], {
            "kind": "BASELINE",
            "scenario_id": None,
            "baseline_snapshot_id": None,
            "scenario_model_sha256": None,
        })
        self.assertEqual(receipt["payload_storage"], {
            "receipt_snapshot_payload_stored": False,
            "receipt_run_payload_stored": False,
            "receipt_input_values_duplicated": False,
            "companion_replay_payload_required": True,
        })
        self.assertTrue({
            "snapshot", "run", "ptns", "actors", "trace", "overrides",
            "values", "input_values", "parameter_values", "scenario_model",
        }.isdisjoint(self._keys(receipt)))

        listed = self.measured(lambda: self.client.get(self.receipt_list_url()))
        self.assertEqual(listed.status_code, 200, listed.content)
        listing = listed.json()
        self.assertEqual(listing["contract"], RECEIPT_LIST_CONTRACT)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["receipts"], [receipt])
        detail = self.measured(lambda: self.client.get(self.receipt_url(operation_id)))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json(), receipt)

        row = AuditEvent.objects.get(pk=operation_id)
        self.assertEqual(row.entity_type, BASELINE_RECEIPT_CONTRACT)
        row.after = {**row.after, "result_digest": "0" * 64}
        with self.assertRaises(ValidationError):
            row.save(update_fields=["after", "updated_at"])
        with self.assertRaises(ValidationError):
            AuditEvent.objects.filter(pk=operation_id).update(after={})
        with self.assertRaises(ValidationError):
            AuditEvent.objects.filter(pk=operation_id).delete()

    def test_metadata_envelope_semantics_reject_missing_duplicate_and_mutation(self):
        result = self.run_json()
        snapshot = CalculationSnapshot.from_json(json.dumps(result["snapshot"]))
        valid = result["input_metadata"]
        self.assertEqual(_validate_input_metadata(valid, snapshot), valid)

        missing = deepcopy(valid)
        missing["inputs"].pop()
        missing = self._rehash_metadata(missing)

        duplicate = deepcopy(valid)
        duplicate["inputs"].append(deepcopy(duplicate["inputs"][0]))
        duplicate = self._rehash_metadata(duplicate)

        mutated = deepcopy(valid)
        target = next(
            row for row in mutated["inputs"]
            if row["kind"] == "POS" and row["actor_id"] is not None
        )
        target["actor_id"] = str(uuid4())
        mutated = self._rehash_metadata(mutated)

        for candidate in (missing, duplicate, mutated):
            with self.subTest(candidate=candidate["sha256"]):
                with self.assertRaises(PlayerExperimentError) as error:
                    _validate_input_metadata(candidate, snapshot)
                self.assertEqual(
                    error.exception.code, "PLAYER_OPERATION_RESULT_DRIFT",
                )

    def test_legacy_v1_receipt_without_companion_remains_readable_and_replayable(self):
        operation_id = uuid4()
        view = calculate_experiment(
            user=self.user,
            experiment_id=self.experiment_id,
            time_slice_id=self.time.pk,
        )
        experiment = open_experiment(
            user=self.user, experiment_id=self.experiment_id,
        )
        legacy = record_calculation_receipt(
            user=self.user,
            experiment=experiment,
            snapshot=view.snapshot,
            run=view.run,
            quality=view.legacy_quality,
            operation_id=operation_id,
            context_kind="BASELINE",
        )
        self.assertEqual(
            legacy.payload["contract"], BASELINE_RECEIPT_CONTRACT_V1,
        )
        detail = self.client.get(self.receipt_url(operation_id))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["contract"], BASELINE_RECEIPT_CONTRACT_V1)

        replay_view, replay_receipt = calculate_and_record_experiment(
            user=self.user,
            experiment_id=self.experiment_id,
            time_slice_id=self.time.pk,
            operation_id=operation_id,
            beta_weights=None,
        )
        self.assertTrue(replay_receipt.replayed)
        self.assertEqual(
            replay_receipt.payload["contract"], BASELINE_RECEIPT_CONTRACT_V1,
        )
        self.assertEqual(replay_view.run.result_digest, view.run.result_digest)
        self.assertFalse(AuditEvent.objects.filter(
            entity_type="PLAYER_CALCULATION_REPLAY_ARTIFACT_V2",
            entity_id=operation_id,
        ).exists())

    def test_v2_missing_companion_is_corruption_not_legacy(self):
        operation_id = uuid4()
        created = self.run_json(operation_id=operation_id)
        artifact_id = created["receipt"]["companion"]["id"]
        artifact_code = f"CALC-REPLAY-{operation_id}"
        self.assertEqual(
            str(AuditEvent.objects.get(code=artifact_code).pk),
            artifact_id,
        )

        if connection.vendor == "postgresql":
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM domain_auditevent WHERE code = %s",
                        [artifact_code],
                    )
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM domain_auditevent WHERE code = %s",
                    [artifact_code],
                )
            self.assertFalse(AuditEvent.objects.filter(code=artifact_code).exists())
            conflict = self.measured(lambda: self.post_json(
                self.url(), self.weights(), operation_id=operation_id,
            ))
            self.assertEqual(conflict.status_code, 409, conflict.content)
            self.assertEqual(
                conflict.json()["code"], "PLAYER_OPERATION_RESULT_DRIFT",
            )

    def test_raw_sql_tamper_is_rejected_or_detected_fail_closed(self):
        operation_id = uuid4()
        created = self.run_json(operation_id=operation_id)
        code = f"CALC-RUN-{operation_id}"
        original_actor = AuditEvent.objects.get(pk=operation_id).actor_identifier

        if connection.vendor == "postgresql":
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE domain_auditevent "
                        "SET actor_identifier = %s WHERE code = %s",
                        ["tampered-actor", code],
                    )
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM domain_auditevent WHERE code = %s",
                        [code],
                    )
            row = AuditEvent.objects.get(pk=operation_id)
            self.assertEqual(row.actor_identifier, original_actor)
            detail = self.client.get(self.receipt_url(operation_id))
            self.assertEqual(detail.status_code, 200, detail.content)
            self.assertEqual(detail.json(), created["receipt"])
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE domain_auditevent "
                    "SET actor_identifier = %s WHERE code = %s",
                    ["tampered-actor", code],
                )
            detail = self.client.get(self.receipt_url(operation_id))
            self.assertEqual(detail.status_code, 409, detail.content)
            self.assertEqual(
                detail.json()["code"],
                "PLAYER_OPERATION_RESULT_DRIFT",
            )

        self.assertEqual(created["receipt"]["operation_id"], str(operation_id))


    def test_receipt_and_replay_artifact_are_one_outer_transaction(self):
        operation_id = uuid4()
        with patch(
            "player_integration.services.record_replay_artifact",
            side_effect=DatabaseError("forced artifact failure"),
        ):
            response = self.post_json(
                self.url(), self.weights(), operation_id=operation_id,
            )
        self.assertEqual(response.status_code, 503, response.content)
        self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())
        self.assertFalse(AuditEvent.objects.filter(
            entity_type="PLAYER_CALCULATION_REPLAY_ARTIFACT_V2",
            entity_id=operation_id,
        ).exists())

    def test_replay_artifact_tamper_is_rejected_or_detected_fail_closed(self):
        operation_id = uuid4()
        self.run_json(operation_id=operation_id)
        artifact = AuditEvent.objects.get(
            entity_type="PLAYER_CALCULATION_REPLAY_ARTIFACT_V2",
            entity_id=operation_id,
        )

        if connection.vendor == "postgresql":
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE domain_auditevent "
                        "SET actor_identifier = %s WHERE code = %s",
                        ["tampered-artifact", artifact.code],
                    )
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE domain_auditevent "
                    "SET actor_identifier = %s WHERE code = %s",
                    ["tampered-artifact", artifact.code],
                )
            conflict = self.measured(lambda: self.post_json(
                self.url(), self.weights(), operation_id=operation_id,
            ))
            self.assertEqual(conflict.status_code, 409, conflict.content)
            self.assertEqual(conflict.json()["code"], "PLAYER_OPERATION_RESULT_DRIFT")

    def test_exact_replay_does_not_revalidate_current_time_slice(self):
        operation_id = uuid4()
        first = self.run_json(operation_id=operation_id)
        with patch(
            "player_integration.services.TimeSlice.objects.filter",
            side_effect=AssertionError("exact replay must not recapture current TimeSlice"),
        ):
            second = self.run_json(
                operation_id=operation_id,
                expected_audit_inserts=0,
            )
        self.assertEqual(second["snapshot"], first["snapshot"])
        self.assertEqual(second["run"], first["run"])

    def test_operation_key_reuse_cross_lane_scope_and_corruption_fail_closed(self):
        operation_id = uuid4()
        created = self.run_json(operation_id=operation_id)
        changed = self.weights()
        first_actor = next(iter(changed["rgu"]))
        changed["rgu"][first_actor]["value"] = "2"
        conflict = self.measured(lambda: self.post_json(
            self.url(), changed, operation_id=operation_id,
        ))
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(conflict.json()["code"], "PLAYER_OPERATION_KEY_REUSE")

        ai_id = self.create_experiment_http("AI")
        hidden = self.measured(lambda: self.client.get(
            self.receipt_url(operation_id, experiment_id=ai_id),
        ))
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json()["code"], "PLAYER_NOT_FOUND")
        cross_lane = self.measured(lambda: self.post_json(
            self.url(experiment_id=ai_id),
            self.weights(experiment_id=ai_id),
            operation_id=operation_id,
        ))
        self.assertEqual(cross_lane.status_code, 409, cross_lane.content)
        self.assertEqual(cross_lane.json()["code"], "PLAYER_OPERATION_KEY_REUSE")

        source_row = AuditEvent.objects.exclude(entity_type__in={
            BASELINE_RECEIPT_CONTRACT, SCENARIO_RECEIPT_CONTRACT,
        }).first()
        self.assertIsNotNone(source_row)
        unrelated = self.measured(lambda: self.post_json(
            self.url(), self.weights(), operation_id=source_row.pk,
        ))
        self.assertEqual(unrelated.status_code, 409)
        self.assertEqual(unrelated.json()["code"], "PLAYER_OPERATION_KEY_REUSE")

        self.assertEqual(
            AuditEvent.objects.get(pk=operation_id).after["receipt_sha256"],
            created["receipt"]["receipt_sha256"],
        )

    def test_invalid_operation_identity_and_denied_scope_never_create_receipts(self):
        before = AuditEvent.objects.count()
        for value in ("", "not-a-uuid", str(uuid4()).upper()):
            response = self.client.post(
                self.url(),
                data="{}",
                content_type="application/json",
                HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
                HTTP_IDEMPOTENCY_KEY=value,
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditEvent.objects.count(), before)

        self.user.groups.clear()
        denied = self.client.get(self.receipt_list_url())
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(AuditEvent.objects.count(), before)
