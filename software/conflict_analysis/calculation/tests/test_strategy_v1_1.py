"""Direct standalone checks of V2+V3+V4+V5 (also runnable with unittest).

These implementation tests do not claim to replace the independent oracle gate.
"""
from dataclasses import FrozenInstanceError, asdict, replace
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import random
import unittest

from calculation import CalculationInputError, CalculationSnapshot, calculate
from calculation.contracts import canonical_json
from calculation.contracts_v1_1 import (
    ActorInputV1_1, CalculationSnapshotV1_1, DesignWeightInputV1_1,
    FreezeProvenanceV1_1, InputValueV1_1, PtnInputV1_1,
    TopologyAuthorityV1_1, TopologyExclusionV1_1, TopologyRuleV1_1,
)
from calculation.strategy import PolarizationV1Beta
from calculation.strategy_v1_1 import (
    PolarizationV1_1Beta, calculate_v1_1, classify_row_v1_1, publish_bound_v1_1, scenario_delta_v1_1,
)


def digest(payload):
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def empirical(value=None, *, status=None, temporal="UNKNOWN", source="synthetic"):
    if isinstance(value, (tuple, list)):
        return InputValueV1_1("DISPUTED", temporal, alternatives=value, source_id=source)
    return InputValueV1_1(status or ("UNKNOWN" if value is None else "CONFIRMED"),
                         temporal, value, source_id=source)


def weight(value=1):
    return DesignWeightInputV1_1(value, "design", "d" * 64)


def actor(index, x=None, c=1, r=1, *, ptn="p"):
    return ActorInputV1_1(f"actor-{index}", f"{ptn}-relation-{index}", f"assessment-{index}",
                          x if isinstance(x, InputValueV1_1) else empirical(x),
                          c if isinstance(c, InputValueV1_1) else empirical(c), weight(r))


PROVENANCE = FreezeProvenanceV1_1("freeze-1", "2026-10-01T00:00:00Z", "definition-owner")
RULE = TopologyRuleV1_1("rule-1", "1", "a" * 64, ("TOPOLOGY_NOT_APPLICABLE",))


def authority(*, excluded=(), version="definition-1", strict=False):
    method = "b" * 64 if strict else None
    records = []
    for row, ptn in excluded:
        payload = dict(exclusion_id=f"exclude-{row.relation_id}", actor_id=row.actor_id,
                       ptn_id=ptn, relation_id=row.relation_id, rule_id=RULE.rule_id,
                       rule_version=RULE.rule_version, rule_sha256=RULE.rule_sha256,
                       reason="TOPOLOGY_NOT_APPLICABLE", definition_version_id=version,
                       method_contract_sha256=method, provenance=asdict(PROVENANCE))
        records.append(TopologyExclusionV1_1(**{**payload, "provenance": PROVENANCE,
                                               "exclusion_record_sha256": digest(payload)}))
    records.sort(key=lambda e: e.exclusion_id)
    set_digest = digest([asdict(e) for e in records])
    return TopologyAuthorityV1_1(version, "c" * 64, PROVENANCE, (RULE,), tuple(records),
                                set_digest, method, set_digest if strict else None,
                                (RULE,) if strict else ())


def snapshot(rows, *, q=1, topology=None):
    return CalculationSnapshotV1_1(
        "experiment", "assessments", "HUMAN", "project", "time", "workspace", "1", "2026-10-01",
        topology or authority(), (PtnInputV1_1("p", weight(q), tuple(rows)),),
    )


def value_of(witness):
    # Deliberately evaluate the original 1.0 formula, not strategy helpers.
    total = sum(row.weight for row in witness)
    assert total > 0
    positive = sum(10 * row.weight * max(row.position, 0) for row in witness) / total
    negative = sum(10 * row.weight * max(-row.position, 0) for row in witness) / total
    return 2 * min(positive, negative)


class StrategyV11Tests(unittest.TestCase):
    def assert_witnesses(self, s, result):
        by_relation = {r.relation_id: r for p in s.ptns for r in p.actors}
        expected = {t.input.relation_id for t in result.trace if t.row_class != "EXCLUDED"}
        for witness, endpoint in ((result.witness_lo, result.exact_lo),
                                  (result.witness_hi, result.exact_hi)):
            if witness is None:
                continue
            self.assertEqual({w.relation_id for w in witness}, expected)
            for row in witness:
                source = by_relation[row.relation_id]
                self.assertTrue(-10 <= row.position <= 10)
                self.assertTrue(0 <= row.kvs <= 10)
                self.assertEqual(row.weight, Fraction(source.rgu.value) * row.kvs)
                for original, completed, selected in ((source.attitude, row.position, row.position_alternative),
                                                       (source.kvs, row.kvs, row.kvs_alternative)):
                    if original.known:
                        self.assertEqual(completed, Fraction(original.value))
                    if original.alternatives:
                        self.assertIn(completed, tuple(Fraction(v) for v in original.alternatives))
                        self.assertEqual(selected, completed)
                    else:
                        self.assertIsNone(selected)
            self.assertEqual(value_of(witness), endpoint)

    def test_canonical_v1_through_v19_and_tb21_22_23(self):
        vectors = [
            ("V1", [(10, 1), (-10, 1)], 100, 100, "COMPLETE"),
            ("V2", [(10, 1), (None, 1)], 0, 100, "BOUNDED"),
            ("V3", [(10, 1), (-10, 1), (None, 10)], Fraction(50, 3), Fraction(50, 3), "BOUNDED"),
            ("V4", [(10, 5), (None, 1)], 0, Fraction(100, 3), "BOUNDED"),
            ("V5", [(10, 1), ((5, -5), 1)], 0, 50, "BOUNDED"),
            ("V6", [(10, 5), (-10, 5), (None, None)], 50, 100, "BOUNDED"),
            ("V7", [(10, 1), (None, 1), (None, 1)], 0, Fraction(200, 3), "BOUNDED"),
            ("V8", [(None, None)], 0, 0, "BOUNDED"),
            ("V9", [(-10, 2), (5, 2), (None, 1)], 40, 80, "BOUNDED"),
            ("V10", [(10, 0), (-10, 0)], None, None, "NOT_COMPUTABLE"),
            ("V11", [(10, 1), (-10, 1, None)], None, None, "NOT_COMPUTABLE"),
            ("V12a", [(10, 1), (-10, 1), (empirical(status="NOT_APPLICABLE"), 5)], Fraction(200, 7), Fraction(200, 7), "BOUNDED"),
            ("V12b", [(10, 1), (-10, 1), (empirical(status="NOT_APPLICABLE"), 5)], 100, 100, "COMPLETE"),
            ("V13", [(10, 1), (-5, None)], 0, Fraction(200, 3), "BOUNDED"),
            ("V14", [(10, 2), (-10, (2, 8))], 40, 100, "BOUNDED"),
            ("V15", [(10, 1), ((5, -5), 1), (-10, (2, 5))], Fraction(200, 7), 75, "BOUNDED"),
            ("V17", [(10, 5), (-10, (0, 5))], 0, 100, "BOUNDED"),
            ("V18", [(-6, (0, 2))], 0, 0, "BOUNDED"),
            ("V19", [(-6, (0, 2), 0)], None, None, "NOT_COMPUTABLE"),
        ]
        for name, data, lo, hi, status in vectors:
            with self.subTest(vector=name):
                rows = tuple(actor(i, *v) for i, v in enumerate(data))
                s = snapshot(rows, topology=authority(excluded=((rows[-1], "p"),)) if name == "V12b" else None)
                run = calculate_v1_1(s)
                result = run.ptns[0]
                self.assertEqual((result.exact_lo, result.exact_hi, result.status), (lo, hi, status))
                self.assertEqual((run.exact_lo, run.exact_hi, run.status), (lo, hi, status))
                self.assertEqual(result.Pol_point is not None, status == "COMPLETE")
                if status == "BOUNDED":
                    self.assertEqual(result.envelope_sharpness, "SHARP")
                    self.assertIsNotNone(result.witness_lo)
                    self.assertIsNotNone(result.witness_hi)
                    self.assert_witnesses(s, result)
                if name in ("V8", "V18"):
                    self.assertIn("ZERO_WEIGHT_COMPLETIONS_EXCLUDED", result.warnings)
                if name in ("V10", "V17", "V19"):
                    self.assertNotIn("ZERO_WEIGHT_COMPLETIONS_EXCLUDED", result.warnings)
                if name in ("V10", "V19"):
                    self.assertEqual(result.reason, "ZERO_WEIGHT")
                if name == "V19":
                    self.assertEqual(result.trace[0].row_class, "KD")
                if name == "V11":
                    self.assertEqual(result.reason, "DESIGN_WEIGHT_MISSING")
                if name == "V2":
                    self.assertIn("ONE_SIDED_OBSERVED", result.warnings)
                if name == "V3":
                    self.assertIn("SUBSET_VALUE_OUTSIDE_ENVELOPE", result.warnings)
                if name == "V12a":
                    self.assertEqual(result.not_applicable_rows, 1)
                if name == "V12b":
                    self.assertEqual((result.excluded_rows, result.expected_rows), (1, 2))
        # V16 is a rejected input, not an envelope.
        with self.assertRaisesRegex(CalculationInputError, "DESIGN_WEIGHT_STATUS_INVALID"):
            DesignWeightInputV1_1.from_payload({"value": 1, "value_status": "DISPUTED"})

    def test_directed_nonterminating_publication(self):
        for number, lower, upper in ((Fraction(50, 3), "16.66666666", "16.66666667"),
                                     (Fraction(100, 3), "33.33333333", "33.33333334"),
                                     (Fraction(200, 7), "28.57142857", "28.57142858")):
            self.assertEqual(publish_bound_v1_1(number, upper=False), Decimal(lower))
            self.assertEqual(publish_bound_v1_1(number, upper=True), Decimal(upper))
            self.assertEqual(publish_bound_v1_1(-number, upper=False), -Decimal(upper))
            self.assertEqual(publish_bound_v1_1(-number, upper=True), -Decimal(lower))

    def test_all_row_classes_and_no_silent_disputed_conversion(self):
        cases = [(10, 1, 1, "E"), (None, 1, 1, "M1"), (10, None, 1, "M2a"),
                 (None, None, 1, "M2b"), ((-5, 5), 1, 1, "PD"),
                 (10, (0, 2), 1, "KD"), ((-5, 5), (0, 2), 1, "PDKD"),
                 (10, 1, None, "X"),
                 (empirical(status="NOT_APPLICABLE"), 1, 1, "M1")]
        for x, c, r, expected in cases:
            self.assertEqual(classify_row_v1_1(actor(0, x, c, r)), expected)
        for field in ("attitude", "kvs"):
            with self.subTest(field=field), self.assertRaisesRegex(CalculationInputError, "NONNUMERIC"):
                replace(actor(0), **{field: empirical(1, status="DISPUTED")})

        for alternatives in ((), (1,), (1, 1), (1, "1.0")):
            with self.subTest(disputed_alternatives=alternatives), self.assertRaisesRegex(
                    CalculationInputError, "ALTERNATIVES_INVALID"):
                InputValueV1_1("DISPUTED", "UNKNOWN", alternatives=alternatives)
        with self.assertRaisesRegex(CalculationInputError, "ALTERNATIVES_INVALID"):
            InputValueV1_1("UNKNOWN", "UNKNOWN", alternatives=(1, 2))

    def test_decimal_lexical_and_domain_validation(self):
        invalid = [True, 1.0, "1e0", "1E+0", " 1", "1 ", "\t1", "пј‘", "ЩЎ", "+1", "01",
                   "1.", ".1", "NaN", "Infinity", "-Infinity", Decimal("NaN"), Decimal("Infinity"),
                   "0." + "1" * 33, "11", "-11", 100, {}, []]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(CalculationInputError):
                empirical(value) if not isinstance(value, (list, tuple)) else InputValueV1_1("CONFIRMED", value=value)
        for valid in (0, -10, "10.000", "-0.00", Decimal("1.25"), "0." + "0" * 31 + "1"):
            self.assertTrue(empirical(valid).known)
        for alternatives in ((0,), (0, 0), ("0", "0.0"), (-11, 1)):
            with self.assertRaises(CalculationInputError):
                empirical(alternatives)
        with self.assertRaises(CalculationInputError):
            InputValueV1_1("CONFIRMED", value=1, alternatives=(0, 1))
        for c in (-1, (-1, 1)):
            with self.assertRaisesRegex(CalculationInputError, "KVS_DOMAIN_INVALID"):
                actor(0, 1, c)
        with self.assertRaisesRegex(CalculationInputError, "DECIMAL_DOMAIN_INVALID"):
            weight(-1)

    def test_decimal_revalidation_cutoff_wire_shapes_and_result_container_freeze(self):
        tiny = InputValueV1_1("CONFIRMED", "UNKNOWN", Decimal("0.0000001"))
        self.assertEqual(replace(tiny, source_version="2").value, Decimal("0.0000001"))
        tiny_weight = DesignWeightInputV1_1(Decimal("0.0000001"), "design", "d" * 64)
        self.assertEqual(replace(tiny_weight, design_record_id="design-2").value, Decimal("0.0000001"))
        disputed = InputValueV1_1(
            "DISPUTED", "UNKNOWN", alternatives=(Decimal("0.0000001"), Decimal("0.0000002")))
        self.assertEqual(
            replace(disputed, source_version="2").alternatives,
            (Decimal("0.0000001"), Decimal("0.0000002")),
        )
        with self.assertRaisesRegex(CalculationInputError, "DECIMAL_LEXICAL_INVALID"):
            InputValueV1_1("CONFIRMED", "UNKNOWN", Decimal("1E-33"))

        s = snapshot((actor(0, 10), actor(1, -10)))
        self.assertEqual(replace(s, cutoff_date="2024-02-29").cutoff_date, "2024-02-29")
        for invalid in ("2026-02-30", "not-a-date", "2026-2-03"):
            with self.subTest(cutoff_date=invalid), self.assertRaisesRegex(
                    CalculationInputError, "CUTOFF_DATE_INVALID"):
                replace(s, cutoff_date=invalid)

        empty = replace(s, ptns=())
        for malformed in ({}, ""):
            payload = json.loads(empty.to_json())
            payload["ptns"] = malformed
            with self.subTest(ptns=repr(malformed)), self.assertRaisesRegex(
                    CalculationInputError, "SNAPSHOT_PAYLOAD_INVALID"):
                CalculationSnapshotV1_1.from_json(json.dumps(payload))

        empty_rows = snapshot(())
        payload = json.loads(empty_rows.to_json())
        payload["ptns"][0]["actors"] = {}
        with self.assertRaisesRegex(CalculationInputError, "PTN_PAYLOAD_INVALID"):
            CalculationSnapshotV1_1.from_json(json.dumps(payload))

        payload = json.loads(s.to_json())
        authority_payload = payload["topology_authority"]
        payload["topology_authority"] = [
            ["definition_version_id", "wrong"],
            *[[key, value] for key, value in authority_payload.items()],
        ]
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_AUTHORITY_PAYLOAD_INVALID"):
            CalculationSnapshotV1_1.from_json(json.dumps(payload))

        for malformed in ("", {}):
            with self.subTest(direct_ptns=repr(malformed)), self.assertRaisesRegex(
                    CalculationInputError, "PTN_INPUT_SCHEMA_INVALID"):
                replace(s, ptns=malformed)
            with self.subTest(direct_actors=repr(malformed)), self.assertRaisesRegex(
                    CalculationInputError, "ACTOR_INPUT_SCHEMA_INVALID"):
                PtnInputV1_1("direct-p", weight(1), malformed)
            for field in ("rules", "exclusions", "method_rules"):
                with self.subTest(authority_field=field, value=repr(malformed)), self.assertRaisesRegex(
                        CalculationInputError, "TOPOLOGY_AUTHORITY_COLLECTION_INVALID"):
                    replace(authority(), **{field: malformed})

        bounded = calculate_v1_1(snapshot((actor(0, 10), actor(1, None))))
        ptn = bounded.ptns[0]
        trace_source = list(ptn.trace)
        warnings_source = list(ptn.warnings)
        witness_source = list(ptn.witness_lo)
        frozen_ptn = replace(
            ptn, trace=trace_source, warnings=warnings_source, witness_lo=witness_source)
        trace_source.clear()
        warnings_source.append("EXTERNAL_MUTATION")
        witness_source.clear()
        self.assertIsInstance(frozen_ptn.trace, tuple)
        self.assertIsInstance(frozen_ptn.warnings, tuple)
        self.assertIsInstance(frozen_ptn.witness_lo, tuple)
        self.assertNotIn("EXTERNAL_MUTATION", frozen_ptn.warnings)
        self.assertTrue(frozen_ptn.trace)
        self.assertTrue(frozen_ptn.witness_lo)

        run_ptns = list(bounded.ptns)
        run_warnings = list(bounded.warnings)
        frozen_run = replace(bounded, ptns=run_ptns, warnings=run_warnings)
        digest_before = frozen_run.result_digest
        run_ptns.clear()
        run_warnings.append("EXTERNAL_MUTATION")
        self.assertEqual(frozen_run.result_digest, digest_before)
        self.assertIsInstance(frozen_run.ptns, tuple)
        self.assertIsInstance(frozen_run.warnings, tuple)

        base = snapshot((actor(0, 10), actor(1, None)))
        scenario = replace(base, ptns=(replace(
            base.ptns[0],
            actors=(base.ptns[0].actors[0], replace(
                base.ptns[0].actors[1], attitude=empirical(-10, source="SCENARIO"))),
        ),))
        delta = scenario_delta_v1_1(base, scenario)
        outer_source = list(delta.delta_outer)
        exact_source = list(delta.exact_outer)
        frozen_delta = replace(delta, delta_outer=outer_source, exact_outer=exact_source)
        digest_before = frozen_delta.result_digest
        outer_source[1] = Decimal("999")
        exact_source.clear()
        self.assertEqual(frozen_delta.result_digest, digest_before)
        self.assertIsInstance(frozen_delta.delta_outer, tuple)
        self.assertIsInstance(frozen_delta.exact_outer, tuple)

    def test_temporal_axis_is_orthogonal_and_hashed(self):
        original = snapshot((actor(0, 10), actor(1, -10)))
        rows = original.ptns[0].actors
        retro = replace(rows[0], attitude=empirical(10, status="PROVISIONAL", temporal="RETROSPECTIVE_KNOWLEDGE"),
                        kvs=empirical(1, status="RETROSPECTIVE_KNOWLEDGE"))
        changed = replace(original, ptns=(replace(original.ptns[0], actors=(retro, rows[1])),))
        run = calculate_v1_1(changed)
        self.assertEqual(run.UNO_point, calculate_v1_1(original).UNO_point)
        self.assertNotEqual(changed.input_digest, original.input_digest)
        self.assertEqual((run.ptns[0].retrospective_value_count, run.ptns[0].retrospective_temporal_count), (1, 1))
        self.assertIn("RETROSPECTIVE_INPUTS_PRESENT", run.warnings)
        with self.assertRaisesRegex(CalculationInputError, "NO_DIRECT_POSITION_REQUIRES_UNKNOWN"):
            empirical(1, temporal="NO_DIRECT_POSITION")
        self.assertEqual(empirical(temporal="NO_DIRECT_POSITION").value_status, "UNKNOWN")
        with self.assertRaisesRegex(CalculationInputError, "ASSESSMENT_KIND_INVALID"):
            replace(original, assessment_kind="MIXED")
        nonnumeric = snapshot((actor(0, empirical((-5, 5), temporal="RETROSPECTIVE_KNOWLEDGE")),))
        self.assertNotIn("RETROSPECTIVE_INPUTS_PRESENT", calculate_v1_1(nonnumeric).warnings)

    def test_topology_authority_tb15_through_tb20(self):
        rows = (actor(0, 10), actor(1, -10), actor(2, empirical(status="NOT_APPLICABLE"), 5))
        auth = authority(excluded=((rows[2], "p"),))
        s = snapshot(rows, topology=auth)
        run = calculate_v1_1(s)
        self.assertEqual(run.UNO_point, 100)
        self.assertEqual(s.topology_exclusion_set_sha256, digest([asdict(e) for e in auth.exclusions]))
        self.assertEqual(snapshot(rows).topology_exclusion_set_sha256, digest([]))
        with self.assertRaises((TypeError, ValueError)):
            replace(s, topology_exclusions=())  # No caller exclusion option.
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_AUTHORITY_REQUIRED"):
            replace(s, topology_authority=None)
        other = replace(s, experiment_id="another-experiment")
        self.assertEqual(other.topology_exclusion_set_sha256, s.topology_exclusion_set_sha256)
        revised = replace(s, topology_authority=authority(version="definition-2"))
        self.assertNotEqual(revised.input_digest, s.input_digest)
        self.assertEqual(calculate_v1_1(revised).status, "BOUNDED")
        self.assertEqual(calculate_v1_1(CalculationSnapshotV1_1.from_json(s.to_json())).to_json(), run.to_json())
        self.assertIn("NOT_APPLICABLE_VALUE_TREATED_AS_ABSENT", calculate_v1_1(revised).warnings)
        strict = snapshot(rows, topology=authority(excluded=((rows[2], "p"),), strict=True))
        self.assertEqual(calculate_v1_1(strict).UNO_point, 100)
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_EXCLUSION_SET_MISMATCH"):
            replace(strict.topology_authority, method_topology_exclusion_set_sha256="e" * 64)
        with self.assertRaisesRegex(CalculationInputError, "METHOD_TOPOLOGY_RULE_MISMATCH"):
            replace(strict.topology_authority, method_rules=())
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_EXCLUSION_SET_MISMATCH"):
            replace(auth, exclusions=())
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_EXCLUSION_RECORD_DIGEST_MISMATCH"):
            replace(auth.exclusions[0], reason="OTHER")
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_RULE_MISMATCH"):
            replace(auth, rules=(replace(RULE, rule_version="2"),))
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_RULE_REASONS_INVALID"):
            TopologyRuleV1_1("rule-x", "1", "a" * 64, "NOT_A_COLLECTION")
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_AUTHORITY_MISMATCH"):
            replace(auth, definition_version_id="changed")
        with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_EXCLUSION_RELATION_MISMATCH"):
            snapshot(rows[:2], topology=auth)
        changed_excluded = replace(rows[2], attitude=empirical(-10), kvs=empirical(10), rgu=weight(None))
        ignored = calculate_v1_1(snapshot((*rows[:2], changed_excluded), topology=auth))
        self.assertEqual(ignored.UNO_point, 100)
        self.assertIn("VALUE_ON_EXCLUDED_RELATION", ignored.warnings)
        self.assertEqual((ignored.ptns[0].trace[-1].exclusion_id, ignored.ptns[0].trace[-1].rule_id),
                         (auth.exclusions[0].exclusion_id, RULE.rule_id))

    def test_replay_tampering_permutations_and_immutability(self):
        rows = (actor(0, (-5, 5), (0, 2)), actor(1, -10), actor(2, 5))
        s = snapshot(rows, topology=authority(excluded=((rows[2], "p"), (rows[1], "p"))))
        second = PtnInputV1_1("q", weight(3), (actor(0, None, ptn="q"), actor(1, -10, ptn="q")))
        s = replace(s, ptns=(*s.ptns, second))
        reversed_rows = tuple(replace(r, attitude=replace(r.attitude, alternatives=r.attitude.alternatives[::-1]),
                                      kvs=replace(r.kvs, alternatives=r.kvs.alternatives[::-1])) for r in rows[::-1])
        shuffled = replace(s, ptns=(replace(second, actors=second.actors[::-1]),
                                   replace(s.ptns[0], actors=reversed_rows)),
                           topology_authority=replace(s.topology_authority,
                                                      exclusions=s.topology_exclusions[::-1]))
        self.assertEqual(s.to_json(), shuffled.to_json())
        self.assertEqual(calculate_v1_1(s).to_json(), calculate_v1_1(shuffled).to_json())
        self.assertEqual(calculate_v1_1(s).result_digest, calculate_v1_1(shuffled).result_digest)
        replay = CalculationSnapshotV1_1.from_json(s.to_json())
        self.assertEqual(replay, s)
        self.assertEqual(calculate_v1_1(replay).to_json(), calculate_v1_1(s).to_json())
        self.assert_witnesses(s, calculate_v1_1(s).ptns[0])
        with self.assertRaises(FrozenInstanceError):
            s.assessment_kind = "AI"
        with self.assertRaises(FrozenInstanceError):
            s.ptns[0].actors[0].kvs.value = Decimal(0)
        for name, value in (("topology_exclusions", []), ("topology_exclusion_set_sha256", "f" * 64)):
            payload = json.loads(s.to_json())
            payload[name] = value
            with self.assertRaisesRegex(CalculationInputError, "TOPOLOGY_EXCLUSION_SET_MISMATCH"):
                CalculationSnapshotV1_1.from_json(json.dumps(payload))
        payload = json.loads(s.to_json())
        payload["ptns"][0]["actors"][0]["attitude"]["alternatives"] = ["-4", "5"]
        with self.assertRaisesRegex(CalculationInputError, "SNAPSHOT_DIGEST_MISMATCH"):
            CalculationSnapshotV1_1.from_json(json.dumps(payload))
        payload = json.loads(s.to_json())
        payload["ptns"][0]["unexpected"] = "ignored-data-must-fail"
        with self.assertRaisesRegex(CalculationInputError, "PTN_PAYLOAD_INVALID"):
            CalculationSnapshotV1_1.from_json(json.dumps(payload))
        with self.assertRaisesRegex(CalculationInputError, "DUPLICATE_JSON_KEY"):
            CalculationSnapshotV1_1.from_json('{"strategy_version":"1.1.0","strategy_version":"1.0.0"}')

    def test_outer_relaxation_has_exact_lower_witness_without_exponential_lower_loop(self):
        # 21 free sides exceed R-B15. A sole observed +10 cannot be balanced
        # by an odd number of fixed unit contributions at exactly Pol=100.
        rows = (actor(0, 10),) + tuple(actor(i, None) for i in range(1, 22))
        s = snapshot(rows)
        p = calculate_v1_1(s).ptns[0]
        self.assertEqual(p.envelope_sharpness, "OUTER_BOUND_NONSHARP")
        self.assertEqual((p.exact_lo, p.exact_hi), (0, 100))
        self.assertIsNone(p.witness_hi)
        self.assertIsNotNone(p.witness_lo)
        self.assert_witnesses(s, p)
        self.assertIn("ENVELOPE_OUTER_RELAXED", p.warnings)
        # More than 2**20 finite combinations: lower factoring must not
        # enumerate alternatives after the upper budget has been exceeded.
        finite = snapshot(tuple(actor(i, (-5, 5), (0, 2)) for i in range(11)))
        p = calculate_v1_1(finite).ptns[0]
        self.assertEqual(p.envelope_sharpness, "OUTER_BOUND_NONSHARP")
        self.assertEqual(p.exact_lo, 0)
        self.assert_witnesses(finite, p)
        self.assertIn("ZERO_WEIGHT_COMPLETIONS_EXCLUDED", p.warnings)

    def test_uno_exact_aggregation_and_q_zero_rules(self):
        first = snapshot((actor(0, 10), actor(1, -10)))
        second = PtnInputV1_1("q", weight(1), (actor(0, 10, ptn="q"), actor(1, None, ptn="q")))
        s = replace(first, ptns=(*first.ptns, second))
        run = calculate_v1_1(s)
        self.assertEqual((run.UNO_lo, run.UNO_hi, run.UNO_point, run.status), (50, 100, None, "BOUNDED"))
        second = replace(second, kvptn=weight(3))
        self.assertEqual(calculate_v1_1(replace(s, ptns=(s.ptns[0], second))).exact_lo, 25)
        for q in (None, 1):
            empty = replace(second, actors=(), kvptn=weight(q))
            blocked = calculate_v1_1(replace(s, ptns=(s.ptns[0], empty)))
            self.assertIsNone(blocked.UNO_lo)
            self.assertEqual(blocked.status, "NOT_COMPUTABLE")
        empty_zero = replace(second, actors=(), kvptn=weight(0))
        run = calculate_v1_1(replace(s, ptns=(s.ptns[0], empty_zero)))
        self.assertEqual((run.UNO_point, run.status), (100, "COMPLETE"))
        self.assertIsNone(run.ptns[1].UNO_contribution_lo)  # R-B22, unlike 1.0.
        known_zero = replace(second, kvptn=weight(0))
        run = calculate_v1_1(replace(s, ptns=(s.ptns[0], known_zero)))
        self.assertEqual((run.ptns[1].UNO_contribution_lo, run.ptns[1].UNO_contribution_hi), (0, 0))
        zero_area = calculate_v1_1(snapshot((actor(0, 10),), q=0))
        self.assertIsNone(zero_area.UNO_lo)
        self.assertEqual(
            (zero_area.ptns[0].UNO_contribution_lo, zero_area.ptns[0].UNO_contribution_hi),
            (0, 0),
        )
        self.assertIsNone(calculate_v1_1(replace(s, ptns=())).UNO_lo)
        # Area rounding uses exact PTN endpoints, never their rounded displays.
        third = snapshot((actor(0, 10, 1), actor(1, -10, 1), actor(2, None, 5)))
        p = third.ptns[0]
        one_sided = PtnInputV1_1("q", weight(2), (actor(0, 10, ptn="q"),))
        run = calculate_v1_1(replace(third, ptns=(p, one_sided)))
        self.assertEqual(run.exact_lo, Fraction(200, 21))
        self.assertEqual(run.UNO_lo, Decimal("9.52380952"))
        self.assertEqual(run.UNO_hi, Decimal("9.52380953"))

    def test_scenarios_bounds_direction_and_exclusion_invariance_tb16(self):
        base = snapshot((actor(0, 10), actor(1, None)))
        p = base.ptns[0]
        scenario = replace(base, ptns=(replace(p, actors=(p.actors[0], replace(p.actors[1],
            attitude=empirical(-10, source="SCENARIO")))),))
        delta = scenario_delta_v1_1(base, scenario)
        self.assertEqual((delta.delta_point, delta.delta_outer, delta.envelope_sharpness, delta.direction),
                         (None, (0, 100), "OUTER_BOUND_NONSHARP", "DIRECTION_NOT_ESTABLISHED"))
        self.assertEqual(scenario_delta_v1_1(scenario, base).delta_outer if False else delta.exact_outer, (0, 100))
        complete = snapshot((actor(0, 10), actor(1, 10)))
        moved = replace(complete, ptns=(replace(complete.ptns[0], actors=(complete.ptns[0].actors[0],
            replace(complete.ptns[0].actors[1], attitude=empirical(-10, source="SCENARIO")))),))
        delta = scenario_delta_v1_1(complete, moved)
        self.assertEqual(
            (delta.delta_point, delta.delta_outer, delta.direction),
            (100, None, "DIRECTION_NOT_ESTABLISHED"),
        )
        blocked_base = snapshot((actor(0, 10), actor(1, None, r=None)))
        blocked_ptn = blocked_base.ptns[0]
        blocked_scenario = replace(blocked_base, ptns=(replace(
            blocked_ptn,
            actors=(blocked_ptn.actors[0], replace(
                blocked_ptn.actors[1], attitude=empirical(-10, source="SCENARIO")
            )),
        ),))
        self.assertEqual(
            (calculate_v1_1(blocked_base).status, calculate_v1_1(blocked_scenario).status),
            ("NOT_COMPUTABLE", "NOT_COMPUTABLE"),
        )
        self.assertIsNone(scenario_delta_v1_1(blocked_base, blocked_scenario).delta_outer)
        illegal_kvptn = replace(scenario, ptns=(replace(scenario.ptns[0], kvptn=weight(None)),))
        with self.assertRaisesRegex(CalculationInputError, "SCENARIO_DESIGN_OVERRIDE_UNSPECIFIED"):
            scenario_delta_v1_1(base, illegal_kvptn)
        illegal_row = replace(
            scenario,
            ptns=(replace(scenario.ptns[0], actors=(
                scenario.ptns[0].actors[0],
                replace(scenario.ptns[0].actors[1], rgu=weight(None)),
            )),),
        )
        with self.assertRaisesRegex(CalculationInputError, "SCENARIO_DESIGN_OVERRIDE_UNSPECIFIED"):
            scenario_delta_v1_1(base, illegal_row)
        excluded = replace(base, topology_authority=authority(excluded=((p.actors[1], "p"),)))
        for before, after in ((base, excluded), (excluded, base)):
            with self.assertRaisesRegex(CalculationInputError, "SCENARIO_TOPOLOGY_EXCLUSION_MISMATCH"):
                scenario_delta_v1_1(before, after)
        with self.assertRaisesRegex(CalculationInputError, "SCENARIO_EMPIRICAL_OVERRIDE_INVALID"):
            scenario_delta_v1_1(base, complete)
        for field in ("experiment_id", "assessment_set_id"):
            with self.subTest(field=field), self.assertRaisesRegex(
                    CalculationInputError, "SCENARIO_BASE_IDENTITY_MISMATCH"):
                scenario_delta_v1_1(base, replace(scenario, **{field: f"other-{field}"}))

    def test_exact_arithmetic_is_decimal_context_independent(self):
        s = snapshot((actor(0, 10, "0.00000000000000000000000000000001"),
                      actor(1, -5, None), actor(2, (-5, 5), (0, 2))))
        expected = calculate_v1_1(s).to_json()
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            replay = CalculationSnapshotV1_1.from_json(s.to_json())
            self.assertEqual(calculate_v1_1(replay).to_json(), expected)

    def test_grid_containment_and_witness_attainment_mixed_classes(self):
        rng = random.Random(1105)
        classes = [(10, 2), (None, 2), (-5, None), (None, None), ((-5, 5), 2),
                   (-10, (0, 2)), ((-5, 5), (0, 2)), ((-5, 5), None), (None, (0, 2))]
        for case in range(50):
            rows = tuple(actor(i, *rng.choice(classes), r=rng.choice((0, 1, 2))) for i in range(3))
            s = snapshot(rows)
            p = calculate_v1_1(s).ptns[0]
            if p.status == "BOUNDED":
                self.assert_witnesses(s, p)
            completions = []
            for row in rows:
                xs = (row.attitude.value,) if row.attitude.known else row.attitude.alternatives or (-10, -5, 0, 5, 10)
                cs = (row.kvs.value,) if row.kvs.known else row.kvs.alternatives or (0, 2, 5, 8, 10)
                completions.append(tuple((Fraction(x), Fraction(c) * Fraction(row.rgu.value)) for x, c in product(xs, cs)))
            grid_values = []
            for completion in product(*completions):
                total = sum(w for _, w in completion)
                if total:
                    val = 20 * min(sum(max(x, 0) * w for x, w in completion),
                                   sum(max(-x, 0) * w for x, w in completion)) / total
                    grid_values.append(val)
                    self.assertLessEqual(p.exact_lo, val, (case, rows))
                    self.assertLessEqual(val, p.exact_hi, (case, rows))
            if p.exact_lo is not None:
                self.assertEqual(p.exact_lo, min(grid_values), (case, rows))

    def test_version_isolation_no_upgrade_and_v10_byte_digest_goldens(self):
        # Generated from pinned base fc1e2f3 and independently replay-checked.
        fixture_path = Path(__file__).with_name("strategy_v1_0_golden.json")
        goldens = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
        self.assertEqual(len(goldens), 11)
        for case in goldens:
            with self.subTest(case=case["name"]):
                replay = CalculationSnapshot.from_json(case["snapshot"])
                self.assertEqual(replay.to_json(), case["snapshot"])
                self.assertEqual(replay.input_digest, case["input_digest"])
                run = calculate(replay)
                self.assertEqual(run.to_json(), case["result"])
                self.assertEqual(run.result_digest, case["result_digest"])
                self.assertEqual(run.strategy_version, "1.0.0")
                self.assertNotIn("Pol_lo", run.to_json())

        old = CalculationSnapshot.from_json(goldens[0]["snapshot"])
        new = snapshot((actor(0, 10), actor(1, -10)))
        for executor, wrong in ((PolarizationV1Beta(), new), (PolarizationV1_1Beta(), old),
                                (PolarizationV1_1Beta(), replace(old, strategy_version="1.1.0"))):
            with self.assertRaises(CalculationInputError):
                executor.calculate(wrong)
        with self.assertRaises(CalculationInputError):
            calculate(replace(old, strategy_version="1.1.0"))
        for version in ("1.1", "1.1.1", "latest", "2.0.0"):
            with self.assertRaises(CalculationInputError):
                calculate(replace(old, strategy_version=version))
        with self.assertRaises(CalculationInputError):
            CalculationSnapshotV1_1.from_json(old.to_json())
        with self.assertRaises(CalculationInputError):
            CalculationSnapshot.from_json(new.to_json())


if __name__ == "__main__":
    unittest.main()
