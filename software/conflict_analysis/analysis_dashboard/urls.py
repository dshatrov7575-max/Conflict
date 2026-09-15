from django.urls import path

from analysis_dashboard import views


app_name = "analysis_dashboard"
urlpatterns = [
    path("", views.entry, name="entry"),
    path(
        "projects/<uuid:project_id>/workspaces/<uuid:workspace_id>/",
        views.workspace,
        name="workspace",
    ),
]
