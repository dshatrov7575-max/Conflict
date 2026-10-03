from django.contrib import admin
from django.test import RequestFactory, TestCase

from domain.admin import StableVersionedAdmin
from domain.models import ParameterValue


class AdminAuthorityBoundaryTests(TestCase):
    def test_authoritative_admin_surface_is_read_only(self):
        model_admin = StableVersionedAdmin(ParameterValue, admin.site)
        request = RequestFactory().get("/admin/")
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
