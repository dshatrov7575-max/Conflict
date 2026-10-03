from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from domain import admin as domain_admin  # noqa: F401


class DomainAdminAuthorityTests(TestCase):
    def test_every_registered_domain_model_is_read_only_even_for_superuser(self):
        user = get_user_model().objects.create_superuser(
            username="domain-admin-authority-test",
            email="admin@example.invalid",
            password="test-password",
        )
        request = RequestFactory().get("/admin/")
        request.user = user
        registry = {
            model: model_admin
            for model, model_admin in admin.site._registry.items()
            if model._meta.app_label == "domain"
        }
        self.assertTrue(registry)
        for model, model_admin in registry.items():
            with self.subTest(model=model._meta.label):
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))
                permissions = model_admin.get_model_perms(request)
                self.assertFalse(permissions["add"])
                self.assertFalse(permissions["change"])
                self.assertFalse(permissions["delete"])
