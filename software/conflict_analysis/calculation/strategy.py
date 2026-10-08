"""Versioned executable dispatch. Registry metadata remains in Foundation."""
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Protocol

from .contracts import (
    STRATEGY_ID, STRATEGY_VERSION, ActorTrace, CalculationInputError,
    CalculationRun, CalculationSnapshot, Completeness, PtnResult,
)


def _decimal(number: Fraction) -> Decimal:
    """Eight places, ties to even, with no ambient Decimal/float dependency."""
    scaled = abs(number) * 100_000_000
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * remainder
    if twice > scaled.denominator or (twice == scaled.denominator and whole % 2):
        whole += 1
    sign = "-" if number < 0 and whole else ""
    return Decimal(f"{sign}{whole // 100_000_000}.{whole % 100_000_000:08d}")


def _exact_decimal(number: Fraction) -> Decimal:
    """Preserve finite-decimal trace sums/weights, including tiny nonzero W."""
    denominator = number.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise ValueError("Trace intermediate is not a finite decimal.")
    places = max(twos, fives)
    scaled = abs(number.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
    return Decimal((int(number < 0), tuple(int(digit) for digit in str(scaled)), -places))


class CalculationStrategy(Protocol):
    strategy_id: str
    strategy_version: str

    def calculate(self, snapshot: CalculationSnapshot) -> CalculationRun: ...


class PolarizationV1Beta:
    strategy_id = STRATEGY_ID
    strategy_version = STRATEGY_VERSION

    def calculate(self, snapshot: CalculationSnapshot) -> CalculationRun:
        if (snapshot.strategy_id, snapshot.strategy_version) != (self.strategy_id, self.strategy_version):
            raise CalculationInputError("Snapshot strategy identity does not match executor.")
        warnings = {"BETA_POLARIZATION_INDEX", "KVS_KVPTN_DEPENDENCE_NOT_VALIDATED"}
        results, exact_polarizations = [], {}
        for ptn in snapshot.ptns:
            intermediate = []
            W = positive = negative = Fraction(0)
            for row in ptn.actors:
                missing = tuple(name for name in ("attitude", "kvs", "rgu")
                                if not getattr(row, name).known)
                if missing:
                    intermediate.append((row, missing, None, None, None))
                    warnings.add("INCOMPLETE_ACTOR_INPUTS")
                    continue
                x = Fraction(row.attitude.value)
                w = Fraction(row.rgu.value) * Fraction(row.kvs.value)
                # Attitude is -10..10; output components are 0..100.
                p, n = 10 * w * max(x, 0), 10 * w * max(-x, 0)
                W, positive, negative = W + w, positive + p, negative + n
                intermediate.append((row, (), w, p, n))
            eligible = sum(not row[1] for row in intermediate)
            if W:
                P, N = positive / W, negative / W
                exact_polarizations[ptn.ptn_id] = 2 * min(P, N)
                metrics = tuple(_decimal(value) for value in (P, N, P + N, P - N, 2 * min(P, N)))
                status = "COMPLETE" if eligible == len(ptn.actors) else "PARTIAL"
            else:
                metrics = (None,) * 5
                status = "NOT_COMPUTABLE"
                warnings.add("ZERO_ACTOR_WEIGHT")
            trace = tuple(ActorTrace(
                row, not missing, missing,
                None if w is None else _exact_decimal(w),
                None if p is None else _exact_decimal(p),
                None if n is None else _exact_decimal(n),
                _decimal(p / W) if p is not None and W else None,
                _decimal(n / W) if n is not None and W else None,
            ) for row, missing, w, p, n in intermediate)
            results.append(PtnResult(ptn.ptn_id, *metrics, _exact_decimal(W), status,
                                     len(ptn.actors), eligible, ptn.kvptn, None, trace))

        missing_q = any(not ptn.kvptn.known for ptn in snapshot.ptns)
        if missing_q:
            warnings.add("MISSING_PTN_WEIGHT")
        Q = sum((Fraction(ptn.kvptn.value) for ptn in snapshot.ptns if ptn.kvptn.known), Fraction(0))
        blocked_ptn = any(ptn.kvptn.known and ptn.kvptn.value > 0 and
                          ptn.ptn_id not in exact_polarizations for ptn in snapshot.ptns)
        if blocked_ptn:
            warnings.add("NONCOMPUTABLE_POSITIVE_WEIGHT_PTN")
        if not Q:
            warnings.add("ZERO_AREA_WEIGHT")
        if not snapshot.ptns:
            warnings.add("EMPTY_TOPOLOGY")
        UNO = None
        if not missing_q and Q and not blocked_ptn:
            # A known q=0 excludes that PTN from the area, even if W=0 there.
            contributions = {ptn.ptn_id: Fraction(ptn.kvptn.value) *
                             exact_polarizations[ptn.ptn_id] / Q
                             if ptn.kvptn.value else Fraction(0) for ptn in snapshot.ptns}
            UNO = _decimal(sum(contributions.values(), Fraction(0)))
            results = [replace(row, UNO_contribution=_decimal(contributions[row.ptn_id])) for row in results]
        completeness = Completeness(
            sum(row.expected_rows for row in results), sum(row.eligible_rows for row in results),
            len(results), len(exact_polarizations), sum(ptn.kvptn.known for ptn in snapshot.ptns),
        )
        complete = (completeness.expected_rows == completeness.eligible_rows and
                    completeness.expected_ptns == completeness.computable_ptns == completeness.known_ptn_weights)
        status = "NOT_COMPUTABLE" if UNO is None else "COMPLETE" if complete else "PARTIAL"
        return CalculationRun(snapshot.id, self.strategy_id, self.strategy_version,
                              tuple(results), UNO, completeness, tuple(sorted(warnings)), status)


_EXECUTORS = MappingProxyType({(STRATEGY_ID, STRATEGY_VERSION): PolarizationV1Beta()})


def calculate(snapshot: CalculationSnapshot) -> CalculationRun:
    """Exact version dispatch only; no latest-version or method fallback."""
    try:
        executor = _EXECUTORS[(snapshot.strategy_id, snapshot.strategy_version)]
    except KeyError as exc:
        raise CalculationInputError("Unsupported calculation strategy/version.") from exc
    return executor.calculate(snapshot)
