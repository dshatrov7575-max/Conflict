"""Django application configuration for the read-only Studio shell."""

from django.apps import AppConfig


class ProductionStudioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "production_studio"
    verbose_name = "Production Studio C (read-only)"

    def ready(self) -> None:
        """Fail application startup closed when the fixed claim bytes drift."""

        from production_studio.claim_boundaries import load_claim_boundaries

        load_claim_boundaries()
