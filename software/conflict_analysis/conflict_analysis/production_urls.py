"""Production URL configuration: no Django Admin mutation surface."""

from django.urls import include, path


urlpatterns = [
    path("api/foundation/", include("domain.urls")),
    path("studio/", include("production_studio.urls")),
    path("player/calculations/scenarios/", include("scenario_modeling.urls")),
    path("player/calculations/", include("player_integration.urls")),
    path("player/", include("production_player.urls")),
]
