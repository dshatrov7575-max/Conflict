import json
from urllib.parse import urlencode
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from calculation import CalculationSnapshot, calculate
from domain.models import AssessmentSet, ParameterValue
from player_integration.tests.test_e2e import PlayerIntegrationHTTPFixture
from scenario_modeling.model import ScenarioModel
from scenario_modeling.session import MAX_AGE


class ScenarioHTTPFixture(PlayerIntegrationHTTPFixture):
    def baseline_response(self, weights=None, **scope):
        weights = self.weights(**scope) if weights is None else weights
        inputs = self.client.get(self.url(**scope))
        weights = {**weights, **{group: {
            identity: weights[group].get(identity, {"status": "UNKNOWN", "value": None,
                                                   "source_id": "", "source_version": ""})
            for identity in identities
        } for group, identities in inputs.context["form"].groups.items()}}
        data = self.form_body(inputs, weights)
        response = self.measured(lambda: self.client.post(
            self.url(**scope), urlencode(data), content_type="application/x-www-form-urlencoded",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value))
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def scenario_post(self, token, action="start", **fields):
        return self.measured(lambda: self.client.post(
            reverse("scenario_modeling:update"),
            urlencode({"scenario_token": token, "action": action, **fields}, doseq=True),
            content_type="application/x-www-form-urlencoded",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value))

    def begin(self, **scope):
        baseline = self.baseline_response(**scope)
        response = self.scenario_post(baseline.context["scenario_token"])
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def change(self, response, value="0", parameter=None):
        parameter = parameter or f"attitude:{self.pair[0].pk}"
        changed = self.scenario_post(response.context["scenario_token"], "set", parameter=parameter, value=value)
        self.assertEqual(changed.status_code, 200, changed.content)
        return changed


class ScenarioHTTPTests(ScenarioHTTPFixture, TestCase):
    def test_create_change_replay_remove_and_reset_without_domain_writes(self):
        self.fill()
        sets = list(AssessmentSet.objects.order_by("pk").values())
        response = self.begin()
        baseline_json = response.context["model"].baseline.to_json()
        self.assertContains(response, 'data-testid="baseline-uno">100</strong>')
        self.assertContains(response, 'data-testid="delta-uno">0</strong>')
        changed = self.change(response)
        self.assertContains(changed, 'data-testid="scenario-uno">0</strong>')
        self.assertContains(changed, 'data-testid="delta-uno">-100</strong>')
        self.assertContains(changed, "POS задаёт сторону")
        self.assertEqual(changed.context["model"].baseline.to_json(), baseline_json)
        token = changed.context["scenario_token"]
        for _ in range(2):
            replay = self.scenario_post(token, "recalculate")
            self.assertEqual(replay.context["scenario_run_json"], changed.context["scenario_run_json"])
            self.assertEqual(replay.context["result_digest"], changed.context["result_digest"])
        for action, fields in (("remove", {"parameter": f"attitude:{self.pair[0].pk}"}), ("reset", {})):
            reset = self.scenario_post(token, action, **fields)
            self.assertEqual(reset.context["model"].overrides, ())
            self.assertEqual(reset.context["delta_uno"], "0")
        self.assertEqual(sets, list(AssessmentSet.objects.order_by("pk").values()))
        snapshot = CalculationSnapshot.from_json(changed.context["scenario_snapshot_json"])
        self.assertEqual(calculate(snapshot).to_json(), changed.context["scenario_run_json"])

    def test_existing_baseline_survives_correction_freeze_and_archive(self):
        self.fill()
        start = self.begin()
        pos = ParameterValue.objects.get(actor_element_assessment__experiment_id=self.experiment_id,
                                         actor_element_assessment__actor_id=self.pair[0].actor_id,
                                         parameter_definition__code="POS", successor__isnull=True)
        self.write_value_http(self.pair[0], "POS", 0, predecessor=str(pos.pk))
        for action in ("freeze", "archive"):
            base = f"/api/foundation/player/experiments/{self.experiment_id}/"
            etag = self.client.get(base).json()["etag"]
            self.assertIn(self.post_json(base + action + "/", {}, etag=etag).status_code, (200, 201))
        changed = self.change(start, "5")
        self.assertEqual(changed.context["baseline"]["UNO"], "100")
        self.assertEqual(changed.context["scenario"]["UNO"], "50")
        self.assertEqual(changed.context["model"].baseline, start.context["model"].baseline)
        self.assertEqual(self.baseline_response().context["run"]["UNO"], "0")

    def test_human_ai_and_separate_scenarios_remain_isolated(self):
        self.fill()
        human = self.begin()
        independent = self.begin()
        ai_id = self.create_experiment_http("AI")
        self.fill(experiment_id=ai_id, attitudes=(0, 0))
        ai = self.begin(experiment_id=ai_id)
        changed = self.change(human, "5")
        for response, expected, kind in ((independent, "100", "HUMAN"), (ai, "0", "AI")):
            replay = self.scenario_post(response.context["scenario_token"], "recalculate")
            self.assertEqual(replay.context["scenario"]["UNO"], expected)
            self.assertContains(replay, f'data-testid="assessment-kind">{kind}</strong>')
            self.assertEqual(replay.context["model"].overrides, ())
        self.assertNotEqual(ai.context["model"].baseline.assessment_set_id, changed.context["model"].baseline.assessment_set_id)
        rejected = self.scenario_post(human.context["scenario_token"], "set", parameter=f"attitude:{self.pair[0].pk}", value="1", experiment_id=ai_id)
        self.assertEqual(rejected.status_code, 400)

    def test_unknown_and_zero_weight_results_keep_missingness(self):
        self.fill()
        weights = {**self.weights(), "rgu": {}, "kvptn": {}}
        unknown = self.begin(weights=weights)
        changed = self.change(unknown, "5")
        self.assertIsNone(changed.context["scenario"]["UNO"])
        self.assertIsNone(changed.context["delta_uno"])
        rejected = self.scenario_post(unknown.context["scenario_token"], "set", parameter=f"rgu:{self.pair[0].actor_id}", value="1")
        self.assertEqual(rejected.status_code, 400)
        weights = self.weights()
        for weight in weights["rgu"].values():
            weight["value"] = "0"
        zero = self.change(self.begin(weights=weights), "5")
        self.assertContains(zero, 'data-testid="scenario-status">NOT_COMPUTABLE</p>')
        self.assertIsNone(zero.context["baseline"]["UNO"])
        self.assertIsNone(zero.context["scenario"]["UNO"])
        self.assertIsNone(zero.context["delta_uno"])

    def test_invalid_values_and_repeated_fields_leave_model_unchanged(self):
        self.fill()
        response = self.begin()
        token = response.context["scenario_token"]
        for value in ("NaN", "1e0", "11", "", "0." + "1" * 33):
            invalid = self.scenario_post(token, "set", parameter=f"attitude:{self.pair[0].pk}", value=value)
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(invalid.context["model"], response.context["model"])
        repeated = self.scenario_post(token, "set", parameter=f"attitude:{self.pair[0].pk}", value=["1", "2"])
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(self.scenario_post(token, "recalculate", value="1").status_code, 400)

    def test_signed_state_tampering_expiry_csrf_and_new_session_are_rejected(self):
        token = self.begin().context["scenario_token"]
        self.assertEqual(self.scenario_post(token + "x").status_code, 400)
        import time
        with patch("django.core.signing.time.time", return_value=time.time() + MAX_AGE + 10):
            self.assertEqual(self.scenario_post(token).status_code, 400)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse("scenario_modeling:update"), {"scenario_token": token, "action": "start"})
        self.assertEqual(response.status_code, 403)
        self.client = client
        self.client.get(self.url())
        self.assertEqual(self.scenario_post(token).status_code, 400)

    def test_current_permissions_are_required_when_replaying_old_scenario(self):
        token = self.begin().context["scenario_token"]
        self.user.user_permissions.clear()
        # Ensure the session does not make a previously admitted model authoritative.
        response = self.scenario_post(token, "recalculate")
        self.assertEqual(response.status_code, 403)

    def test_json_export_is_a_model_not_source_data(self):
        self.fill()
        result = self.change(self.begin(), "5")
        payload = json.loads(result.context["model_json"])
        self.assertEqual(payload["contract"], "SCENARIO_MODEL_V1")
        self.assertEqual(len(payload["overrides"]), 1)
        model = ScenarioModel.from_dict(payload)
        self.assertEqual(calculate(model.baseline).UNO, 100)
        self.assertEqual(model.baseline, result.context["model"].baseline)

    def test_precise_decimal_form_roundtrip_and_oversized_baseline_fallback(self):
        self.fill()
        exact = "0.00000000000000000000000000000001"
        result = self.change(self.begin(), exact, parameter=f"kvs:{self.pair[0].pk}")
        choice = next(row for row in result.context["choices"] if row["key"] == f"kvs:{self.pair[0].pk}")
        self.assertEqual(choice["value"], exact)
        with patch("scenario_modeling.session.MAX_TOKEN_LENGTH", 10):
            baseline = self.baseline_response()
        self.assertIsNone(baseline.context["scenario_token"])
        self.assertEqual(baseline.context["run"]["UNO"], "100")
        self.assertContains(baseline, "Snapshot превышает лимит")
