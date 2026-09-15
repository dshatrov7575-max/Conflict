from __future__ import annotations

import hashlib
import json

from django.contrib.auth.models import Group
from django.test import Client, TestCase

from domain.services.analysis_admission import analysis_reader_group_name
from domain.services.project_definitions import project_access_group_name
from domain.services.seed import seed_zhanaozen_demo
from domain.services import zhanaozen_typed_manifest as typed


class AnalysisHTTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = seed_zhanaozen_demo()
        from django.contrib.auth import get_user_model
        cls.user = get_user_model().objects.create_user(username="analysis-reader")
        for name in (
            project_access_group_name(cls.project.pk),
            analysis_reader_group_name(cls.project.pk),
        ):
            group, _ = Group.objects.get_or_create(name=name)
            cls.user.groups.add(group)

    def test_shell_is_same_origin_and_analysis_api_is_canonical_zero_write(self):
        client = Client()
        client.force_login(self.user)
        shell = client.get(
            f"/analysis/projects/{self.project.pk}/workspaces/{typed.WORKSPACE_ID}/"
        )
        self.assertEqual(shell.status_code, 200)
        self.assertIn("default-src 'self'", shell["Content-Security-Policy"])
        self.assertNotIn("Set-Cookie", shell.headers)

        response = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{typed.WORKSPACE_ID}/context/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("Set-Cookie", response.headers)
        raw = response.content
        self.assertEqual(response["ETag"], f'"{hashlib.sha256(raw).hexdigest()}"')
        payload = json.loads(raw)
        digest = payload.pop("response_sha256")
        canonical = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(digest, hashlib.sha256(canonical).hexdigest())

    def test_project_member_without_analysis_capability_gets_neutral_404(self):
        self.user.groups.remove(
            Group.objects.get(name=analysis_reader_group_name(self.project.pk))
        )
        client = Client(); client.force_login(self.user)
        response = client.get(
            f"/api/foundation/analysis/v1/projects/{self.project.pk}/"
            f"workspaces/{typed.WORKSPACE_ID}/context/"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.content)["code"], "ANALYSIS_NOT_FOUND")
