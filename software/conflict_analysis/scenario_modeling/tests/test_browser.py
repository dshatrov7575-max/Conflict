"""Real Chromium form/slider E2E; SCENARIO_BROWSER=1 opts in."""
import json
import os
from pathlib import Path
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection

from domain.models import AssessmentSet, ParameterValue
from .test_http import ScenarioHTTPFixture


@skipUnless(os.getenv("SCENARIO_BROWSER") == "1" and connection.vendor == "postgresql",
            "Set SCENARIO_BROWSER=1 with PostgreSQL; Foundation triggers forbid SQLite live-server flush")
class ScenarioBrowserTests(ScenarioHTTPFixture, StaticLiveServerTestCase):
    def setUp(self):
        type(self).setUpTestData()
        super().setUp()

    def test_native_form_numeric_slider_replay_reset_and_mobile_layout(self):
        self.fill()
        before_values = list(ParameterValue.objects.order_by("pk").values())
        before_sets = list(AssessmentSet.objects.order_by("pk").values())
        artifacts = Path(__file__).resolve().parents[1] / ".artifacts"
        artifacts.mkdir(exist_ok=True)
        result = subprocess.run(
            [os.getenv("NODE_BIN", "node"), str(Path(__file__).with_name("browser_e2e.mjs"))],
            env={**os.environ,
                 "PR3_BASE_URL": self.live_server_url, "PR3_PATH": self.url(),
                 "PR3_COOKIE_NAME": settings.SESSION_COOKIE_NAME,
                 "PR3_COOKIE_VALUE": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                 "PR3_WEIGHTS": json.dumps(self.weights()),
                 "PR3_PARAMETER": f"attitude:{self.pair[0].pk}", "PR3_ARTIFACTS": str(artifacts)},
            capture_output=True, text=True, encoding="utf-8", timeout=150,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1])["status"], "PASS")
        self.assertEqual(before_values, list(ParameterValue.objects.order_by("pk").values()))
        self.assertEqual(before_sets, list(AssessmentSet.objects.order_by("pk").values()))
