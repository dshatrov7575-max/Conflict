"""Full HTTP -> Foundation -> Core -> HTML/JSON flows; no calculation mocks.

Only fixture setup writes assessments, via the existing Foundation HTTP API.
Every measured integration request must leave all domain records unchanged.
"""
import json
import re
from urllib.parse import urlencode
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from calculation import CalculationSnapshot, calculate
from domain.models import ActorElementRole, ParameterValue, TimeSlice
from domain.services import zhanaozen_typed_manifest as typed
from domain.services.player_experiments import PlayerExperimentError
from domain.tests.test_player_experiments import PlayerExperimentsFixture
from player_integration.services import calculate_experiment


TEST_APPS = [*settings.INSTALLED_APPS, *(
    [] if "player_integration.apps.PlayerIntegrationConfig" in settings.INSTALLED_APPS
    else ["player_integration.apps.PlayerIntegrationConfig"]
)]


class PlayerIntegrationHTTPFixture(PlayerExperimentsFixture):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.workspace_url = f"/api/foundation/player/workspaces/{self.workspace.pk}/experiments/"
        self.assertEqual(self.client.get(self.workspace_url).status_code, 200)
        self.experiment_id = self.create_experiment_http("HUMAN")
        self.time = TimeSlice.objects.filter(workspace=self.workspace).order_by("order", "pk").first()
        self.roles = list(ActorElementRole.objects.filter(workspace=self.workspace)
                          .select_related("actor", "element").order_by("element_id", "actor_id"))
        self.ptn = self.roles[0].element_id
        self.pair = [row for row in self.roles if row.element_id == self.ptn][:2]

    def post_json(self, url, body, *, etag=None):
        headers = {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}
        if etag is not None:
            headers.update(HTTP_IF_MATCH=f'"{etag}"', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        return self.client.post(url, json.dumps(body), content_type="application/json", **headers)

    def create_experiment_http(self, kind):
        experiment_id, body = self.aggregate_body(kind=kind)
        response = self.post_json(self.workspace_url, body, etag=typed.MANIFEST_SHA256)
        self.assertEqual(response.status_code, 201, response.content)
        return experiment_id

    def values_url(self, experiment_id=None):
        return f"/api/foundation/player/experiments/{experiment_id or self.experiment_id}/values/"

    def write_value_http(self, role, code, value, *, experiment_id=None, predecessor=None):
        url = self.values_url(experiment_id)
        dto = self.client.get(url).json()
        etag = dto["experiment"]["etag"] if predecessor is None else next(
            row["etag"] for row in dto["values"] if row["id"] == predecessor)
        body = {
            "id": str(uuid4()), "code": f"PR2-V-{uuid4().hex[:12]}",
            "version": "1.0.0" if predecessor is None else "2.0.0",
            "assessment_id": str(uuid4()), "assessment_code": f"PR2-A-{uuid4().hex[:12]}",
            "time_slice_id": str(self.time.pk), "actor_code": role.actor.code,
            "element_code": role.element.code, "parameter_code": code,
            "status": "UNKNOWN" if value is None else "PROVISIONAL", "value": value,
            "temporal_status": "UNKNOWN", "confidence_category": "MEDIUM",
            "rationale": "Synthetic PR-2 E2E input", "note": "", "supersedes_id": predecessor,
        }
        response = self.post_json(url, body, etag=etag)
        self.assertEqual(response.status_code, 201, response.content)
        return body["id"]

    def fill(self, *, experiment_id=None, attitudes=(10, -10), all_rows=False):
        roles = self.roles if all_rows else self.pair
        for index, role in enumerate(roles):
            self.write_value_http(role, "POS", attitudes[index % len(attitudes)], experiment_id=experiment_id)
            self.write_value_http(role, "SAL", 1, experiment_id=experiment_id)

    def weights(self, *, experiment_id=None, time_slice_id=None, all_ptns=False):
        def known(value, source):
            return {"status": "PROVISIONAL", "value": str(value), "source_id": source, "source_version": "1"}
        return {
            "experiment_id": str(experiment_id or self.experiment_id),
            "time_slice_id": str(time_slice_id or self.time.pk),
            "rgu": {str(row.actor_id): known(1, f"beta-rgu-{row.actor_id}") for row in self.roles},
            "kvptn": {str(row.element_id): known(int(all_ptns or row.element_id == self.ptn),
                                                f"beta-q-{row.element_id}") for row in self.roles},
        }

    def url(self, *, experiment_id=None, time_slice_id=None):
        return reverse("player_integration:result", kwargs={
            "experiment_id": experiment_id or self.experiment_id,
            "time_slice_id": time_slice_id or self.time.pk,
        })

    def measured(self, action):
        before = list(ParameterValue.objects.order_by("pk").values())
        with CaptureQueriesContext(connection) as queries:
            response = action()
        self.assertFalse([row["sql"] for row in queries if re.match(
            r"\s*(INSERT|UPDATE|DELETE)\b", row["sql"], re.IGNORECASE)])
        self.assertEqual(before, list(ParameterValue.objects.order_by("pk").values()))
        self.assertEqual(response["Cache-Control"], "no-store")
        return response

    def run_json(self, weights=None, **scope):
        response = self.measured(lambda: self.post_json(
            self.url(**scope), self.weights(**scope) if weights is None else weights))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        snapshot = CalculationSnapshot.from_json(json.dumps(payload["snapshot"]))
        replay = calculate(snapshot)
        self.assertEqual(json.loads(replay.to_json()), payload["run"])
        self.assertEqual(replay.result_digest, payload["result_digest"])
        return payload

    def form_body(self, response, weights):
        form = response.context["form"]
        data = {"experiment_id": weights["experiment_id"], "time_slice_id": weights["time_slice_id"]}
        for group, identities in form.groups.items():
            for identity in identities:
                for name, value in weights[group][identity].items():
                    data[f"{group}.{identity}.{name}"] = "" if value is None else value
        return data

    def post_form(self, data):
        return self.client.post(self.url(), urlencode(data, doseq=True),
                                content_type="application/x-www-form-urlencoded",
                                HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)


@override_settings(ROOT_URLCONF="player_integration.project_urls", INSTALLED_APPS=TEST_APPS)
class PlayerIntegrationE2ETests(PlayerIntegrationHTTPFixture, TestCase):
    def test_select_experiment_time_calculate_and_render_trace_without_writes(self):
        self.fill()
        start = self.measured(lambda: self.client.get(reverse("player_integration:start")))
        self.assertContains(start, "Идентификатор эксперимента")
        selected = self.client.get(reverse("player_integration:start"), {"experiment_id": self.experiment_id})
        self.assertEqual(selected.status_code, 302)
        selection = self.measured(lambda: self.client.get(selected["Location"]))
        self.assertContains(selection, self.url())
        inputs = self.measured(lambda: self.client.get(self.url()))
        response = self.measured(lambda: self.post_form(self.form_body(inputs, self.weights())))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, 'data-testid="uno">100</span>')
        self.assertContains(response, 'data-testid="assessment-kind">HUMAN</strong>')
        self.assertContains(response, 'data-testid="run-status">PARTIAL</strong>')
        self.assertContains(response, "KVS_KVPTN_DEPENDENCE_NOT_VALIDATED")
        self.assertContains(response, "Трассировка входов и вкладов")
        snapshot = CalculationSnapshot.from_json(response.context["snapshot_json"])
        with self.assertNumQueries(0):
            self.assertEqual(calculate(snapshot).to_json(), response.context["run_json"])
        for value in ParameterValue.objects.filter(assessment_set_id=snapshot.assessment_set_id):
            self.assertContains(response, str(value.pk))
        self.assertEqual(response.context["run"]["snapshot_id"], snapshot.id)

    def test_full_topology_complete_result(self):
        self.fill(all_rows=True)
        result = self.run_json(self.weights(all_ptns=True))
        self.assertEqual(result["run"]["status"], "COMPLETE")
        self.assertEqual(result["run"]["UNO"], "100")
        self.assertEqual(result["run"]["completeness"]["eligible_rows"], len(self.roles))

    def test_human_and_ai_are_independent_for_equal_and_different_inputs(self):
        self.fill()
        human = self.run_json()
        ai_id = self.create_experiment_http("AI")
        empty_ai = self.run_json(experiment_id=ai_id)
        self.assertEqual(empty_ai["lane"]["assessment_kind"], "AI")
        self.assertIsNone(empty_ai["run"]["UNO"])
        self.assertEqual(empty_ai["run"]["completeness"]["eligible_rows"], 0)
        self.fill(experiment_id=ai_id)
        equal_ai = self.run_json(experiment_id=ai_id)
        self.assertEqual(equal_ai["run"]["UNO"], human["run"]["UNO"])
        self.assertNotEqual(equal_ai["snapshot"]["id"], human["snapshot"]["id"])
        current = self.client.get(self.values_url(ai_id)).json()["values"]
        pos = next(row for row in current if row["parameter_code"] == "POS")
        role = next(row for row in self.pair if row.actor.code == pos["actor_code"])
        self.write_value_http(role, "POS", 0, experiment_id=ai_id, predecessor=pos["id"])
        self.assertEqual(self.run_json(experiment_id=ai_id)["run"]["UNO"], "0")
        self.assertEqual(self.run_json(), human)

    def test_missing_weights_stay_unknown_and_are_not_filled(self):
        self.fill()
        weights = {**self.weights(), "rgu": {}, "kvptn": {}}
        result = self.run_json(weights)
        self.assertIsNone(result["run"]["UNO"])
        self.assertEqual(result["run"]["status"], "NOT_COMPUTABLE")
        self.assertEqual(result["run"]["completeness"]["eligible_rows"], 0)
        self.assertIn("MISSING_PTN_WEIGHT", result["run"]["warnings"])
        for ptn in result["snapshot"]["ptns"]:
            self.assertEqual(ptn["kvptn"]["source_id"], "ABSENT")
            self.assertIsNone(ptn["kvptn"]["value"])

    def test_neutral_zero_is_visible_and_distinct_from_noncomputable(self):
        self.fill(attitudes=(0, 0))
        result = self.run_json()
        self.assertEqual(result["run"]["UNO"], "0")
        inputs = self.client.get(self.url())
        response = self.post_form(self.form_body(inputs, self.weights()))
        self.assertContains(response, 'data-testid="uno">0</span>')
        weights = self.weights()
        for weight in weights["rgu"].values():
            weight["value"] = "0"
        self.assertIsNone(self.run_json(weights)["run"]["UNO"])
        response = self.post_form(self.form_body(inputs, weights))
        self.assertContains(response, 'data-testid="uno">Недостаточно данных</span>')

    def test_missing_one_ptn_weight_blocks_area_but_retains_ptn_metrics(self):
        self.fill()
        weights = self.weights()
        del weights["kvptn"][next(key for key in weights["kvptn"] if key != str(self.ptn))]
        result = self.run_json(weights)
        self.assertIsNone(result["run"]["UNO"])
        self.assertEqual(next(row["Pol"] for row in result["run"]["ptns"] if row["ptn_id"] == str(self.ptn)), "100")

    def test_correction_changes_new_snapshot_and_old_result_replays_after_archive(self):
        self.fill()
        before = self.run_json()
        pos = ParameterValue.objects.get(actor_element_assessment__experiment_id=self.experiment_id,
                                         actor_element_assessment__actor_id=self.pair[0].actor_id,
                                         parameter_definition__code="POS", successor__isnull=True)
        successor_id = self.write_value_http(self.pair[0], "POS", None, predecessor=str(pos.pk))
        corrected = self.run_json()
        self.assertNotEqual(corrected["snapshot"]["id"], before["snapshot"]["id"])
        self.assertEqual(corrected["run"]["UNO"], "0")
        row = next(actor for ptn in corrected["snapshot"]["ptns"] if ptn["ptn_id"] == str(self.ptn)
                   for actor in ptn["actors"] if actor["actor_id"] == str(self.pair[0].actor_id))
        self.assertEqual(row["attitude"]["source_id"], successor_id)
        self.assertEqual(row["attitude"]["source_version"], "2.0.0")
        self.assertEqual(row["kvs"]["value"], "1")
        base = f"/api/foundation/player/experiments/{self.experiment_id}/"
        for action, status in (("freeze", "FROZEN"), ("archive", "ARCHIVED")):
            etag = self.client.get(base).json()["etag"]
            response = self.post_json(base + action + "/", {}, etag=etag)
            self.assertIn(response.status_code, (200, 201), response.content)
            current = self.run_json()
            self.assertEqual(current["lane"]["experiment_status"], status)
            self.assertEqual(current["run"], corrected["run"])
        with self.assertNumQueries(0):
            replay = calculate(CalculationSnapshot.from_json(json.dumps(before["snapshot"])))
            self.assertEqual(replay.UNO, 100)
            self.assertEqual(replay.result_digest, before["result_digest"])

    def test_other_time_slice_does_not_borrow_values(self):
        self.fill()
        other = TimeSlice.objects.filter(workspace=self.workspace).exclude(pk=self.time.pk).first()
        self.assertIsNotNone(other)
        result = self.run_json(time_slice_id=other.pk)
        self.assertIsNone(result["run"]["UNO"])
        self.assertEqual(result["run"]["completeness"]["eligible_rows"], 0)

    def test_cross_lane_time_and_topology_weights_rejected_without_writes(self):
        for patch in ({"experiment_id": str(uuid4())}, {"time_slice_id": str(uuid4())},
                      {"rgu": {str(uuid4()): next(iter(self.weights()["rgu"].values()))}}):
            with self.subTest(patch=patch):
                response = self.measured(lambda: self.post_json(self.url(), {**self.weights(), **patch}))
                self.assertEqual(response.status_code, 400)
        response = self.measured(lambda: self.post_json(self.url(time_slice_id=uuid4()), self.weights()))
        self.assertEqual(response.status_code, 404)

    def test_session_and_existing_foundation_scope_are_required(self):
        anonymous = Client()
        self.assertEqual(anonymous.get(self.url()).status_code, 401)
        with self.assertRaises(PlayerExperimentError):
            calculate_experiment(user=AnonymousUser(), experiment_id=self.experiment_id, time_slice_id=self.time.pk)
        self.user.groups.clear()
        response = self.measured(lambda: self.client.get(self.url()))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(str(self.experiment_id), response.content.decode())

    def test_permission_revocation_is_rechecked_and_spoof_headers_are_rejected(self):
        for header in ("HTTP_AUTHORIZATION", "HTTP_X_ROLE", "HTTP_X_ACTOR_TYPE", "HTTP_X_WORKSPACE_ID"):
            response = self.client.get(self.url(), **{header: "AI"})
            self.assertEqual(response.status_code, 400)
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_post_requires_csrf_and_unsupported_methods_do_not_calculate(self):
        response = self.client.post(self.url(), json.dumps(self.weights()), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        for method in ("put", "patch", "delete", "head"):
            response = getattr(self.client, method)(
                self.url(), HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertEqual(response.status_code, 405)
        response = self.client.post(self.url(), json.dumps(self.weights()), content_type="application/json",
                                    HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
                                    HTTP_ORIGIN="https://untrusted.example")
        self.assertEqual(response.status_code, 403)

    def test_invalid_payloads_are_bounded_errors_and_never_write(self):
        valid = self.weights()
        input_value = next(iter(valid["rgu"].values()))
        actor = next(iter(valid["rgu"]))
        for invalid in ([], {}, {**valid, "assessment_kind": "AI"},
                        *({**valid, "rgu": {actor: {**input_value, **change}}} for change in (
                            {"value": "11"}, {"value": "-1"}, {"value": "NaN"}, {"value": "1e9"},
                            {"value": True}, {"value": 1}, {"status": []}, {"status": "UNKNOWN"},
                            {"source_id": "ABSENT"}, {"source_version": ""},
                        ))):
            with self.subTest(invalid=invalid):
                response = self.measured(lambda: self.post_json(self.url(), invalid))
                self.assertEqual(response.status_code, 400, response.content)
        for raw in ('{"rgu":{},"rgu":{}}', '{"x":NaN}', '{', '[' * 1100, ' ' * 262145):
            response = self.client.post(self.url(), raw, content_type="application/json",
                                        HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertEqual(response.status_code, 400)

    def test_form_errors_preserve_user_inputs_and_do_not_run(self):
        inputs = self.client.get(self.url())
        data = self.form_body(inputs, self.weights())
        field = f"rgu.{self.pair[0].actor_id}.source_id"
        data[field] = ""
        response = self.measured(lambda: self.post_form(data))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Проверьте веса", status_code=400)
        self.assertContains(response, "beta-q-", status_code=400)
        data = self.form_body(inputs, self.weights())
        data["experiment_id"] = str(uuid4())
        self.assertEqual(self.post_form(data).status_code, 400)
        data = self.form_body(inputs, self.weights())
        data["unexpected"] = "value"
        self.assertEqual(self.post_form(data).status_code, 400)

    def test_unsupported_media_and_duplicate_form_fields_are_rejected(self):
        response = self.measured(lambda: self.client.post(
            self.url(), {"weight": "1"},  # Django's default multipart encoding
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        ))
        self.assertEqual(response.status_code, 415)
        inputs = self.client.get(self.url())
        data = self.form_body(inputs, self.weights())
        data["experiment_id"] = [str(self.experiment_id), str(self.experiment_id)]
        self.assertEqual(self.post_form(data).status_code, 400)

    def test_result_escapes_caller_supplied_source_text(self):
        self.fill()
        weights = self.weights()
        for value in weights["rgu"].values():
            value["source_id"] = '<script>alert("source")</script>'
        inputs = self.client.get(self.url())
        response = self.post_form(self.form_body(inputs, weights))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>alert("source")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("form-action 'self'", response["Content-Security-Policy"])
