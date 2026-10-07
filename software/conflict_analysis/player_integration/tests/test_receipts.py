from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from domain.models import AuditEvent
from player_integration.receipts import (
    BASELINE_RECEIPT_CONTRACT,
    RECEIPT_LIST_CONTRACT,
    SCENARIO_RECEIPT_CONTRACT,
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
        self.assertEqual(receipt["quality"]["contract"], "PLAYER_CALCULATION_QUALITY_V1")
        self.assertEqual(first["quality"]["contract"], "PLAYER_CALCULATION_QUALITY_V2")
        for key, value in receipt["quality"].items():
            if key != "contract":
                self.assertEqual(value, first["quality"][key])
        self.assertIn("temporal_status_counts", first["quality"])
        self.assertEqual(receipt["context"], {
            "kind": "BASELINE",
            "scenario_id": None,
            "baseline_snapshot_id": None,
            "scenario_model_sha256": None,
        })
        self.assertEqual(receipt["payload_storage"], {
            "snapshot_payload_stored": False,
            "run_payload_stored": False,
            "input_values_duplicated": False,
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
            entity_type="PLAYER_CALCULATION_REPLAY_ARTIFACT_V1",
            entity_id=operation_id,
        ).exists())

    def test_replay_artifact_tamper_is_rejected_or_detected_fail_closed(self):
        operation_id = uuid4()
        self.run_json(operation_id=operation_id)
        artifact = AuditEvent.objects.get(
            entity_type="PLAYER_CALCULATION_REPLAY_ARTIFACT_V1",
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
