"""Root URL configuration for Conflict Analysis."""

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/foundation/", include("domain.urls")),
    path("studio/", include("production_studio.urls")),
    path("player/calculations/scenarios/", include("scenario_modeling.urls")),
    path("player/calculations/", include("player_integration.urls")),
    path("player/", include("production_player.urls")),
]
