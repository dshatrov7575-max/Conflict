from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import json

import pytest

from calculation import CalculationInputError, CalculationSnapshot, InputValue, calculate
from calculation.examples import example_snapshot
from scenario_modeling.adapter import CalculationAdapter, result_view
from scenario_modeling.model import ScenarioModel, ScenarioOverride, parameters


def model(snapshot=None):
    snapshot = snapshot or example_snapshot([10, -10])
    return ScenarioModel.from_calculation(snapshot, calculate(snapshot))


def test_baseline_is_immutable_and_separate_scenarios_are_isolated():
    original = model()
    baseline = original.baseline.to_json()
    second = model(original.baseline)
    changed = original.with_override("attitude:relation-0", "0")
    assert original.overrides == second.overrides == ()
    assert changed.baseline is original.baseline
    assert changed.baseline.to_json() == baseline
    assert calculate(original.baseline).UNO == 100
    assert CalculationAdapter.run(changed).run.UNO == 0
    assert CalculationAdapter.run(second).run.UNO == 100
    with pytest.raises(FrozenInstanceError):
        changed.baseline.ptns[0].actors[0].attitude.value = Decimal(0)


def test_repeated_runs_offline_replay_and_override_order_are_deterministic():
    original = model()
    first = original.with_override("attitude:relation-0", "6").with_override("kvs:relation-1", "2")
    reordered = original.with_override("kvs:relation-1", "2").with_override("attitude:relation-0", "6")
    replayed = ScenarioModel.from_dict(json.loads(first.to_json()))
    expected = result_view(first)
    for candidate in (first, reordered, replayed):
        assert result_view(candidate) == expected
    with localcontext() as context:
        context.prec = 3
        assert result_view(first) == expected
    snapshot = CalculationSnapshot.from_json(expected["scenario_snapshot_json"])
    assert calculate(snapshot).to_json() == expected["scenario_run_json"]


@pytest.mark.parametrize("status", ["UNKNOWN", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "OPEN_METHOD"])
@pytest.mark.parametrize("field", ["attitude", "kvs", "rgu", "kvptn"])
def test_absent_input_remains_exactly_absent_and_cannot_be_overridden(status, field):
    snapshot = example_snapshot([10, -10])
    ptn = snapshot.ptns[0]
    absent = InputValue(status, None, "missing-source", "2")
    if field == "kvptn":
        ptn = replace(ptn, kvptn=absent)
        target = "kvptn:PTN-1"
    else:
        ptn = replace(ptn, actors=(replace(ptn.actors[0], **{field: absent}), ptn.actors[1]))
        target = f"{field}:" + ("GU-0" if field == "rgu" else "relation-0")
    original = model(replace(snapshot, ptns=(ptn,)))
    changed = original.with_override("attitude:relation-1", "-5")
    effective = CalculationAdapter.snapshot(changed).ptns[0]
    actual = effective.kvptn if field == "kvptn" else getattr(effective.actors[0], field)
    assert actual is absent
    with pytest.raises(CalculationInputError):
        original.with_override(target, "1")


def test_zero_weight_stays_not_computable_and_never_becomes_zero_uno():
    original = model(example_snapshot([10, -10], weights=[0, 0]))
    view = result_view(original.with_override("attitude:relation-0", "5"))
    for result in (view["baseline"], view["scenario"]):
        assert result["UNO"] is None
        assert result["status"] == "NOT_COMPUTABLE"
        assert result["ptns"][0]["W"] == "0"
        assert result["ptns"][0]["Pol"] is None
    assert view["delta_uno"] is None
    assert view["changes"][0]["isolated_delta"] is None


def test_overrides_can_make_weight_zero_without_fallback():
    scenario = model().with_override("rgu:GU-0", "0").with_override("rgu:GU-1", "0")
    view = result_view(scenario)
    assert view["baseline"]["UNO"] == "100"
    assert view["scenario"]["status"] == "NOT_COMPUTABLE"
    assert view["scenario"]["UNO"] is None
    assert view["delta_uno"] is None


def test_rgu_is_applied_to_actor_across_all_ptns_with_explicit_scenario_provenance():
    snapshot = example_snapshot([10, -10])
    second = replace(snapshot.ptns[0], ptn_id="PTN-2", actors=tuple(
        replace(actor, relation_id=actor.relation_id + "-second") for actor in snapshot.ptns[0].actors))
    scenario = model(replace(snapshot, ptns=(*snapshot.ptns, second))).with_override("rgu:GU-0", "3")
    effective = CalculationAdapter.snapshot(scenario)
    assert len([row for row in parameters(scenario.baseline) if row.key == "rgu:GU-0"]) == 1
    for ptn in effective.ptns:
        assert ptn.actors[0].rgu.value == 3
        assert ptn.actors[0].rgu.status == "PROVISIONAL"
        assert ptn.actors[0].rgu.source_id.startswith(f"SCENARIO:{scenario.id}:")
        assert ptn.actors[1].rgu == snapshot.ptns[0].actors[1].rgu
    assert CalculationAdapter.run(scenario).run.UNO == 50


def test_effects_use_individual_core_runs_and_do_not_claim_additivity():
    scenario = model().with_override("attitude:relation-0", "5").with_override("attitude:relation-1", "-5")
    view = result_view(scenario)
    assert view["scenario"]["UNO"] == "50"
    assert view["delta_uno"] == "-50"
    assert [row["isolated_delta"] for row in view["changes"]] == ["-50", "-50"]
    assert all(row["explanation"] for row in view["changes"])


def test_replace_remove_and_return_to_baseline_do_not_accumulate_overrides():
    original = model()
    one = original.with_override("attitude:relation-0", "5")
    two = one.with_override("attitude:relation-0", "7")
    assert len(two.overrides) == 1 and two.overrides[0].value == 7
    assert two.without_override("attitude:relation-0") == original
    assert two.with_override("attitude:relation-0", "10") == original
    assert result_view(original)["delta_uno"] == "0"
    assert CalculationAdapter.snapshot(original).to_json() == original.baseline.to_json()


def test_small_exact_decimal_values_survive_model_roundtrip():
    small = Decimal("0.00000000000000000000000000000001")
    scenario = model().with_override("kvs:relation-0", small)
    assert scenario.overrides[0].value == small
    assert ScenarioModel.from_dict(json.loads(scenario.to_json())) == scenario


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e0", True, 1.2, None, "", "11", "-11", "0." + "1" * 33,
                                  Decimal("1E1000"), Decimal("1E-1000")])
def test_invalid_override_values_are_rejected(value):
    with pytest.raises(CalculationInputError):
        model().with_override("attitude:relation-0", value)


def test_scope_duplicate_targets_and_negative_weights_are_rejected():
    original = model()
    for key, value in (("attitude:other-relation", "1"), ("rgu:GU-0", "-1"), ("kvptn:PTN-1", "-1")):
        with pytest.raises(CalculationInputError):
            original.with_override(key, value)
    override = ScenarioOverride("attitude:relation-0", "1")
    with pytest.raises(CalculationInputError):
        replace(original, overrides=(override, override))
    other = example_snapshot([0, 0])
    with pytest.raises(CalculationInputError):
        ScenarioModel.from_calculation(original.baseline, calculate(other))
    payload = original.as_dict()
    payload["baseline"]["experiment_id"] = "another-lane"
    with pytest.raises(CalculationInputError):
        ScenarioModel.from_dict(payload)
