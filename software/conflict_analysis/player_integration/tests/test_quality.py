from dataclasses import replace
from unittest import TestCase

from calculation import ActorInput, CalculationSnapshot, InputValue, PtnInput, calculate
from player_integration.quality import quality_ui, summarize_quality


def snapshot(*, attitude="CONFIRMED", kvs="CONFIRMED", rgu="CONFIRMED", kvptn="CONFIRMED", scenario=False):
    def value(status, number, name):
        if status in {"UNKNOWN", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "OPEN_METHOD"}:
            return InputValue(status, None, f"source-{name}", "1")
        source = f"SCENARIO:quality:{name}" if scenario and name == "attitude" else f"source-{name}"
        return InputValue(status, number, source, "1")
    return CalculationSnapshot(
        experiment_id="experiment", assessment_set_id="set", project_id="project",
        time_slice_id="time", workspace_id="workspace", definition_version_id="definition",
        definition_hash="hash", time_slice_version="1", cutoff_date="2026-01-01",
        ptns=(PtnInput("ptn", value(kvptn, 1, "kvptn"), (
            ActorInput("actor", "relation", "assessment",
                       value(attitude, 5, "attitude"), value(kvs, 1, "kvs"), value(rgu, 1, "rgu")),
        )),),
    )


class CalculationQualityTests(TestCase):
    def quality(self, **statuses):
        item = snapshot(**statuses)
        return summarize_quality(item, calculate(item))

    def test_confirmed_inputs_are_separate_from_scientific_admission(self):
        quality = self.quality()
        self.assertEqual(quality.computation_status, "COMPLETE")
        self.assertEqual(quality.evidence_status, "CONFIRMED_INPUTS_ONLY")
        self.assertEqual(quality.scientific_admission_status, "NOT_ESTABLISHED")
        self.assertEqual(quality.human_validation_status, "NOT_PERFORMED")
        self.assertEqual(quality.predictive_validity_status, "NOT_CLAIMED")
        self.assertEqual((quality.required_input_count, quality.known_input_count, quality.missing_input_count), (4, 4, 0))

    def test_status_precedence_and_counts_preserve_all_input_states(self):
        disputed = self.quality(attitude="DISPUTED", kvs="PROVISIONAL", rgu="RETROSPECTIVE_KNOWLEDGE")
        self.assertEqual(disputed.evidence_status, "DISPUTED_INPUTS_PRESENT")
        self.assertEqual(dict(disputed.status_counts), {
            "CONFIRMED": 1, "DISPUTED": 1, "PROVISIONAL": 1, "RETROSPECTIVE_KNOWLEDGE": 1,
        })
        missing = self.quality(attitude="DISPUTED", kvptn="UNKNOWN")
        self.assertEqual(missing.computation_status, "NOT_COMPUTABLE")
        self.assertEqual(missing.evidence_status, "REQUIRED_INPUTS_MISSING")
        self.assertEqual((missing.known_input_count, missing.missing_input_count), (3, 1))

    def test_provisional_retrospective_and_scenario_inputs_are_visible(self):
        provisional = self.quality(attitude="PROVISIONAL")
        self.assertEqual(provisional.evidence_status, "PROVISIONAL_INPUTS_PRESENT")
        retrospective = self.quality(attitude="RETROSPECTIVE_KNOWLEDGE")
        self.assertEqual(retrospective.evidence_status, "RETROSPECTIVE_KNOWLEDGE_PRESENT")
        scenario = self.quality(attitude="PROVISIONAL", scenario=True)
        self.assertEqual(scenario.scenario_input_count, 1)
        self.assertEqual(quality_ui(scenario)["evidence_label"], "предварительные входы")

    def test_run_must_belong_to_snapshot(self):
        first = snapshot()
        second = replace(first, experiment_id="another")
        with self.assertRaisesRegex(ValueError, "does not belong"):
            summarize_quality(first, calculate(second))
