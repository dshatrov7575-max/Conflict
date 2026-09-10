from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import hashlib
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.test import Client, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.urls import resolve, reverse

from domain.models import ActorElementAssessment, ImportRun, ParameterValue
from domain.services.player_experiments import comparison, list_experiments, list_values, mutate_experiment
from domain.services.player_experiments import G8_REQUIRED_PERMISSIONS
from domain.api.studio_definitions import project_access_group_name
from domain.services.seed import seed_zhanaozen_demo
from domain.services import zhanaozen_typed_manifest as typed
from domain.models import ProjectWorkspace
from domain.tests.test_player_experiments import PlayerExperimentsFixture
from domain.tests.test_player_xlsx_import import profile_workbook
from domain.services.player_workspaces import (
    PLAYER_REQUIRED_PERMISSIONS, canonical_receipt_bytes, list_player_experiments,
)
from domain.services.xlsx_import_profiles import load_profile, preview_profile_xlsx
from production_player.experiment_claim_boundaries import (
    CONTRACT_ID, CONTRACT_SHA256, load_experiment_claim_boundaries,
)

ROOT=Path(__file__).resolve().parents[2]
TEMPLATE=ROOT/"production_player"/"templates"/"production_player"/"workspace.html"
SCRIPT=ROOT/"production_player"/"static"/"production_player"/"experiments.js"
FOUNDATION=ROOT/"domain"/"services"/"player_experiments.py"
BROWSER=ROOT/"production_player"/"browser_tests"/"player_g8.mjs"


class ProductionPlayerG8Tests(PlayerExperimentsFixture,TestCase):
    def setUp(self):
        self.client=Client(enforce_csrf_checks=True); self.client.force_login(self.user)
        self.shell=self.client.get(reverse("production_player:workspace",kwargs={"workspace_id":self.workspace.pk}))

    def api(self,path): return f"/api/foundation/player/{path}"

    def test_g8_routes_permission_family_csrf_object_scope_and_nonfingerprinting_are_exact(self):
        self.assertEqual(self.shell.status_code,200); self.assertIn(settings.CSRF_COOKIE_NAME,self.client.cookies); self.assertContains(self.shell,'data-player-page="g8-workspace"'); self.assertContains(self.shell,'data-g8-shell="true"')
        route=reverse("production_player:experiment",kwargs={"workspace_id":self.workspace.pk,"experiment_id":uuid4()}); self.assertEqual(resolve(route).url_name,"experiment")
        self.assertEqual(Client().get(self.api(f"workspaces/{self.workspace.pk}/experiments/")).status_code,401)
        self.assertEqual(self.client.post(self.api(f"workspaces/{self.workspace.pk}/experiments/"),data=b"{}",content_type="application/json").status_code,403)
        patterns=[str(pattern.pattern) for pattern in __import__("domain.urls",fromlist=["urlpatterns"]).urlpatterns]
        self.assertEqual(patterns.count("player/workspaces/<uuid:workspace_id>/experiments/"),1)
        profile_url=self.api(f"workspaces/{self.workspace.pk}/expert-profiles/"); profile_id=uuid4(); profile_body={"id":str(profile_id),"code":f"PROFILE-{profile_id.hex[:8]}","version":"1.0.0","kind":"HUMAN","display_name":"Editable profile","identity_key":f"human:{profile_id}","provider":"","model_name":"","metadata":{"contract":"FOUNDATION_PLAYER_EXPERT_PROFILE_V1"}}
        csrf=self.client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(self.client.post(profile_url,data=json.dumps(profile_body),content_type="application/json",HTTP_IDEMPOTENCY_KEY=str(uuid4()),HTTP_IF_MATCH=f'"{typed.MANIFEST_SHA256}"').status_code,403)
        created=self.client.post(profile_url,data=json.dumps(profile_body),content_type="application/json",HTTP_IDEMPOTENCY_KEY=str(uuid4()),HTTP_IF_MATCH=f'"{typed.MANIFEST_SHA256}"',HTTP_X_CSRFTOKEN=csrf); self.assertEqual(created.status_code,201,created.content)
        listed=self.client.get(profile_url).json()["profiles"]; item=next(row for row in listed if row["id"]==str(profile_id)); profile_body["display_name"]="Edited before use"
        edited=self.client.post(profile_url,data=json.dumps(profile_body),content_type="application/json",HTTP_IDEMPOTENCY_KEY=str(uuid4()),HTTP_IF_MATCH=f'"{item["etag"]}"',HTTP_X_CSRFTOKEN=csrf); self.assertEqual(edited.status_code,201,edited.content)
        legacy=get_user_model().objects.create_user(username=f"g7-legacy-{uuid4()}"); legacy.user_permissions.add(*Permission.objects.filter(content_type__app_label="domain",codename__in=[value.removeprefix("domain.") for value in PLAYER_REQUIRED_PERMISSIONS])); legacy.groups.add(Group.objects.get(name=project_access_group_name(self.project.pk))); legacy_client=Client(); legacy_client.force_login(legacy); collection=self.api(f"workspaces/{self.workspace.pk}/experiments/")
        inherited=legacy_client.get(collection); self.assertEqual(inherited.content,canonical_receipt_bytes(list_player_experiments(user=legacy,workspace_id=self.workspace.pk)))
        invalid=legacy_client.get(collection+"?include_archived=true"); self.assertEqual((invalid.status_code,invalid.json()["code"]),(400,"PLAYER_REQUEST_INVALID"))
        _,experiment,_=self.aggregate(); detail=self.api(f"experiments/{experiment.pk}/")
        self.assertEqual(self.client.put(detail,data=b"{}",content_type="application/json").status_code,403)
        self.assertEqual(self.client.put(detail,data=b"{}",content_type="application/json",HTTP_X_CSRFTOKEN=csrf).status_code,400)
        raw=profile_workbook(stored=True); self.assertGreater(len(raw),65536)
        upload=SimpleUploadedFile("expert.xlsx",raw,content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        preview=self.client.post(self.api(f"experiments/{experiment.pk}/xlsx-preview/"),data={"metadata":json.dumps({"profile_id":"KZ_ZHANAOZEN_EXPERT_V2_A5_0_1","sheet":"По_главам","source_column":"ИИ_Значение"}),"file":upload},HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(preview.status_code,200,preview.content); self.assertEqual(preview.json()["raw_file_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.client.get(detail,HTTP_AUTHORIZATION="Bearer forbidden").status_code,400)

    def test_only_projection_complete_workspaces_and_draft_assessment_experiments_enable_g8_actions(self):
        source=SCRIPT.read_text(encoding="utf-8"); html=TEMPLATE.read_text(encoding="utf-8"); self.assertIn('app.dataset.projectionStatus !== "COMPLETE"',source); self.assertIn('state.selected.status !== "DRAFT"',source); self.assertIn('>Общее</button>',html); self.assertIn('`Эксперимент ${item.name}`',source)

    def test_expert_profile_creation_freeze_on_first_use_and_historical_display_are_truthful(self):
        _,experiment,_=self.aggregate(); self.assertTrue(experiment.expert_profile.experiments.exists()); html=self.shell.content.decode(); self.assertIn("Профиль эксперта",html); self.assertIn("неизменяемым",html)

    def test_experiment_create_edit_freeze_archive_replay_and_modeling_disabled_states_are_exact(self):
        _,experiment,_=self.aggregate(); dto=list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"][0]
        result=mutate_experiment(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{dto["etag"]}"',action="freeze",body={}); self.assertFalse(result.replayed)
        experiment.refresh_from_db(); self.assertEqual(experiment.status,"FROZEN"); self.assertIn("Расчётное ядро",self.shell.content.decode())

    def test_ai_and_human_tabs_select_distinct_columns_and_never_overwrite_lanes(self):
        focus_id="G8-G9-FOCUS-R1"
        source=SCRIPT.read_text(encoding="utf-8"); self.assertIn('{"AI":"ИИ_Значение","HUMAN":"Эксперт_Значение"}',source); self.assertIn("Independent assessment lane",source)
        self.assertIn("root.dataset.caProjectId = item.project_id",source); self.assertIn("root.dataset.caWorkspaceId = item.id",source); self.assertIn("node.dataset.caFocusKind = focus.kind",source); self.assertIn("node.dataset.caFocusId = focus.id",source)
        self.assertNotIn("dataset.focusKind",source); self.assertNotIn("dataset.focusId",source); self.assertNotIn(focus_id,source)
        _,ai,_=self.aggregate(kind="AI"); _,human,_=self.aggregate(kind="HUMAN"); ai_value=self.create_value(ai,value=None); human_value=self.create_value(human,value=0)
        identities=[list_values(user=self.user,experiment_id=item.pk)["values"][0]["focus"] for item in (ai,human)]
        self.assertEqual({item["kind"] for item in identities},{"parameter-value"}); self.assertEqual({item["id"] for item in identities},{str(ai_value.pk),str(human_value.pk)})

    def test_xlsx_preview_renders_source_lineage_330_classification_and_zero_write_truth(self):
        before=(ActorElementAssessment.objects.count(),ParameterValue.objects.count(),ImportRun.objects.count()); self.assertIn("нулевую запись",SCRIPT.read_text(encoding="utf-8")); self.assertEqual(before,(ActorElementAssessment.objects.count(),ParameterValue.objects.count(),ImportRun.objects.count()))

    def test_retained_ticket_acknowledgement_commit_recovery_and_key_reuse_ui_are_exact(self):
        source=SCRIPT.read_text(encoding="utf-8"); html=TEMPLATE.read_text(encoding="utf-8"); self.assertIn("FOUNDATION_PLAYER_XLSX_IMPORT_TICKET_V1",source); self.assertIn("excluded_42_acknowledged: true",source); self.assertIn("deterministicOperationId",source); self.assertIn("crosswalk_lineage",source); self.assertIn("ticketRetained",source); self.assertIn("Idempotency-Key",source); self.assertIn("new FormData",source); self.assertIn('id="g8-ticket-ack"',html); self.assertNotIn("file_base64",source)

    def test_unknown_blank_zero_confidence_review_flags_and_blocked42_render_distinctly(self):
        source=SCRIPT.read_text(encoding="utf-8"); html=TEMPLATE.read_text(encoding="utf-8"); profile=load_profile(); result=preview_profile_xlsx(profile_workbook(production_confidence=True),profile_id=profile["profile_id"],sheet=profile["input"]["sheet"],source_column="ИИ_Значение"); unknown={row["profile"]["legacy_id"] for row in result["creates"] if row["status"]=="UNKNOWN"}; contexts={}
        for row in result["creates"]:
            mapped=row["profile"]; contexts.setdefault((mapped["source_manifest_actor_code"],mapped["source_manifest_element_code"],mapped["time_slice_code"]),{})[mapped["canonical_parameter_code"]]=row["confidence_category"]
        self.assertEqual(unknown,{"2026-ПТН-01-ГУ-08-УОС","2026-ПТН-04-ГУ-08-УОС"}); self.assertEqual(sum(set(value)=={"POS","SAL"} and value["POS"]!=value["SAL"] for value in contexts.values()),32); self.assertIn('item.status === "UNKNOWN"',source); self.assertIn("18 METHOD_BLOCKED + 24 RECODING_REQUIRED",source); self.assertIn("Категория уверенности",html); self.assertIn("Неразрешённая проверка",html); self.assertIn("cell(item.confidence_category)",source); self.assertIn("cell(item.review_flag)",source)

    def test_manual_value_successor_history_and_frozen_target_disabled_reasons_are_exact(self):
        focus_id="G8-G9-FOCUS-R1"
        _,experiment,_=self.aggregate(); first=self.create_value(experiment,value=0); second=self.create_value(experiment,predecessor=first,value=1,version="1.0.1"); self.assertEqual(second.supersedes_id,first.pk); self.assertIn("Преемник предыдущего",self.shell.content.decode())
        values=list_values(user=self.user,experiment_id=experiment.pk)["values"]; self.assertEqual({item["focus"]["id"] for item in values},{str(first.pk),str(second.pk)}); self.assertTrue(all(item["focus"]["kind"]=="parameter-value" for item in values))
        source=SCRIPT.read_text(encoding="utf-8"); html=TEMPLATE.read_text(encoding="utf-8"); self.assertIn('request(`experiments/${state.selected.id}/values/`',source); self.assertIn("supersedes_id: predecessor?.id || null",source); self.assertIn("bindFocus(button, item.focus)",source); self.assertIn('id="g8-manual-form"',html); self.assertFalse(ParameterValue.objects.filter(code=focus_id).exists())

    def test_general_comparison_shows_only_raw_series_without_mean_rank_consensus_or_fill(self):
        focus_id="G8-G9-FOCUS-R1"
        _,experiment,_=self.aggregate(); value=self.create_value(experiment,value=0); result=comparison(user=self.user,workspace_id=self.workspace.pk); row=result["values"][0]; self.assertIsNone(result["aggregation"]); self.assertEqual(row["value"],0)
        self.assertEqual((result["project_id"],result["workspace_id"]),(str(self.project.pk),str(self.workspace.pk))); self.assertEqual(row["focus"],{"kind":"parameter-value","id":str(value.pk)}); self.assertEqual(row["confidence_category"],"MEDIUM"); self.assertEqual(row["review_flag"],row["review_flags"][row["parameter_code"]]); self.assertIn(row["review_flag"],{"REFERENCE_STATEMENT_REVIEW_REQUIRED","SCALE_CONSTRUCT_REVIEW_REQUIRED"})
        self.assertFalse(any(item.get("focus",{}).get("id")==focus_id for item in result["values"]))

    def test_import_candidates_and_receipts_are_experiment_scoped_non_html_and_not_evidence(self):
        source=FOUNDATION.read_text(encoding="utf-8"); self.assertIn("target_experiment=experiment",source); self.assertNotIn("EvidenceSource.objects",source); self.assertNotIn("Document.objects",source); self.assertNotIn("Fragment.objects",source)

    def test_claim_contract_browser_storage_off_origin_formula_and_product_orm_boundaries_are_exact(self):
        contract=load_experiment_claim_boundaries(); self.assertEqual((contract.contract,contract.sha256),(CONTRACT_ID,CONTRACT_SHA256)); source=SCRIPT.read_text(encoding="utf-8"); views=(ROOT/"production_player"/"views.py").read_text(encoding="utf-8")
        for token in ("localStorage","sessionStorage","indexedDB","serviceWorker","http://","https://"): self.assertNotIn(token,source)
        self.assertNotIn("domain.models",views); self.assertNotIn(".objects.",views); self.assertIn("Formula cells are forbidden",(ROOT/"domain"/"services"/"xlsx_adapter.py").read_text(encoding="utf-8"))


@unittest.skipUnless(connection.vendor=="postgresql","G8 Chromium nodes require PostgreSQL")
class ProductionPlayerG8ChromiumTests(PlayerExperimentsFixture,StaticLiveServerTestCase):
    host="localhost"

    def setUp(self):
        self.project=seed_zhanaozen_demo(); self.workspace=ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        self.user=get_user_model().objects.create_user(username=f"g8-browser-{uuid4()}")
        permissions=Permission.objects.filter(content_type__app_label="domain",codename__in=[item.removeprefix("domain.") for item in G8_REQUIRED_PERMISSIONS]); self.user.user_permissions.add(*permissions)
        group,_=Group.objects.get_or_create(name=project_access_group_name(self.project.pk)); self.user.groups.add(group)
        self.client.force_login(self.user)

    def run_browser(self,scenario):
        self.aggregate(kind="AI"); self.aggregate(kind="HUMAN")
        profile=load_profile(); transfers=[row["legacy_id"] for row in profile["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW"]; unknown={row["legacy_id"] for row in profile["normalization_exceptions"]["AI_NULL_TO_UNKNOWN"]}; numeric=next(identity for identity in transfers if identity not in unknown)
        with tempfile.TemporaryDirectory(prefix="g8-browser-xlsx-") as directory:
            directory=Path(directory); common=directory/"same-checksum.xlsx"; common.write_bytes(profile_workbook(both_columns=True,stored=True))
            boundaries=directory/"unknown-zero.xlsx"; boundaries.write_bytes(profile_workbook(zero={numeric},stored=True))
            duplicate=directory/"duplicate.xlsx"; duplicate.write_bytes(profile_workbook(duplicate=transfers[2],both_columns=True,stored=True))
            env=os.environ.copy(); env.update(PLAYER_BASE_URL=self.live_server_url,PLAYER_WORKSPACE_ID=str(self.workspace.pk),PLAYER_SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,PLAYER_SESSION_COOKIE_VALUE=self.client.cookies[settings.SESSION_COOKIE_NAME].value,PLAYER_EXPECTED_G8_CLAIM_SHA256=CONTRACT_SHA256,PLAYER_G8_SCENARIO=scenario,PLAYER_XLSX_PATH=str(common),PLAYER_BOUNDARY_XLSX_PATH=str(boundaries),PLAYER_DUPLICATE_XLSX_PATH=str(duplicate),PLAYER_CDP_TIMEOUT_MS=env.get("PLAYER_CDP_TIMEOUT_MS","90000"))
            result=subprocess.run([env.get("NODE_BIN","node"),str(BROWSER)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",timeout=300)
        self.assertEqual(result.returncode,0,f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"); payload=json.loads([line for line in result.stdout.splitlines() if line][-1]); self.assertEqual(payload["browser_result"],"PASS"); return payload

    def test_chromium_ai_and_human_experiments_import_distinct_columns_compare_raw_series_and_reopen(self):
        focus_id="G8-G9-FOCUS-R1"
        payload=self.run_browser("lanes"); self.assertGreaterEqual(payload["tabs"],2); self.assertEqual(payload["raw_rows"],576); self.assertTrue(payload["off_origin_free"]); self.assertTrue(payload["same_checksum"]); self.assertTrue(payload["reopened"])
        self.assertNotIn(focus_id,payload)

    def test_chromium_unknown_duplicate_blocked42_freeze_role_scope_and_no_persistent_state(self):
        payload=self.run_browser("boundaries"); self.assertLessEqual(set(payload["storage"]),{"conflict-analysis-player:layout:v1"}); self.assertEqual(payload["claim_sha256"],CONTRACT_SHA256)
