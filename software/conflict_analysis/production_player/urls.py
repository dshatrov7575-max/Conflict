"""GET-only composition; mutation endpoints belong exclusively to Foundation."""

from django.urls import path

from production_player import views


app_name = "production_player"
urlpatterns = [
    path("", views.entry, name="entry"),
    path("projects/<uuid:project_id>/", views.project, name="project"),
    path("workspaces/<uuid:workspace_id>/", views.workspace, name="workspace"),
]
