#!/usr/bin/env python3
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "weight_sensitivity", HERE / "weight_sensitivity.py"
)
ws = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ws)


def grid():
    return json.loads((HERE / "SENSITIVITY_GRID_V1.json").read_text(encoding="utf-8"))


def factors(worker_pos=-5, worker_kvs=5, company_pos=5, company_kvs=5):
    return {
        "episode_id": ws.EPISODE_ID,
        "ptn_id": ws.PTN_ID,
        "actors": {
            ws.WORKER: {
                "status": "VERIFIED_NUMERIC",
                "POS": worker_pos,
                "KVS": worker_kvs,
            },
            ws.COMPANY: {
                "status": "VERIFIED_NUMERIC",
                "POS": company_pos,
                "KVS": company_kvs,
            },
        },
    }


class WeightSensitivityTests(unittest.TestCase):
    def test_baseline_equal_opposition(self):
        out = ws.run(factors(), grid())
        r = out["baseline"]["result"]
        self.assertEqual(r["P"], "25.00000000")
        self.assertEqual(r["N"], "25.00000000")
        self.assertEqual(r["Pol"], "50.00000000")
        self.assertEqual(r["single_ptn_uno_field"], "50.00000000")

    def test_company_kvs_eight(self):
        out = ws.run(factors(company_kvs=8), grid())
        self.assertEqual(out["baseline"]["result"]["Pol"], "38.46153846")

    def test_rgu_extreme_envelope(self):
        out = ws.run(factors(), grid())
        self.assertEqual(out["envelope"]["Pol_min"], "9.09090909")
        self.assertEqual(out["envelope"]["Pol_max"], "50.00000000")

    def test_positive_q_scale_invariance(self):
        out = ws.run(factors(), grid())
        self.assertTrue(out["positive_q_invariance"]["passed"])
        self.assertEqual(
            out["positive_q_invariance"]["observed_Pol_values"],
            ["50.00000000"],
        )

    def test_q_zero_is_not_area_uno(self):
        out = ws.run(factors(), grid())
        row = next(
            x for x in out["zero_weight_stress"]
            if x["scenario_id"] == "Q_ZERO_EXCLUSION"
        )
        self.assertEqual(row["result"]["Pol"], "50.00000000")
        self.assertIsNone(row["result"]["single_ptn_uno_field"])

    def test_worker_zero_hides_negative_side(self):
        out = ws.run(factors(), grid())
        row = next(
            x for x in out["zero_weight_stress"]
            if x["scenario_id"] == "R_WORKER_ZERO"
        )
        self.assertEqual(row["result"]["P"], "50.00000000")
        self.assertEqual(row["result"]["N"], "0.00000000")
        self.assertEqual(row["result"]["Pol"], "0.00000000")

    def test_company_zero_hides_positive_side(self):
        out = ws.run(factors(), grid())
        row = next(
            x for x in out["zero_weight_stress"]
            if x["scenario_id"] == "R_COMPANY_ZERO"
        )
        self.assertEqual(row["result"]["P"], "0.00000000")
        self.assertEqual(row["result"]["N"], "50.00000000")
        self.assertEqual(row["result"]["Pol"], "0.00000000")

    def test_all_rgu_zero_not_computable(self):
        out = ws.run(factors(), grid())
        row = next(
            x for x in out["zero_weight_stress"]
            if x["scenario_id"] == "R_ALL_ZERO"
        )
        self.assertEqual(row["result"]["ptn_status"], "NOT_COMPUTABLE")
        self.assertIsNone(row["result"]["Pol"])

    def test_missing_company_kvs_blocks_all(self):
        payload = factors()
        payload["actors"][ws.COMPANY] = {
            "status": "UNKNOWN",
            "POS": 5,
            "KVS": None,
        }
        out = ws.run(payload, grid())
        self.assertEqual(out["state"], "NOT_COMPUTABLE")
        self.assertIn("not VERIFIED_NUMERIC", out["reason"])

    def test_scale_both_rgu_invariance(self):
        f = ws._validate_factor_record(factors())
        a = ws.compute_ptn(f, ws.Fraction(1), ws.Fraction(1), ws.Fraction(1))
        b = ws.compute_ptn(f, ws.Fraction(10), ws.Fraction(10), ws.Fraction(1))
        self.assertEqual(a["Pol"], b["Pol"])
        self.assertEqual(a["P"], b["P"])
        self.assertEqual(a["N"], b["N"])

    def test_wrong_actor_set_rejected(self):
        payload = factors()
        payload["actors"].pop(ws.COMPANY)
        out = ws.run(payload, grid())
        self.assertEqual(out["state"], "NOT_COMPUTABLE")

    def test_main_grid_count(self):
        out = ws.run(factors(), grid())
        self.assertEqual(len(out["main_positive_scenarios"]), 7)
        self.assertEqual(len(out["zero_weight_stress"]), 4)


if __name__ == "__main__":
    unittest.main()
