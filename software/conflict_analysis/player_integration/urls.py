from django.urls import path

from . import views

app_name = "player_integration"
urlpatterns = [
    path("", views.start, name="start"),
    path("experiments/<uuid:experiment_id>/", views.experiment, name="experiment"),
    path(
        "experiments/<uuid:experiment_id>/time-slices/<uuid:time_slice_id>/",
        views.result, name="result",
    ),
]
