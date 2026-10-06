from importlib import import_module

from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import SimpleTestCase
from django.urls import resolve, reverse


class UnifiedRuntimeContractTests(SimpleTestCase):
    def test_default_settings_install_the_complete_composition_layer(self):
        self.assertEqual(settings.ROOT_URLCONF, "conflict_analysis.urls")
        self.assertTrue(apps.is_installed("player_integration"))
        self.assertTrue(apps.is_installed("scenario_modeling"))
        self.assertEqual(
            resolve("/player/calculations/").namespace,
            "player_integration",
        )
        self.assertEqual(
            resolve("/player/calculations/scenarios/").namespace,
            "scenario_modeling",
        )
        self.assertEqual(
            reverse("player_integration:start"),
            "/player/calculations/",
        )
        self.assertEqual(
            reverse("scenario_modeling:update"),
            "/player/calculations/scenarios/",
        )

    def test_packaged_templates_and_static_assets_are_discoverable(self):
        for template in (
            "player_integration/start.html",
            "player_integration/result.html",
            "scenario_modeling/result.html",
        ):
            with self.subTest(template=template):
                self.assertIsNotNone(get_template(template))
        for asset in (
            "player_integration/result.css",
            "scenario_modeling/scenario.css",
            "scenario_modeling/scenario.js",
        ):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))

    def test_old_opt_in_modules_are_compatibility_aliases_only(self):
        legacy_settings = import_module("player_integration.settings")
        legacy_urls = import_module("player_integration.project_urls")
        root_urls = import_module("conflict_analysis.urls")
        self.assertEqual(legacy_settings.ROOT_URLCONF, "conflict_analysis.urls")
        self.assertEqual(legacy_urls.urlpatterns, root_urls.urlpatterns)
