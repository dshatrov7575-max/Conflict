from __future__ import annotations

from uuid import uuid4

from django.contrib.auth.models import Group
from django.test import TestCase

from domain.services.analysis_admission import analysis_reader_group_name
from domain.services.analysis_contracts import AnalysisError
from domain.services.analysis_read_model import (
    context_snapshot,
    select_unique_terminal_rows,
    timeline_snapshot,
)
from domain.services.player_experiments import create_manual_value, list_values
from domain.tests.test_player_experiments import PlayerExperimentsFixture


class AnalysisReadModelTests(PlayerExperimentsFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.analysis_group = Group.objects.create(
            name=analysis_reader_group_name(cls.project.pk)
        )
        cls.user.groups.add(cls.analysis_group)

    def test_context_is_method_safe_and_permission_neutral(self):
        before = set(self.user.get_all_permissions())
        payload = context_snapshot(
            user=self.user,
            project_id=self.project.pk,
            workspace_id=self.workspace.pk,
        )
        self.assertEqual(len(payload["actors"]), 8)
        self.assertEqual(len(payload["analytical_elements"]), 6)
        self.assertEqual({row["code"] for row in payload["parameters"]}, {"POS", "SAL"})
        self.assertEqual(payload["method_state"]["project_total_score"], "METHOD_NOT_APPROVED")
        self.assertEqual(before, set(self.user.get_all_permissions()))

    def test_project_member_without_analysis_capability_is_hidden(self):
        self.user.groups.remove(self.analysis_group)
        with self.assertRaises(AnalysisError) as rejected:
            context_snapshot(
                user=self.user,
                project_id=self.project.pk,
                workspace_id=self.workspace.pk,
            )
        self.assertEqual((rejected.exception.code, rejected.exception.status), ("ANALYSIS_NOT_FOUND", 404))

    def test_terminal_selector_rejects_split_brain_and_excludes_predecessor(self):
        selected = select_unique_terminal_rows([
            {"id": "V1", "context": "C1", "successor_id": "V2"},
            {"id": "V2", "context": "C1", "successor_id": None},
        ])
        self.assertEqual([row["id"] for row in selected], ["V2"])
        with self.assertRaises(AnalysisError) as rejected:
            select_unique_terminal_rows([
                {"id": "V1", "context": "C1", "successor_id": None},
                {"id": "V2", "context": "C1", "successor_id": None},
            ])
        self.assertEqual(rejected.exception.code, "ANALYSIS_INTEGRITY_CONFLICT")

    def test_zero_and_unknown_remain_distinct(self):
        _, experiment, _ = self.aggregate(kind="HUMAN")
        zero_body = self.value_body(experiment, value=0)
        first_etag = list_values(user=self.user, experiment_id=experiment.pk)["experiment"]["etag"]
        create_manual_value(
            user=self.user, experiment_id=experiment.pk, operation_id=str(uuid4()),
            if_match=f'"{first_etag}"', body=zero_body,
        )
        payload = timeline_snapshot(
            user=self.user, project_id=self.project.pk, workspace_id=self.workspace.pk,
            experiment_id=experiment.pk, actor_code=zero_body["actor_code"],
            element_code=zero_body["element_code"], parameter_code=zero_body["parameter_code"],
        )
        self.assertEqual(payload["series"]["points"][0]["value"], 0)
        self.assertEqual(payload["series"]["points"][0]["status"], "PROVISIONAL")

        successor = self.value_body(experiment, predecessor=type("P", (), {"pk": zero_body["id"]})(), value=None, version="1.0.1")
        value_dto = list_values(user=self.user, experiment_id=experiment.pk)["values"][0]
        create_manual_value(
            user=self.user, experiment_id=experiment.pk, operation_id=str(uuid4()),
            if_match=f'"{value_dto["etag"]}"', body=successor,
        )
        payload = timeline_snapshot(
            user=self.user, project_id=self.project.pk, workspace_id=self.workspace.pk,
            experiment_id=experiment.pk, actor_code=successor["actor_code"],
            element_code=successor["element_code"], parameter_code=successor["parameter_code"],
        )
        self.assertEqual(len(payload["series"]["points"]), 1)
        self.assertIsNone(payload["series"]["points"][0]["value"])
        self.assertEqual(payload["series"]["points"][0]["status"], "UNKNOWN")

    def test_terminal_value_on_older_assessment_is_not_dropped(self):
        _, experiment, _ = self.aggregate(kind="AI")
        pos = self.value_body(experiment, value=2)
        pos["parameter_code"] = "POS"
        etag = list_values(user=self.user, experiment_id=experiment.pk)["experiment"]["etag"]
        create_manual_value(
            user=self.user, experiment_id=experiment.pk, operation_id=str(uuid4()),
            if_match=f'"{etag}"', body=pos,
        )
        sal = self.value_body(experiment, value=7)
        sal.update({
            "parameter_code": "SAL",
            "time_slice_id": pos["time_slice_id"],
            "actor_code": pos["actor_code"],
            "element_code": pos["element_code"],
        })
        etag = list_values(user=self.user, experiment_id=experiment.pk)["experiment"]["etag"]
        create_manual_value(
            user=self.user, experiment_id=experiment.pk, operation_id=str(uuid4()),
            if_match=f'"{etag}"', body=sal,
        )
        payload = timeline_snapshot(
            user=self.user, project_id=self.project.pk, workspace_id=self.workspace.pk,
            experiment_id=experiment.pk, actor_code=pos["actor_code"],
            element_code=pos["element_code"], parameter_code="POS",
        )
        self.assertEqual([point["value"] for point in payload["series"]["points"]], [2])

    def test_unapproved_total_parameter_is_blocked(self):
        _, experiment, _ = self.aggregate(kind="AI")
        with self.assertRaises(AnalysisError) as rejected:
            timeline_snapshot(
                user=self.user, project_id=self.project.pk, workspace_id=self.workspace.pk,
                experiment_id=experiment.pk, actor_code="GU-01", element_code="PTN-01",
                parameter_code="TOTAL_TENSION",
            )
        self.assertEqual(rejected.exception.code, "ANALYSIS_METHOD_NOT_APPROVED")
