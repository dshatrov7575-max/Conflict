from pathlib import Path
import re

from django.test import SimpleTestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROJECT_ROOT = REPOSITORY_ROOT / "software" / "conflict_analysis"
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "conflict-analysis-unified-gate.yml"
PYTEST_INI = PROJECT_ROOT / "pytest.ini"


class UnifiedRequiredCIGateTests(SimpleTestCase):
    maxDiff = None

    def test_universal_trigger_and_stable_required_check_name(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        pull_request_block = source.split("  push:\n", 1)[0]
        self.assertIn("on:\n  pull_request:\n    paths:\n", source)
        self.assertNotIn("    branches:\n", pull_request_block)
        self.assertIn("  push:\n    branches:\n      - main\n", source)
        self.assertIn("  workflow_dispatch:\n", source)
        self.assertIn("name: Required / Unified Product Gate", source)
        self.assertIn('group: conflict-analysis-unified-${{ github.workflow }}-${{ github.ref }}', source)

    def test_actions_and_postgresql_are_immutable_or_exactly_bounded(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        pins = {
            "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
            "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
            "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
        }
        for action, sha in pins.items():
            self.assertIn(f"uses: {action}@{sha}", source)
        self.assertNotRegex(source, r"uses:\s+actions/(?:checkout|setup-python|setup-node)@v\d")
        self.assertIn("image: postgres:18-alpine", source)
        self.assertIn('runs-on: ubuntu-24.04', source)
        self.assertIn('python-version: "3.12"', source)
        self.assertIn('node-version: "24"', source)

    def test_gate_builds_installs_and_exercises_the_complete_product(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        required_fragments = (
            'python -m pip wheel --no-deps --wheel-dir "$wheel_dir" .',
            'python -m pip install --no-deps --target "$target" "$CONFLICT_ANALYSIS_WHEEL"',
            'assert reverse("player_integration:start") == "/player/calculations/"',
            'assert reverse("scenario_modeling:update") == "/player/calculations/scenarios/"',
            'call_command("collectstatic", interactive=False, verbosity=0, clear=True)',
            'python manage.py makemigrations --check --dry-run --settings=conflict_analysis.settings',
            'python manage.py migrate --noinput --settings=conflict_analysis.settings',
            'python -m pytest --junitxml="$RUNNER_TEMP/conflict-analysis-unified.xml"',
            'PLAYER_INTEGRATION_BROWSER: "1"',
            'SCENARIO_BROWSER: "1"',
            'STUDIO_C0_WHEEL=$wheel',
            'assert not skipped, len(skipped)',
        )
        for fragment in required_fragments:
            self.assertIn(fragment, source)
        self.assertIn('HTTP_PROXY: http://127.0.0.1:9', source)
        self.assertIn('TRANSFORMERS_OFFLINE: "1"', source)

    def test_default_pytest_collects_every_product_layer(self):
        source = PYTEST_INI.read_text(encoding="utf-8")
        self.assertIn("DJANGO_SETTINGS_MODULE = conflict_analysis.settings", source)
        expected = {
            "conflict_analysis/tests",
            "domain/tests",
            "calculation/tests",
            "production_studio/tests",
            "production_player/tests",
            "player_integration/tests",
            "scenario_modeling/tests",
        }
        paths = set(re.findall(r"^    ([a-z_]+/tests)$", source, flags=re.MULTILINE))
        self.assertEqual(paths, expected)
