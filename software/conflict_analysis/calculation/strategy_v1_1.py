"""Pure V2+V3+V4+V5 envelope executor; all optimization uses exact fractions.

R-B8 uses sorted prefixes, not weight-vertex enumeration. R-B9 enumerates
signs, box vertices and balance intersections only within the R-B15 budget.
The finite PD/KD outer loop also runs for the exact lower bound on fallback.
"""
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction
from itertools import product
from math import prod

from .contracts import CalculationInputError
from .contracts_v1_1 import (
    STRATEGY_ID_V1_1, STRATEGY_VERSION_V1_1, ActorTraceV1_1,
    CalculationRunV1_1, CalculationSnapshotV1_1, PtnResultV1_1,
    ScenarioDeltaV1_1, WitnessRowV1_1,
)


EXACT_EVALUATION_BUDGET_V1_1 = 2 ** 20
_ZERO = Fraction(0)


def publish_v1_1(number: Fraction, direction: str) -> Decimal:
    """One integer rounding operation, independent of the Decimal context."""
    scaled = number * 100_000_000
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    if direction == "up":
        whole += bool(remainder)
    elif direction == "nearest":
        twice = 2 * remainder
        whole += twice > scaled.denominator or (twice == scaled.denominator and whole % 2)
    elif direction != "down":
        raise CalculationInputError("ROUNDING_DIRECTION_INVALID")
    return Decimal((int(whole < 0), tuple(map(int, str(abs(whole)))), -8))


def classify_row_v1_1(row):
    if row.rgu.value is None:
        return "X"
    pd, kd = bool(row.attitude.alternatives), bool(row.kvs.alternatives)
    if pd or kd:
        return "PDKD" if pd and kd else "PD" if pd else "KD"
    if row.attitude.known:
        return "E" if row.kvs.known else "M2a"
    return "M1" if row.kvs.known else "M2b"


@dataclass(frozen=True)
class _ResolvedRow:
    row: object
    position: Fraction | None
    kvs: Fraction | None

    @property
    def cap(self):
        return Fraction(self.row.rgu.value) * (10 if self.kvs is None else self.kvs)


def _choices(value):
    return tuple(map(Fraction, value.alternatives)) if value.alternatives else (
        Fraction(value.value) if value.known else None,)


def _completions(rows):
    options = [tuple(_ResolvedRow(row, x, c) for x, c in product(
        _choices(row.attitude), _choices(row.kvs))) for row in rows]
    yield from product(*options)


def _witness(rows, positions, weights):
    return tuple(WitnessRowV1_1(
        item.row.relation_id, x,
        item.kvs if item.kvs is not None else w / Fraction(item.row.rgu.value)
        if item.row.rgu.value else _ZERO,
        w, item.position if item.row.attitude.alternatives else None,
        item.kvs if item.row.kvs.alternatives else None,
    ) for item, x, w in zip(rows, positions, weights, strict=True))


def _sums(positions, weights):
    return (sum((w * max(x, 0) / 10 for x, w in zip(positions, weights)), _ZERO),
            sum((w * max(-x, 0) / 10 for x, w in zip(positions, weights)), _ZERO),
            sum(weights, _ZERO))


def _lower(rows):
    """R-B8: the smaller of the two sorted-prefix ratio minima."""
    best, witness = None, None
    for side in (1, -1):
        positions = [item.position if item.position is not None else _ZERO for item in rows]
        weights = [item.cap if item.kvs is not None or item.position is None else _ZERO
                   for item in rows]
        variable = sorted((i for i, item in enumerate(rows)
                           if item.kvs is None and item.position is not None),
                          key=lambda i: (max(side * positions[i], 0), rows[i].row.relation_id))
        a, b, total = _sums(positions, weights)
        numerator = a if side == 1 else b
        for index in (None, *variable):
            if index is not None:
                weights[index] = rows[index].cap
                total += weights[index]
                numerator += weights[index] * max(side * positions[index], 0) / 10
            if total:
                value = 200 * numerator / total
                if best is None or value < best:
                    best, witness = value, _witness(rows, positions, weights)
    return best, witness


def _upper(rows):
    """R-B9: vertices plus A=B intersections on each edge, for each sign."""
    free_positions = [i for i, item in enumerate(rows) if item.position is None]
    variables = [i for i, item in enumerate(rows) if item.kvs is None]
    best, witness = None, None
    for signs in product((-10, 10), repeat=len(free_positions)):
        positions = [item.position for item in rows]
        for i, sign in zip(free_positions, signs):
            positions[i] = Fraction(sign)
        for bits in product((0, 1), repeat=len(variables)):
            weights = [item.cap for item in rows]
            for i, bit in zip(variables, bits):
                weights[i] *= bit
            a, b, total = _sums(positions, weights)

            def consider(aa, bb, ww):
                nonlocal best, witness
                if ww:
                    value = 200 * min(aa, bb) / ww
                    if best is None or value > best:
                        best, witness = value, _witness(rows, positions, weights)

            consider(a, b, total)
            # Enumerate every edge once, from its zero endpoint.
            for i, bit in zip(variables, bits):
                if bit or not positions[i]:
                    continue
                crossing = (b - a) * 10 / positions[i]
                if 0 < crossing < rows[i].cap:
                    weights[i] = crossing
                    consider(a + crossing * max(positions[i], 0) / 10,
                             b + crossing * max(-positions[i], 0) / 10, total + crossing)
                    weights[i] = _ZERO
    return best, witness


def _maximum_weight(row):
    return Fraction(row.rgu.value) * (Fraction(row.kvs.value) if row.kvs.known else
                                    max(map(Fraction, row.kvs.alternatives))
                                    if row.kvs.alternatives else 10)


def _minimum_weight(row):
    return Fraction(row.rgu.value) * (Fraction(row.kvs.value) if row.kvs.known else
                                    min(map(Fraction, row.kvs.alternatives))
                                    if row.kvs.alternatives else 0)


def _lower_candidates(row, side):
    if row.attitude.known:
        positions = (Fraction(row.attitude.value),)
    elif row.attitude.alternatives:
        positions = tuple(map(Fraction, row.attitude.alternatives))
    else:
        positions = (Fraction(-10 * side),)
    if row.kvs.known:
        kvs_values = (Fraction(row.kvs.value),)
    elif row.kvs.alternatives:
        kvs_values = tuple(map(Fraction, row.kvs.alternatives))
    else:
        # A fractional-linear minimum over a missing KVS interval is attained
        # at an endpoint. Keeping both endpoints also preserves exact witnesses.
        kvs_values = (_ZERO, Fraction(10))
    rgu = Fraction(row.rgu.value)
    return tuple(
        (x, c, rgu * c, Fraction(max(side * x, 0), 10))
        for x, c in product(positions, kvs_values)
    )


def _lower_all(rows):
    """Exact R-B8 minimum without a Cartesian product of PD/KD alternatives.

    Dinkelbach's finite fractional iteration factors the minimization by row:
    for a trial ratio rho, each independent row minimizes n_i-rho*w_i.
    Missing KVS intervals need only their endpoints.  The iteration uses exact
    Fraction arithmetic and terminates at a feasible global ratio.
    """
    best_value = best_witness = None
    for side in (1, -1):
        candidates = [_lower_candidates(row, side) for row in rows]
        selected = [
            min(options, key=lambda item: (item[3], -item[2], item[0], item[1]))
            for options in candidates
        ]
        total_w = sum((item[2] for item in selected), _ZERO)
        if not total_w:
            continue
        rho = sum((item[2] * item[3] for item in selected), _ZERO) / total_w
        seen = set()
        while rho not in seen:
            seen.add(rho)
            selected = [
                min(options, key=lambda item: (
                    item[2] * (item[3] - rho), -item[2], item[3], item[0], item[1]
                ))
                for options in candidates
            ]
            total_w = sum((item[2] for item in selected), _ZERO)
            if not total_w:
                raise CalculationInputError("LOWER_ENVELOPE_ZERO_WEIGHT_INTERNAL")
            next_rho = sum((item[2] * item[3] for item in selected), _ZERO) / total_w
            if next_rho == rho:
                witness = tuple(
                    WitnessRowV1_1(
                        row.relation_id, item[0], item[1], item[2],
                        item[0] if row.attitude.alternatives else None,
                        item[1] if row.kvs.alternatives else None,
                    )
                    for row, item in zip(rows, selected, strict=True)
                )
                value = 200 * rho
                if best_value is None or value < best_value:
                    best_value, best_witness = value, witness
                break
            rho = next_rho
        else:
            raise CalculationInputError("LOWER_ENVELOPE_ITERATION_INTERNAL")
    return best_value, best_witness


def _evaluation_count(rows):
    alternatives = prod(max(1, len(v.alternatives)) for row in rows
                        for v in (row.attitude, row.kvs))
    signs = sum(not row.attitude.known and not row.attitude.alternatives for row in rows)
    k = sum(not row.kvs.known and not row.kvs.alternatives for row in rows)
    return alternatives * 2 ** signs * (2 ** k + (k * 2 ** (k - 1) if k else 0))


def _ptn(ptn, exclusions):
    warnings, active, trace = set(), [], []
    for row in ptn.actors:
        exclusion = exclusions.get(row.relation_id)
        if exclusion:
            trace.append(ActorTraceV1_1(row, "EXCLUDED", exclusion.exclusion_id, exclusion.rule_id))
            warnings.add("TOPOLOGY_EXCLUSIONS_APPLIED")
            if any(v.known or v.alternatives or v.source_id != "ABSENT"
                   for v in (row.attitude, row.kvs)):
                warnings.add("VALUE_ON_EXCLUDED_RELATION")
        else:
            active.append(row)
            trace.append(ActorTraceV1_1(row, classify_row_v1_1(row)))
    classes = [classify_row_v1_1(row) for row in active]
    empirical = [v for row in active for v in (row.attitude, row.kvs)]
    retro_value = sum(v.known and v.value_status == "RETROSPECTIVE_KNOWLEDGE" for v in empirical)
    retro_time = sum(v.known and v.temporal_status == "RETROSPECTIVE_KNOWLEDGE" for v in empirical)
    na = sum(any(v.value_status == "NOT_APPLICABLE" for v in (row.attitude, row.kvs))
             for row in active)
    if retro_value or retro_time:
        warnings.add("RETROSPECTIVE_INPUTS_PRESENT")
    if na:
        warnings.add("NOT_APPLICABLE_VALUE_TREATED_AS_ABSENT")
    if any(v.value_status == "DISPUTED" for v in empirical):
        warnings.add("DISPUTED_INPUTS_PRESENT")
    eligible = [row for row, cls in zip(active, classes) if cls == "E"]
    a, b, observed_weight = _sums([Fraction(r.attitude.value) for r in eligible],
                                 [Fraction(r.rgu.value) * Fraction(r.kvs.value) for r in eligible])
    observed = 200 * min(a, b) / observed_weight if observed_weight else None
    if observed_weight and (not a or not b):
        warnings.add("ONE_SIDED_OBSERVED")
    reason = "DESIGN_WEIGHT_MISSING" if "X" in classes else "EMPTY_TOPOLOGY" if not active else None
    lo = hi = witness_lo = witness_hi = sharpness = coverage = None
    if reason is None:
        maximum = sum(map(_maximum_weight, active), _ZERO)
        coverage = observed_weight / maximum if maximum else None
        if not maximum:
            reason = "ZERO_WEIGHT"
        else:
            if not sum(map(_minimum_weight, active), _ZERO):
                warnings.add("ZERO_WEIGHT_COMPLETIONS_EXCLUDED")
            sharp = _evaluation_count(active) <= EXACT_EVALUATION_BUDGET_V1_1
            sharpness = "SHARP" if sharp else "OUTER_BOUND_NONSHARP"
            lo, witness_lo = _lower_all(active)
            if sharp:
                for resolved in _completions(active):
                    candidate, witness = _upper(resolved)
                    if candidate is not None and (hi is None or candidate > hi):
                        hi, witness_hi = candidate, witness
            else:
                omega = maximum - observed_weight
                hi = 200 * min(min(a, b) + omega, (a + b + omega) / 2) / maximum
                warnings.add("ENVELOPE_OUTER_RELAXED")
            if observed is not None and not lo <= observed <= hi:
                warnings.add("SUBSET_VALUE_OUTSIDE_ENVELOPE")
    if reason:
        warnings.add(reason)
    status = "NOT_COMPUTABLE" if reason else "COMPLETE" if len(eligible) == len(active) else "BOUNDED"
    return PtnResultV1_1(
        ptn_id=ptn.ptn_id, status=status, reason=reason,
        Pol_point=publish_v1_1(lo, "nearest") if status == "COMPLETE" else None,
        Pol_lo=publish_v1_1(lo, "down") if lo is not None else None,
        Pol_hi=publish_v1_1(hi, "up") if hi is not None else None,
        exact_lo=lo, exact_hi=hi, envelope_sharpness=sharpness,
        witness_lo=witness_lo if status == "BOUNDED" else None,
        witness_hi=witness_hi if status == "BOUNDED" else None,
        Pol_observed_subset=publish_v1_1(observed, "nearest") if observed is not None else None,
        expected_rows=len(active), eligible_rows=len(eligible), excluded_rows=len(trace) - len(active),
        retrospective_value_count=retro_value, retrospective_temporal_count=retro_time,
        not_applicable_rows=na, known_weight_fraction=coverage,
        envelope_width=publish_v1_1(hi - lo, "up") if lo is not None else None,
        kvptn=ptn.kvptn, UNO_contribution_lo=None, UNO_contribution_hi=None,
        warnings=tuple(sorted(warnings)), trace=tuple(trace),
    )


class PolarizationV1_1Beta:
    strategy_id = STRATEGY_ID_V1_1
    strategy_version = STRATEGY_VERSION_V1_1

    def calculate(self, snapshot):
        if type(snapshot) is not CalculationSnapshotV1_1 or (
                snapshot.strategy_id, snapshot.strategy_version) != (self.strategy_id, self.strategy_version):
            raise CalculationInputError("SNAPSHOT_STRATEGY_VERSION_MISMATCH")
        results = tuple(_ptn(p, {e.relation_id: e for e in snapshot.topology_exclusions})
                        for p in snapshot.ptns)
        warnings = {"BETA_POLARIZATION_INDEX", "KVS_KVPTN_DEPENDENCE_NOT_VALIDATED"}
        warnings.update(w for p in results for w in p.warnings)
        missing_q = any(p.kvptn.value is None for p in results)
        positive = [p for p in results if p.kvptn.value is not None and p.kvptn.value > 0]
        total_q = sum((Fraction(p.kvptn.value) for p in positive), _ZERO)
        blocked = any(p.status == "NOT_COMPUTABLE" for p in positive)
        if missing_q:
            warnings.add("MISSING_PTN_WEIGHT")
        if not total_q:
            warnings.add("ZERO_AREA_WEIGHT")
        if blocked:
            warnings.add("NONCOMPUTABLE_POSITIVE_WEIGHT_PTN")
        if not results:
            warnings.add("EMPTY_TOPOLOGY")
        lo = hi = sharpness = None
        status = "NOT_COMPUTABLE"
        if not missing_q and total_q and not blocked:
            lo = sum((Fraction(p.kvptn.value) * p.exact_lo for p in positive), _ZERO) / total_q
            hi = sum((Fraction(p.kvptn.value) * p.exact_hi for p in positive), _ZERO) / total_q
            status = "COMPLETE" if all(p.status == "COMPLETE" for p in positive) else "BOUNDED"
            sharpness = "SHARP" if all(p.envelope_sharpness == "SHARP" for p in positive) else "OUTER_BOUND_NONSHARP"
            results = tuple(replace(p,
                UNO_contribution_lo=publish_v1_1(Fraction(p.kvptn.value) * p.exact_lo / total_q, "down"),
                UNO_contribution_hi=publish_v1_1(Fraction(p.kvptn.value) * p.exact_hi / total_q, "up"),
            ) if p.exact_lo is not None else p for p in results)
        return CalculationRunV1_1(
            snapshot.id, self.strategy_id, self.strategy_version, results,
            publish_v1_1(lo, "nearest") if status == "COMPLETE" else None,
            publish_v1_1(lo, "down") if lo is not None else None,
            publish_v1_1(hi, "up") if hi is not None else None,
            lo, hi, sharpness, tuple(sorted(warnings)), status,
        )


def publish_bound_v1_1(number: Fraction, *, upper: bool) -> Decimal:
    """Publish an envelope endpoint outward to exactly eight decimals."""
    if not isinstance(number, Fraction):
        number = Fraction(number)
    return publish_v1_1(number, "up" if upper else "down")


def _scenario_empirical_overrides_valid(base, scenario):
    base_ptns = {ptn.ptn_id: ptn for ptn in base.ptns}
    scenario_ptns = {ptn.ptn_id: ptn for ptn in scenario.ptns}
    if set(base_ptns) != set(scenario_ptns):
        raise CalculationInputError("SCENARIO_TOPOLOGY_MISMATCH")
    for ptn_id, base_ptn in base_ptns.items():
        scenario_ptn = scenario_ptns[ptn_id]
        if base_ptn.kvptn != scenario_ptn.kvptn:
            raise CalculationInputError("SCENARIO_DESIGN_OVERRIDE_UNSPECIFIED")
        base_rows = {row.relation_id: row for row in base_ptn.actors}
        scenario_rows = {row.relation_id: row for row in scenario_ptn.actors}
        if set(base_rows) != set(scenario_rows):
            raise CalculationInputError("SCENARIO_TOPOLOGY_MISMATCH")
        for relation_id, base_row in base_rows.items():
            scenario_row = scenario_rows[relation_id]
            if base_row.actor_id != scenario_row.actor_id:
                raise CalculationInputError("SCENARIO_TOPOLOGY_MISMATCH")
            if base_row.rgu != scenario_row.rgu:
                raise CalculationInputError("SCENARIO_DESIGN_OVERRIDE_UNSPECIFIED")
            for before, after in ((base_row.attitude, scenario_row.attitude),
                                  (base_row.kvs, scenario_row.kvs)):
                if before != after and not (
                        after.known and not after.alternatives and
                        after.source_id == "SCENARIO"):
                    raise CalculationInputError("SCENARIO_EMPIRICAL_OVERRIDE_INVALID")


def scenario_delta_v1_1(base: CalculationSnapshotV1_1,
                        scenario: CalculationSnapshotV1_1) -> ScenarioDeltaV1_1:
    """R-B23..R-B28: conservative scenario delta over two 1.1 runs."""
    if type(base) is not CalculationSnapshotV1_1 or type(scenario) is not CalculationSnapshotV1_1:
        raise CalculationInputError("SCENARIO_SNAPSHOT_SCHEMA_INVALID")
    if (base.topology_exclusion_set_sha256 != scenario.topology_exclusion_set_sha256 or
            base.topology_exclusions != scenario.topology_exclusions):
        raise CalculationInputError("SCENARIO_TOPOLOGY_EXCLUSION_MISMATCH")
    if base.topology_authority != scenario.topology_authority:
        raise CalculationInputError("SCENARIO_TOPOLOGY_AUTHORITY_MISMATCH")
    for name in ("assessment_kind", "project_id", "time_slice_id", "workspace_id",
                 "time_slice_version", "cutoff_date"):
        if getattr(base, name) != getattr(scenario, name):
            raise CalculationInputError("SCENARIO_BASE_IDENTITY_MISMATCH")
    _scenario_empirical_overrides_valid(base, scenario)

    executor = PolarizationV1_1Beta()
    base_run, scenario_run = executor.calculate(base), executor.calculate(scenario)
    direction = "DIRECTION_NOT_ESTABLISHED"
    if "NOT_COMPUTABLE" in (base_run.status, scenario_run.status):
        return ScenarioDeltaV1_1(base.id, scenario.id, None, None, None, None, direction)

    if base_run.status == scenario_run.status == "COMPLETE":
        exact = scenario_run.exact_lo - base_run.exact_lo
        if exact > 0:
            direction = "INCREASE_ON_ALL_COMPLETIONS"
        elif exact < 0:
            direction = "DECREASE_ON_ALL_COMPLETIONS"
        return ScenarioDeltaV1_1(
            base.id, scenario.id, publish_v1_1(exact, "nearest"),
            None, None, None, direction,
        )

    exact_lo = scenario_run.exact_lo - base_run.exact_hi
    exact_hi = scenario_run.exact_hi - base_run.exact_lo
    if exact_lo > 0:
        direction = "INCREASE_ON_ALL_COMPLETIONS"
    elif exact_hi < 0:
        direction = "DECREASE_ON_ALL_COMPLETIONS"
    return ScenarioDeltaV1_1(
        base.id, scenario.id, None,
        (publish_bound_v1_1(exact_lo, upper=False),
         publish_bound_v1_1(exact_hi, upper=True)),
        (exact_lo, exact_hi), "OUTER_BOUND_NONSHARP", direction,
    )
