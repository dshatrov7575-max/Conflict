from django.urls import path

from studio_showcase import views


app_name = "studio_showcase"

urlpatterns = [
    path("", views.index, name="index"),
    path("health/", views.health, name="health"),
    path("api/fixtures/<str:fixture_name>/", views.fixture_api, name="fixture"),
    path("api/validate/", views.validate_api, name="validate"),
]
