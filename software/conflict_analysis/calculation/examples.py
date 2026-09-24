"""Synthetic definition vectors; run with python -m calculation.examples."""
from . import ActorInput, CalculationSnapshot, InputValue, PtnInput, calculate
from .contracts import decimal_text


def known(value, source="synthetic"):
    return InputValue("CONFIRMED", value, source, "1")


def example_snapshot(attitudes, *, weights=None, kvs=None, q=1):
    weights = weights if weights is not None else [1] * len(attitudes)
    kvs = kvs if kvs is not None else [1] * len(attitudes)
    return CalculationSnapshot(
        experiment_id="synthetic-experiment", assessment_set_id="synthetic-assessment-set",
        project_id="synthetic-project", workspace_id="synthetic-workspace",
        time_slice_id="synthetic-time", time_slice_version="1", cutoff_date="2026-09-25",
        definition_version_id="synthetic-definition", definition_hash="synthetic-definition-hash",
        ptns=(PtnInput("PTN-1", known(q), tuple(ActorInput(
            f"GU-{index}", f"relation-{index}", f"assessment-{index}",
            known(x) if x is not None else InputValue(), known(c), known(r),
        ) for index, (x, c, r) in enumerate(zip(attitudes, kvs, weights, strict=True)))),),
    )


def definition_vectors():
    return (
        ("DV-01", example_snapshot([0, 0])),
        ("DV-02", example_snapshot([10, -10])),
        ("DV-03", example_snapshot([10, -10, None])),
        ("DV-04", example_snapshot([10, -10], weights=[0, 0])),
        ("DV-05", example_snapshot([10, -10], weights=[3, 1])),
    )


if __name__ == "__main__":
    for name, snapshot in definition_vectors():
        run = calculate(snapshot)
        row = run.ptns[0]
        components = " ".join(f"{metric}={decimal_text(value) if value is not None else 'null'}"
                              for metric, value in (("P", row.P), ("N", row.N), ("A", row.A),
                                                    ("B", row.B), ("Pol", row.Pol), ("UNO", run.UNO)))
        print(f"{name}: {components} "
              f"rows={row.eligible_rows}/{row.expected_rows} status={run.status}")
