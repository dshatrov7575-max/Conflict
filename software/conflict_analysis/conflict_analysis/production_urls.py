"""Production URL configuration: no Django Admin mutation surface."""

from django.urls import include, path

from conflict_analysis import production_health


urlpatterns = [
    path("health/ready/", production_health.ready, name="production-ready"),
    path("api/foundation/", include("domain.urls")),
    path("studio/", include("production_studio.urls")),
    path("player/calculations/scenarios/", include("scenario_modeling.urls")),
    path("player/calculations/", include("player_integration.urls")),
    path("player/", include("production_player.urls")),
]
