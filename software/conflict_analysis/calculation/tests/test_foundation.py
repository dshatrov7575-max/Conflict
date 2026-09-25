from dataclasses import replace
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from calculation import CalculationInputError, CalculationSnapshot, calculate
from calculation.examples import known
from calculation.foundation import BetaWeights, capture_snapshot
from domain.models import ActorElementRole, ParameterValue, TimeSlice
from domain.services.player_experiments import create_manual_value, list_values
from domain.tests.test_player_experiments import PlayerExperimentsFixture


class FoundationCalculationTests(PlayerExperimentsFixture, TestCase):
    def setUp(self):
        _, self.experiment, _ = self.aggregate(kind="HUMAN")
        self.time = TimeSlice.objects.filter(workspace=self.workspace).order_by("order").first()
        self.roles = list(ActorElementRole.objects.filter(workspace=self.workspace)
                          .select_related("actor", "element").order_by("element_id", "actor_id"))
        self.ptn = self.roles[0].element_id
        self.pair = [row for row in self.roles if row.element_id == self.ptn][:2]

    def weights(self, experiment=None):
        experiment = experiment or self.experiment
        return BetaWeights(str(experiment.pk), str(self.time.pk),
                           tuple((str(actor), known(1, f"beta-rgu-{actor}"))
                                 for actor in {row.actor_id for row in self.roles}),
                           tuple((str(ptn), known(1 if ptn == self.ptn else 0, f"beta-q-{ptn}"))
                                 for ptn in {row.element_id for row in self.roles}))

    def write_value(self, role, code, value, *, experiment=None, predecessor=None):
        experiment = experiment or self.experiment
        dto = list_values(user=self.user, experiment_id=experiment.pk)
        etag = dto["experiment"]["etag"] if predecessor is None else next(
            row["etag"] for row in dto["values"] if row["id"] == str(predecessor.pk))
        body = {
            "id": str(uuid4()), "code": f"CALC-TEST-{uuid4().hex[:12]}",
            "version": "1.0.0" if predecessor is None else "2.0.0",
            "assessment_id": str(uuid4()), "assessment_code": f"CALC-HEADER-{uuid4().hex[:12]}",
            "time_slice_id": str(self.time.pk), "actor_code": role.actor.code,
            "element_code": role.element.code, "parameter_code": code,
            "status": "UNKNOWN" if value is None else "PROVISIONAL", "value": value,
            "temporal_status": "UNKNOWN", "confidence_category": "MEDIUM",
            "rationale": "Synthetic calculation test input", "note": "",
            "supersedes_id": str(predecessor.pk) if predecessor else None,
        }
        create_manual_value(user=self.user, experiment_id=experiment.pk, operation_id=str(uuid4()),
                            if_match=f'"{etag}"', body=body)
        return ParameterValue.objects.get(pk=body["id"])

    def fill(self, experiment=None):
        for role, value in zip(self.pair, (10, -10), strict=True):
            self.write_value(role, "POS", value, experiment=experiment)
            self.write_value(role, "SAL", 1, experiment=experiment)

    def capture(self, experiment=None, weights=True):
        experiment = experiment or self.experiment
        return capture_snapshot(experiment_id=experiment.pk, time_slice_id=self.time.pk,
                                beta_weights=self.weights(experiment) if weights else None)

    def test_g8_inputs_produce_beta_result_without_writes_or_receipt_fallback(self):
        self.fill()
        with CaptureQueriesContext(connection) as queries:
            snapshot = self.capture()
        assert not any(query["sql"].lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
                       for query in queries)
        run = calculate(snapshot)
        assert run.UNO == 100
        assert (run.completeness.expected_rows, run.completeness.eligible_rows) == (48, 2)
        assert snapshot.assessment_set_id == str(self.experiment.assessment_set_id)
        assert snapshot.definition_hash == self.workspace.definition_manifest_hash
        assert snapshot.time_slice_version == self.time.version
        with self.assertNumQueries(0):
            assert calculate(CalculationSnapshot.from_json(snapshot.to_json())).to_json() == run.to_json()
        no_weights = calculate(self.capture(weights=False))
        assert no_weights.UNO is None
        assert "MISSING_PTN_WEIGHT" in no_weights.warnings
        assert no_weights.completeness.eligible_rows == 0
        assert ParameterValue.objects.filter(assessment_set=self.experiment.assessment_set).count() == 4

    def test_human_ai_lanes_never_fill_each_other_and_same_inputs_agree(self):
        self.fill()
        _, ai, _ = self.aggregate(kind="AI")
        unknown = self.capture(ai)
        assert calculate(unknown).UNO is None
        assert calculate(unknown).completeness.eligible_rows == 0
        self.fill(ai)
        ai_snapshot = self.capture(ai)
        human_snapshot = self.capture()
        assert ai_snapshot.input_digest != human_snapshot.input_digest
        assert calculate(ai_snapshot).UNO == calculate(human_snapshot).UNO == 100
        current = ParameterValue.objects.get(assessment_set=self.experiment.assessment_set,
                                             actor_element_assessment__actor=self.pair[0].actor,
                                             parameter_definition__code="POS", successor__isnull=True)
        self.write_value(self.pair[0], "POS", 0, predecessor=current)
        assert calculate(self.capture()).UNO == 0
        assert self.capture(ai).to_json() == ai_snapshot.to_json()
        assert calculate(human_snapshot).UNO == 100

    def test_terminal_value_selection_survives_paired_header_revisions_and_unknown_correction(self):
        self.fill()
        before = self.capture()
        pos = ParameterValue.objects.get(assessment_set=self.experiment.assessment_set,
                                         actor_element_assessment__actor=self.pair[0].actor,
                                         parameter_definition__code="POS", successor__isnull=True)
        successor = self.write_value(self.pair[0], "POS", None, predecessor=pos)
        after = self.capture()
        actor = next(row for ptn in after.ptns for row in ptn.actors
                     if row.actor_id == str(self.pair[0].actor_id) and ptn.ptn_id == str(self.ptn))
        assert actor.attitude.status == "UNKNOWN"
        assert actor.attitude.source_id == str(successor.pk)
        assert actor.kvs.value == 1
        assert actor.kvs.source_id != "ABSENT"
        assert calculate(after).UNO == 0
        assert after.input_digest != before.input_digest
        assert calculate(before).UNO == 100

    def test_cross_experiment_time_and_topology_weights_rejected(self):
        for weights in (replace(self.weights(), experiment_id=str(uuid4())),
                        replace(self.weights(), time_slice_id=str(uuid4())),
                        replace(self.weights(), rgu=((str(uuid4()), known(1)),))):
            with self.assertRaises(CalculationInputError):
                capture_snapshot(experiment_id=self.experiment.pk, time_slice_id=self.time.pk,
                                 beta_weights=weights)

    def test_snapshot_and_trace_survive_freeze_and_archive(self):
        self.fill()
        snapshot = self.capture()
        result = calculate(snapshot).to_json()
        self.experiment.status = "FROZEN"
        self.experiment.frozen_at = timezone.now()
        self.experiment.save()
        assert self.capture().to_json() == snapshot.to_json()
        self.experiment.status = "ARCHIVED"
        self.experiment.save()
        assert calculate(CalculationSnapshot.from_json(snapshot.to_json())).to_json() == result
        assert self.capture().to_json() == snapshot.to_json()
