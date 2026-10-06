from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase
from django.urls import reverse

from production_studio.claim_boundaries import (
    CLAIM_BOUNDARY_CONTRACT_BYTES,
    CLAIM_BOUNDARY_CONTRACT_ID,
    CLAIM_BOUNDARY_CONTRACT_LOCALE,
    CLAIM_BOUNDARY_CONTRACT_PATH,
    CLAIM_BOUNDARY_CONTRACT_SHA256,
    CLAIM_BOUNDARY_CONTRACT_VERSION,
    CLAIM_BOUNDARY_EXPECTED_SIDECAR,
    CLAIM_BOUNDARY_SIDECAR_BYTES,
    CLAIM_BOUNDARY_SIDECAR_PATH,
    ClaimBoundaryContractError,
    load_claim_boundaries,
)


class ProductionStudioClaimBoundaryTests(SimpleTestCase):
    def test_committed_contract_and_sidecar_have_one_exact_identity(self):
        payload = CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()
        sidecar = CLAIM_BOUNDARY_SIDECAR_PATH.read_bytes()
        self.assertEqual(len(payload), CLAIM_BOUNDARY_CONTRACT_BYTES)
        self.assertEqual(len(sidecar), CLAIM_BOUNDARY_SIDECAR_BYTES)
        self.assertEqual(sidecar, CLAIM_BOUNDARY_EXPECTED_SIDECAR)
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            CLAIM_BOUNDARY_CONTRACT_SHA256,
        )
        self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(payload.endswith(b"\n"))
        self.assertFalse(payload.endswith(b"\n\n"))

    def test_contract_envelope_codes_and_russian_non_claims_are_complete(self):
        verified = load_claim_boundaries()
        decoded = json.loads(verified.payload.decode("utf-8"))
        self.assertEqual(verified.contract, CLAIM_BOUNDARY_CONTRACT_ID)
        self.assertEqual(verified.locale, CLAIM_BOUNDARY_CONTRACT_LOCALE)
        self.assertEqual(verified.version, CLAIM_BOUNDARY_CONTRACT_VERSION)
        self.assertEqual(decoded["contract"], CLAIM_BOUNDARY_CONTRACT_ID)
        self.assertEqual(
            [statement["code"] for statement in verified.statements],
            [
                "STATUS",
                "AUTHORITY",
                "TRACEABILITY",
                "SCIENTIFIC_STATUS",
                "UNAVAILABLE_FUNCTIONS",
                "EXPORT_STATUS",
                "BASELINE_SEPARATION",
                "DISTINCT_VALUES",
                "NO_PSEUDO_AGGREGATION",
            ],
        )
        text_by_code = {item["code"]: item["text"] for item in verified.statements}
        self.assertIn("Foundation", text_by_code["AUTHORITY"])
        self.assertIn("не подтверждает", text_by_code["TRACEABILITY"])
        self.assertIn("не заявляются", text_by_code["SCIENTIFIC_STATUS"])
        for forbidden_feature in (
            "scalar Power",
            "POW×SAL",
            "прогнозирование",
            "риск",
            "ранжирование",
            "рекомендации",
            "OCR",
            "LLM",
            "RAG",
        ):
            self.assertIn(forbidden_feature, text_by_code["UNAVAILABLE_FUNCTIONS"])
        self.assertIn("9589796412", text_by_code["BASELINE_SEPARATION"])
        self.assertIn("UNKNOWN", text_by_code["DISTINCT_VALUES"])
        self.assertIn("total/average", text_by_code["NO_PSEUDO_AGGREGATION"])

    def test_any_contract_or_sidecar_byte_drift_fails_closed(self):
        exact_payload = CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()
        exact_sidecar = CLAIM_BOUNDARY_SIDECAR_PATH.read_bytes()
        vectors = (
            (exact_payload[:-1], exact_sidecar),
            (b"\xef\xbb\xbf" + exact_payload, exact_sidecar),
            (exact_payload.replace(b'"locale": "ru"', b'"locale": "en"'), exact_sidecar),
            (exact_payload, exact_sidecar.rstrip(b"\n")),
            (exact_payload, b"0" * len(exact_sidecar)),
        )
        for payload, sidecar in vectors:
            with self.subTest(payload_bytes=len(payload), sidecar_bytes=len(sidecar)):
                with patch(
                    "production_studio.claim_boundaries._read_exact",
                    side_effect=(payload, sidecar),
                ):
                    with self.assertRaises(ClaimBoundaryContractError):
                        load_claim_boundaries()

    def test_every_shell_and_public_contract_fail_closed_if_verification_fails(self):
        urls = (
            reverse("production_studio:entry"),
            reverse(
                "production_studio:definition",
                args=("10000000-0000-4000-8000-000000000099",),
            ),
            reverse("production_studio:claim_boundaries_read_only_v1"),
        )
        with patch(
            "production_studio.views.load_claim_boundaries",
            side_effect=ClaimBoundaryContractError("injected drift"),
        ):
            for url in urls:
                with self.subTest(url=url):
                    response = Client().get(url)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(
                        response.content,
                        b"STUDIO_CLAIM_BOUNDARY_CONTRACT_UNAVAILABLE\n",
                    )
                    self.assertEqual(response["Cache-Control"], "no-store")
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                    self.assertFalse(response.cookies)
