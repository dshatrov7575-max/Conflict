from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
import json

import pytest

from calculation import CalculationInputError, CalculationSnapshot, InputValue, calculate
from calculation.contracts import ABSENT_STATUSES
from calculation.examples import definition_vectors, example_snapshot, known


@pytest.mark.parametrize("name,snapshot,expected,status", [
    (*definition_vectors()[0], (0, 0, 0, 0, 0), "COMPLETE"),
    (*definition_vectors()[1], (50, 50, 100, 0, 100), "COMPLETE"),
    (*definition_vectors()[2], (50, 50, 100, 0, 100), "PARTIAL"),
    (*definition_vectors()[3], (None,) * 5, "NOT_COMPUTABLE"),
    (*definition_vectors()[4], (75, 25, 100, 50, 50), "COMPLETE"),
], ids=[f"DV-0{i}" for i in range(1, 6)])
def test_required_definition_vectors(name, snapshot, expected, status):
    run = calculate(snapshot)
    row = run.ptns[0]
    assert (row.P, row.N, row.A, row.B, row.Pol) == expected
    assert run.UNO == expected[-1]
    assert run.status == status
    assert run.P["PTN-1"] == row.P
    assert run.N["PTN-1"] == row.N
    assert run.A["PTN-1"] == row.A
    assert run.B["PTN-1"] == row.B
    assert run.Pol["PTN-1"] == row.Pol
    if name == "DV-03":
        assert (run.completeness.eligible_rows, run.completeness.expected_rows) == (2, 3)
        assert row.W == 2
        assert row.trace[2].missing == ("attitude",)
        assert row.trace[2].weight is row.trace[2].P_contribution is None
        assert "INCOMPLETE_ACTOR_INPUTS" in run.warnings


@pytest.mark.parametrize("x,expected", [(10, (100, 0, 100, 100, 0)), (-10, (0, 100, 100, -100, 0))])
def test_one_sided_activation_is_not_polarization(x, expected):
    row = calculate(example_snapshot([x, x])).ptns[0]
    assert (row.P, row.N, row.A, row.B, row.Pol) == expected


@pytest.mark.parametrize("status", sorted(ABSENT_STATUSES))
@pytest.mark.parametrize("field", ["attitude", "kvs", "rgu"])
def test_every_missing_component_excludes_entire_row_from_both_sums(status, field):
    snapshot = example_snapshot([10, -10])
    ptn = snapshot.ptns[0]
    row = replace(ptn.actors[0], **{field: InputValue(status)})
    run = calculate(replace(snapshot, ptns=(replace(ptn, actors=(row, ptn.actors[1])),)))
    assert (run.ptns[0].P, run.ptns[0].N, run.ptns[0].W, run.UNO) == (0, 100, 1, 0)
    assert run.ptns[0].trace[0].missing == (field,)
    assert run.status == "PARTIAL"


@pytest.mark.parametrize("status", sorted(ABSENT_STATUSES))
def test_missing_q_blocks_uno_without_partial_renormalization(status):
    snapshot = two_ptns()
    second = replace(snapshot.ptns[1], kvptn=InputValue(status))
    run = calculate(replace(snapshot, ptns=(snapshot.ptns[0], second)))
    assert run.UNO is None
    assert run.status == "NOT_COMPUTABLE"
    assert all(row.Pol is not None for row in run.ptns)
    assert all(row.UNO_contribution is None for row in run.ptns)
    assert run.completeness.known_ptn_weights == 1


def two_ptns():
    snapshot = example_snapshot([10, -10])
    first = replace(snapshot.ptns[0], kvptn=known(3))
    neutral = example_snapshot([0, 0]).ptns[0]
    second = replace(neutral, ptn_id="PTN-2", actors=tuple(
        replace(row, relation_id=f"other-{row.relation_id}") for row in neutral.actors))
    return replace(snapshot, ptns=(first, second))


def test_ptn_importance_controls_uno_and_trace():
    run = calculate(two_ptns())
    assert run.UNO == 75
    assert [row.Pol for row in run.ptns] == [100, 0]
    assert [row.UNO_contribution for row in run.ptns] == [75, 0]


def test_one_important_ptn_and_five_weak_ptns():
    snapshot = two_ptns()
    first = replace(snapshot.ptns[0], kvptn=known(10))
    weak = snapshot.ptns[1]
    rest = tuple(replace(weak, ptn_id=f"PTN-{i}", actors=tuple(
        replace(actor, relation_id=f"{i}-{actor.relation_id}") for actor in weak.actors)) for i in range(2, 7))
    assert calculate(replace(snapshot, ptns=(first, *rest))).UNO == Decimal("66.66666667")


def test_zero_q_excludes_ptn_and_all_zero_q_is_not_computable():
    snapshot = two_ptns()
    empty = replace(snapshot.ptns[1], kvptn=known(0), actors=())
    run = calculate(replace(snapshot, ptns=(snapshot.ptns[0], empty)))
    assert run.UNO == 100
    assert run.ptns[1].Pol is None
    assert run.ptns[1].UNO_contribution == 0
    assert run.status == "PARTIAL"
    assert calculate(example_snapshot([10, -10], q=0)).UNO is None
    blocked = calculate(replace(snapshot, ptns=(snapshot.ptns[0], replace(empty, kvptn=known(1)))))
    assert blocked.UNO is None
    assert "NONCOMPUTABLE_POSITIVE_WEIGHT_PTN" in blocked.warnings


def test_empty_topology_all_unknown_and_zero_salience():
    snapshot = example_snapshot([None, None])
    for run in (calculate(snapshot), calculate(replace(snapshot, ptns=())),
                calculate(example_snapshot([10, -10], kvs=[0, 0]))):
        assert run.status == "NOT_COMPUTABLE"
        assert run.UNO is None


def test_zero_weight_is_known_but_unknown_attitude_still_ineligible():
    run = calculate(example_snapshot([10, None], weights=[1, 0]))
    assert run.completeness.eligible_rows == 1
    assert run.ptns[0].trace[1].weight is None
    known_zero = calculate(example_snapshot([10, -10], weights=[1, 0]))
    assert known_zero.completeness.eligible_rows == 2
    assert known_zero.ptns[0].trace[1].weight == 0


def test_both_rgu_and_kvs_weights_affect_results_and_trace_delta():
    before = calculate(example_snapshot([10, -10]))
    after = calculate(example_snapshot([10, -10], weights=[2, 1], kvs=[3, 2]))
    assert (after.ptns[0].P, after.ptns[0].N, after.UNO) == (75, 25, 50)
    assert after.UNO - before.UNO == -50
    assert [row.weight for row in after.trace[0].trace] == [6, 2]
    assert sum(row.P_contribution for row in after.trace[0].trace) == after.ptns[0].P
    assert sum(row.N_contribution for row in after.trace[0].trace) == after.ptns[0].N


def test_replay_digest_order_normalization_and_deep_immutability():
    snapshot = two_ptns()
    reversed_snapshot = replace(snapshot, ptns=tuple(replace(ptn, actors=ptn.actors[::-1])
                                                    for ptn in snapshot.ptns[::-1]))
    assert snapshot.to_json() == reversed_snapshot.to_json()
    replay = CalculationSnapshot.from_json(snapshot.to_json())
    assert replay == snapshot
    assert calculate(replay).to_json() == calculate(snapshot).to_json()
    assert calculate(replay).result_digest == calculate(snapshot).result_digest
    with pytest.raises(FrozenInstanceError):
        snapshot.experiment_id = "other"
    with pytest.raises(FrozenInstanceError):
        snapshot.ptns[0].actors[0].attitude.value = Decimal(0)
    with pytest.raises(TypeError):
        calculate(snapshot).P["PTN-1"] = 0
    changed = replace(snapshot, experiment_id="other")
    assert changed.id != snapshot.id
    assert calculate(changed).UNO == calculate(snapshot).UNO
    tampered = json.loads(snapshot.to_json())
    tampered["ptns"][0]["actors"][0]["attitude"]["value"] = "0"
    with pytest.raises(CalculationInputError, match="digest"):
        CalculationSnapshot.from_json(json.dumps(tampered))


def test_status_and_source_revision_are_part_of_snapshot_identity():
    snapshot = example_snapshot([10])
    ptn = snapshot.ptns[0]
    actor = ptn.actors[0]
    for value in (replace(actor.attitude, status="PROVISIONAL"),
                  replace(actor.attitude, source_version="2")):
        other = replace(snapshot, ptns=(replace(ptn, actors=(replace(actor, attitude=value),)),))
        assert other.input_digest != snapshot.input_digest


def test_precision_and_rounding_are_independent_of_decimal_context():
    snapshot = example_snapshot([10, -10], weights=[2, 1])
    expected = calculate(snapshot).to_json()
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        replay = CalculationSnapshot.from_json(snapshot.to_json())
        assert calculate(replay).to_json() == expected
    assert calculate(snapshot).UNO == Decimal("66.66666667")


@pytest.mark.parametrize("attitude,expected", [("0.0000000005", "0"),
                                             ("0.0000000015", "0.00000002")])
def test_output_rounding_ties_to_even(attitude, expected):
    assert calculate(example_snapshot([attitude])).ptns[0].P == Decimal(expected)


def test_tiny_nonzero_weight_is_never_reported_as_zero_denominator():
    snapshot = example_snapshot([10], weights=["0.00000001"], kvs=["0.00000001"])
    run = calculate(snapshot)
    assert run.status == "COMPLETE"
    assert run.ptns[0].W == Decimal("0.0000000000000001")
    assert run.ptns[0].trace[0].weight == run.ptns[0].W
    assert run.ptns[0].P == 100


def test_uno_aggregates_ptn_polarization_without_pooling_opposite_ptns():
    snapshot = two_ptns()
    first = replace(snapshot.ptns[0], actors=(snapshot.ptns[0].actors[0],))
    second = replace(snapshot.ptns[1], actors=(replace(snapshot.ptns[1].actors[1],
                                                    attitude=known(-10)),))
    run = calculate(replace(snapshot, ptns=(first, second)))
    assert run.UNO == 0
    assert [row.Pol for row in run.ptns] == [0, 0]


@pytest.mark.parametrize("value", [True, None, "NaN", "Infinity", "-Infinity", "bad", 11, -11])
def test_reject_invalid_numeric_values(value):
    with pytest.raises(CalculationInputError):
        known(value)


def test_invalid_status_zero_disguised_as_missing_and_unsupported_strategy():
    for status, value in (("UNKNOWN", 0), ("OPEN_METHOD", 1), ("MADE_UP", None)):
        with pytest.raises(CalculationInputError):
            InputValue(status, value)
    for identity in ({"strategy_version": "2.0.0"}, {"strategy_id": "V4_POWER"}):
        with pytest.raises(CalculationInputError, match="Unsupported"):
            calculate(replace(example_snapshot([10]), **identity))


def test_reject_negative_weights_duplicate_topology_and_conflicting_rgu():
    snapshot = two_ptns()
    with pytest.raises(CalculationInputError):
        example_snapshot([10], weights=[-1])
    with pytest.raises(CalculationInputError):
        replace(snapshot, ptns=(snapshot.ptns[0], snapshot.ptns[0]))
    second = snapshot.ptns[1]
    with pytest.raises(CalculationInputError):
        replace(second, actors=(second.actors[0], second.actors[0]))
    with pytest.raises(CalculationInputError, match="exact RGU"):
        replace(snapshot, ptns=(snapshot.ptns[0], replace(second, actors=(
            replace(second.actors[0], rgu=known(2)), second.actors[1]))))
