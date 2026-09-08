"""Separate application without models or startup persistence."""

from django.apps import AppConfig


class ProductionPlayerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "production_player"
    verbose_name = "Professional Player G7"

    def ready(self) -> None:
        from production_player.claim_boundaries import load_claim_boundaries

        load_claim_boundaries()
