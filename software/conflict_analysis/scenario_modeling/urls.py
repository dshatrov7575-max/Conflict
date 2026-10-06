from django.urls import path
from .views import update

app_name = "scenario_modeling"
urlpatterns = [path("", update, name="update")]
