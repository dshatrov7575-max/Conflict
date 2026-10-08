import json
import threading
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings

from domain.models import ParameterValue
from domain.services.player_experiments import create_manual_value, list_values
from player_integration.inputs import weights_from_json
from player_integration import services
from player_integration.tests.test_e2e import PlayerIntegrationHTTPFixture, TEST_APPS


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL-only idempotency serialization gate",
)
@override_settings(ROOT_URLCONF="player_integration.project_urls", INSTALLED_APPS=TEST_APPS)
class PlayerIntegrationPostgreSQLConcurrencyTests(
    PlayerIntegrationHTTPFixture,
    TransactionTestCase,
):
    """Authoritative READ COMMITTED T1/T2/T3 replay race gate."""

    reset_sequences = True

    def setUp(self):
        # TransactionTestCase does not invoke TestCase.setUpTestData.
        type(self).setUpTestData()
        super().setUp()

    def test_duplicate_replays_t1_across_concurrent_source_correction(self):
        self.fill()
        operation_id = uuid4()
        beta_weights = weights_from_json(json.dumps(self.weights()).encode("utf-8"))

        pos = ParameterValue.objects.get(
            actor_element_assessment__experiment_id=self.experiment_id,
            actor_element_assessment__actor_id=self.pair[0].actor_id,
            parameter_definition__code="POS",
            successor__isnull=True,
        )
        values = list_values(user=self.user, experiment_id=self.experiment_id)["values"]
        predecessor = next(row for row in values if row["id"] == str(pos.pk))
        assessment = pos.actor_element_assessment
        correction_body = {
            "id": str(uuid4()),
            "code": f"PR2-RACE-{uuid4().hex[:12]}",
            "version": "2.0.0",
            "assessment_id": str(uuid4()),
            "assessment_code": f"PR2-RACE-A-{uuid4().hex[:12]}",
            "time_slice_id": str(pos.time_slice_id),
            "actor_code": assessment.actor.code,
            "element_code": assessment.element.code,
            "parameter_code": pos.parameter_definition.code,
            "status": "PROVISIONAL",
            "value": 0,
            "temporal_status": pos.temporal_status,
            "confidence_category": "MEDIUM",
            "rationale": "PostgreSQL T1/T2/T3 serialization probe",
            "note": "",
            "supersedes_id": str(pos.pk),
        }

        t1_inside_project_lock = threading.Event()
        release_t1 = threading.Event()
        wrapper_lock = threading.Lock()
        first_replay_call = {"pending": True}
        original_replay = services.replay_baseline_if_present

        def gated_replay(*args, **kwargs):
            with wrapper_lock:
                block = first_replay_call["pending"]
                if block:
                    first_replay_call["pending"] = False
            if block:
                t1_inside_project_lock.set()
                if not release_t1.wait(15):
                    raise AssertionError("T1 replay gate timed out")
            return original_replay(*args, **kwargs)

        results = {}
        failures = {}
        result_lock = threading.Lock()
        user_id = self.user.pk

        def store(name, fn):
            close_old_connections()
            try:
                value = fn(get_user_model().objects.get(pk=user_id))
                with result_lock:
                    results[name] = value
            except Exception as exc:
                with result_lock:
                    failures[name] = exc
            finally:
                connections.close_all()

        def t1(user):
            return services.calculate_and_record_experiment(
                user=user,
                experiment_id=self.experiment_id,
                time_slice_id=self.time.pk,
                beta_weights=beta_weights,
                operation_id=operation_id,
            )

        def t2(user):
            return create_manual_value(
                user=user,
                experiment_id=self.experiment_id,
                operation_id=str(uuid4()),
                if_match=f'"{predecessor["etag"]}"',
                body=correction_body,
            )

        def t3(user):
            return services.calculate_and_record_experiment(
                user=user,
                experiment_id=self.experiment_id,
                time_slice_id=self.time.pk,
                beta_weights=beta_weights,
                operation_id=operation_id,
            )

        with patch("player_integration.services.replay_baseline_if_present", side_effect=gated_replay):
            first = threading.Thread(target=store, args=("t1", t1), daemon=True)
            first.start()
            self.assertTrue(
                t1_inside_project_lock.wait(15),
                "T1 never reached replay while holding Project lock",
            )

            correction = threading.Thread(target=store, args=("t2", t2), daemon=True)
            duplicate = threading.Thread(target=store, args=("t3", t3), daemon=True)
            correction.start()
            duplicate.start()

            # T2 and T3 should both be waiting behind T1's Project row lock here.
            release_t1.set()
            for thread in (first, correction, duplicate):
                thread.join(30)
                self.assertFalse(thread.is_alive(), "PostgreSQL race exceeded bounded join")

        self.assertEqual(failures, {})
        self.assertEqual(set(results), {"t1", "t2", "t3"})

        t1_view, t1_receipt = results["t1"]
        t3_view, t3_receipt = results["t3"]
        self.assertFalse(t1_receipt.replayed)
        self.assertTrue(t3_receipt.replayed)
        self.assertEqual(t3_view.snapshot.to_json(), t1_view.snapshot.to_json())
        self.assertEqual(t3_view.run.to_json(), t1_view.run.to_json())
        self.assertEqual(t3_view.run.result_digest, t1_view.run.result_digest)
        self.assertEqual(t3_receipt.payload, t1_receipt.payload)

        successor = ParameterValue.objects.get(pk=correction_body["id"])
        self.assertEqual(successor.supersedes_id, pos.pk)
        self.assertEqual(str(successor.value), "0")

        # A genuinely new operation after the correction must see S1, proving
        # that T3 replayed T1/S0 rather than recapturing current source state.
        fresh_view, fresh_receipt = services.calculate_and_record_experiment(
            user=self.user,
            experiment_id=self.experiment_id,
            time_slice_id=self.time.pk,
            beta_weights=beta_weights,
            operation_id=uuid4(),
        )
        self.assertFalse(fresh_receipt.replayed)
        self.assertNotEqual(fresh_view.snapshot.id, t1_view.snapshot.id)
        self.assertNotEqual(fresh_view.run.result_digest, t1_view.run.result_digest)
