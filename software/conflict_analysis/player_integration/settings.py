"""Opt-in source-tree runtime; existing project settings stay untouched."""
from conflict_analysis.settings import *  # noqa: F403

INSTALLED_APPS = [*INSTALLED_APPS, "player_integration.apps.PlayerIntegrationConfig"]  # noqa: F405
INSTALLED_APPS += ["scenario_modeling.apps.ScenarioModelingConfig"]
ROOT_URLCONF = "player_integration.project_urls"
