"""Mount the integration alongside all existing Foundation/Player routes."""
from django.urls import include, path

urlpatterns = [
    path("player/calculations/", include("player_integration.urls")),
    path("", include("conflict_analysis.urls")),
]
