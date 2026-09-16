from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import uuid4

from django.contrib.auth.models import Group
from django.test import Client, TestCase

from domain.models import TimeSlice
from domain.services.analysis_admission import analysis_reader_group_name
from domain.services.player_experiments import create_manual_value, list_values
from domain.tests.test_player_experiments import PlayerExperimentsFixture


class AnalysisHTTPTests(PlayerExperimentsFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.analysis_group = Group.objects.create(
            name=analysis_reader_group_name(cls.project.pk)
        )
        cls.user.groups.add(cls.analysis_group)

    def test_shell_is_same_origin_and_analysis_api_is_canonical_zero_write(self):
        client = Client()
        client.force_login(self.user)
        shell = client.get(
            f"/analysis/projects/{self.project.pk}/workspaces/{self.workspace.pk}/"
        )
        self.assertEqual(shell.status_code, 200)
        self.assertIn("default-src 'self'", shell["Content-Security-Policy"])
        self.assertNotIn("Set-Cookie", shell.headers)

        response = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{self.workspace.pk}/context/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("Set-Cookie", response.headers)
        raw = response.content
        self.assertEqual(
            response["ETag"],
            f'"{hashlib.sha256(raw).hexdigest()}"',
        )
        payload = json.loads(raw)
        digest = payload.pop("response_sha256")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(digest, hashlib.sha256(canonical).hexdigest())

    def test_fractional_timeline_response_preserves_server_canonical_bytes(self):
        _, experiment, _ = self.aggregate(kind="AI")
        TimeSlice.objects.create(
            id=uuid4(),
            project=self.project,
            workspace=self.workspace,
            code="ANALYSIS-HTTP-FRACTION-FOURTH",
            version="1.0.0",
            name="Fourth fractional HTTP test slice",
            cutoff_date=date(2027, 1, 1),
            order=4,
        )
        slices = list(
            TimeSlice.objects.filter(workspace=self.workspace).order_by(
                "cutoff_date", "order", "pk"
            )[:4]
        )
        self.assertEqual(len(slices), 4)
        values = (0.000001, 0.0000001, -0.000001, 1.25)
        first = self.value_body(experiment, value=values[0])
        experiment_etag = list_values(
            user=self.user,
            experiment_id=experiment.pk,
        )["experiment"]["etag"]
        for index, (time_slice, number) in enumerate(zip(slices, values, strict=True)):
            body = dict(first)
            body.update(
                {
                    "id": str(uuid4()),
                    "code": f"ANALYSIS-HTTP-FRACTION-{index}-{uuid4().hex[:8]}",
                    "assessment_id": str(uuid4()),
                    "assessment_code": f"ANALYSIS-HTTP-ASSESS-{index}-{uuid4().hex[:8]}",
                    "time_slice_id": str(time_slice.pk),
                    "parameter_code": "POS",
                    "value": number,
                }
            )
            create_manual_value(
                user=self.user,
                experiment_id=experiment.pk,
                operation_id=str(uuid4()),
                if_match=f'"{experiment_etag}"',
                body=body,
            )
        client = Client()
        client.force_login(self.user)
        response = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{self.workspace.pk}/timeline/",
            {
                "experiment_id": str(experiment.pk),
                "actor_code": first["actor_code"],
                "element_code": first["element_code"],
                "parameter_code": "POS",
            },
        )
        self.assertEqual(response.status_code, 200)
        for token in (b"1e-06", b"1e-07", b"-1e-06", b"1.25"):
            self.assertIn(token, response.content)
        self.assertEqual(
            response["ETag"],
            f'"{hashlib.sha256(response.content).hexdigest()}"',
        )
        payload = json.loads(response.content)
        persisted = [
            point["value"]
            for point in payload["series"]["points"]
            if point["record_state"] == "PERSISTED"
        ]
        self.assertEqual(persisted, list(values))

    def test_project_member_without_analysis_capability_gets_neutral_404(self):
        self.user.groups.remove(self.analysis_group)
        client = Client()
        client.force_login(self.user)
        response = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{self.workspace.pk}/context/"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            json.loads(response.content)["code"],
            "ANALYSIS_NOT_FOUND",
        )

    def test_unauthenticated_shell_contains_explicit_access_message(self):
        response = Client().get(
            f"/analysis/projects/{self.project.pk}/workspaces/{self.workspace.pk}/"
        )
        self.assertEqual(response.status_code, 401)
        self.assertContains(
            response,
            "Доступ к аналитике не предоставлен",
            status_code=401,
        )

    def test_spoof_headers_and_unapproved_metric_fail_closed(self):
        client = Client()
        client.force_login(self.user)
        context = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{self.workspace.pk}/context/",
            HTTP_AUTHORIZATION="Bearer spoof",
        )
        self.assertEqual(context.status_code, 400)
        self.assertEqual(
            json.loads(context.content)["code"],
            "ANALYSIS_REQUEST_INVALID",
        )

        _, experiment, _ = self.aggregate(kind="HUMAN")
        blocked = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{self.workspace.pk}/timeline/",
            {
                "experiment_id": str(experiment.pk),
                "actor_code": "GU-01",
                "element_code": "PTN-01",
                "parameter_code": "TOTAL_TENSION",
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(
            json.loads(blocked.content)["code"],
            "ANALYSIS_METHOD_NOT_APPROVED",
        )
