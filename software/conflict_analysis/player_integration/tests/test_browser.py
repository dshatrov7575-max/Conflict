"""Real Chromium E2E. Opt in with PLAYER_INTEGRATION_BROWSER=1 (Node 22+)."""
import json
import os
from pathlib import Path
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from domain.models import ParameterValue
from .test_e2e import PlayerIntegrationHTTPFixture, TEST_APPS


@skipUnless(os.getenv("PLAYER_INTEGRATION_BROWSER") == "1", "Set PLAYER_INTEGRATION_BROWSER=1 for Chromium E2E")
@override_settings(ROOT_URLCONF="player_integration.project_urls", INSTALLED_APPS=TEST_APPS)
class PlayerIntegrationBrowserTests(PlayerIntegrationHTTPFixture, StaticLiveServerTestCase):
    def setUp(self):
        # TransactionTestCase does not call TestCase.setUpTestData.
        type(self).setUpTestData()
        super().setUp()

    def test_browser_selects_two_lanes_and_renders_their_own_results(self):
        self.fill()
        ai_id = self.create_experiment_http("AI")
        self.fill(experiment_id=ai_id, attitudes=(0, 0))
        before = list(ParameterValue.objects.order_by("pk").values())
        env = {
            **os.environ,
            "PR2_BASE_URL": self.live_server_url,
            "PR2_SESSION_COOKIE_NAME": settings.SESSION_COOKIE_NAME,
            "PR2_SESSION_COOKIE_VALUE": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "PR2_LANES": json.dumps([
                {"kind": "HUMAN", "expected": "100", "weights": self.weights(), "path": self.url()},
                {"kind": "AI", "expected": "0", "weights": self.weights(experiment_id=ai_id),
                 "path": self.url(experiment_id=ai_id)},
            ]),
        }
        result = subprocess.run(
            [os.getenv("NODE_BIN", "node"), str(Path(__file__).with_name("browser_e2e.mjs"))],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["lanes"], ["HUMAN", "AI"])
        self.assertTrue(report["same_origin_only"])
        self.assertEqual(before, list(ParameterValue.objects.order_by("pk").values()))
