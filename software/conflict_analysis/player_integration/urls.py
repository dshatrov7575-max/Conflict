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
    path(
        "experiments/<uuid:experiment_id>/receipts/",
        views.receipts, name="receipts",
    ),
    path(
        "experiments/<uuid:experiment_id>/receipts/<uuid:operation_id>/",
        views.receipt, name="receipt",
    ),
]
