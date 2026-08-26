"""Root URL configuration for Conflict Analysis."""

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/foundation/", include("domain.urls")),
]
