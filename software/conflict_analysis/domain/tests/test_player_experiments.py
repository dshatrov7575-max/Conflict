from __future__ import annotations

import json
import threading
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase

from domain.api.studio_definitions import project_access_group_name
from domain.enums import ExperimentStatus
from domain.models import (
    ActorElementAssessment, AssessmentSet, AuditEvent, Experiment, ExpertProfile, ImportRun,
    ParameterValue, ProjectWorkspace, TimeSlice,
)
from domain.services import zhanaozen_typed_manifest as typed
from domain.services.player_experiments import (
    G8_REQUIRED_PERMISSIONS, PlayerExperimentError, comparison, create_experiment,
    create_manual_value, create_or_update_expert_profile, import_xlsx,
    list_experiments, list_expert_profiles, list_values, mutate_experiment,
    preview_xlsx, recover_import,
)
from domain.services.player_workspaces import PlayerError
from domain.services.seed import seed_zhanaozen_demo
from domain.services.xlsx_import_profiles import load_profile
from domain.tests.test_player_xlsx_import import profile_workbook


class PlayerExperimentsFixture:
    @classmethod
    def setUpTestData(cls):
        cls.project = seed_zhanaozen_demo()
        cls.workspace = ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        cls.user = get_user_model().objects.create_user(username="g8-experiment-author")
        codenames = [item.removeprefix("domain.") for item in G8_REQUIRED_PERMISSIONS]
        permissions = list(Permission.objects.filter(content_type__app_label="domain", codename__in=codenames))
        if len(permissions) != len(codenames): raise AssertionError("G8 permission fixture drift")
        cls.user.user_permissions.add(*permissions)
        group, _ = Group.objects.get_or_create(name=project_access_group_name(cls.project.pk)); cls.user.groups.add(group)

    def aggregate_body(self, *, kind="AI", suffix=None):
        suffix = suffix or uuid4().hex[:10]; experiment_id, set_id, profile_id = uuid4(), uuid4(), uuid4()
        body = {
            "experiment":{"id":str(experiment_id),"code":f"G8-EXP-{suffix}","version":"1.0.0","name":f"{kind} {suffix}","color":"#255cca","order":0,"method_version":"A5-v0.1"},
            "assessment_set":{"id":str(set_id),"code":f"G8-SET-{suffix}","version":"1.0.0","kind":kind,"name":f"{kind} set","description":"independent lane"},
            "expert_profile":{"id":str(profile_id),"code":f"G8-PROFILE-{suffix}","version":"1.0.0","kind":kind,"display_name":f"{kind} expert","identity_key":f"g8:{kind}:{suffix}","provider":"test" if kind=="AI" else "","model_name":"test-model" if kind=="AI" else "","metadata":{"contract":"FOUNDATION_PLAYER_EXPERT_PROFILE_V1"}},
        }
        return experiment_id, body

    def aggregate(self, *, kind="AI", operation_id=None, suffix=None):
        experiment_id, body = self.aggregate_body(kind=kind, suffix=suffix)
        result=create_experiment(user=self.user,workspace_id=self.workspace.pk,operation_id=str(operation_id or uuid4()),if_match=f'"{typed.MANIFEST_SHA256}"',body=body)
        return result, Experiment.objects.get(pk=experiment_id), body

    @staticmethod
    def value_body(experiment, *, predecessor=None, value=1, version="1.0.0"):
        record=next(row for row in load_profile()["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW")
        time_slice=TimeSlice.objects.get(workspace=experiment.workspace,code=record["time_slice_code"])
        return {"id":str(uuid4()),"code":f"G8-VALUE-{uuid4().hex[:10]}","version":version,"assessment_id":str(uuid4()),"assessment_code":f"G8-ASSESS-{uuid4().hex[:10]}","time_slice_id":str(time_slice.pk),"actor_code":record["source_manifest_actor_code"],"element_code":record["source_manifest_element_code"],"parameter_code":record["canonical_parameter_code"],"status":"UNKNOWN" if value is None else "PROVISIONAL","value":value,"temporal_status":"UNKNOWN","confidence_category":"MEDIUM","rationale":"Exact manual assertion","note":"","supersedes_id":str(predecessor.pk) if predecessor else None}

    def create_value(self, experiment, *, predecessor=None, value=1, version="1.0.0"):
        body=self.value_body(experiment,predecessor=predecessor,value=value,version=version)
        etag=list_values(user=self.user,experiment_id=experiment.pk)["experiment"]["etag"] if predecessor is None else list_values(user=self.user,experiment_id=experiment.pk)["values"][-1]["etag"]
        create_manual_value(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{etag}"',body=body)
        return ParameterValue.objects.get(pk=body["id"])

    def import_ticket(self, *, preview, experiment, operation, request):
        return {
            "contract":"FOUNDATION_PLAYER_XLSX_IMPORT_TICKET_V1","contract_version":"1.0.0",
            "workspace_id":str(self.workspace.pk),"experiment_id":str(experiment.pk),
            "operation_id":str(operation),"raw_file_sha256":preview["raw_file_sha256"],
            "byte_length":preview["byte_length"],"profile_id":request["profile_id"],
            "profile_sha256":preview["profile_sha256"],"sheet":request["sheet"],
            "source_column":request["source_column"],
            "crosswalk_lineage":preview["crosswalk_lineage"],
            "preview_sha256":preview["preview_sha256"],
            "request_plan_sha256":preview["request_plan_sha256"],
        }


class PlayerExperimentsTests(PlayerExperimentsFixture, TestCase):
    def test_assessment_author_permission_family_scope_hiding_and_no_studio_mixing_are_exact(self):
        self.assertEqual(set(self.user.get_all_permissions()),set(G8_REQUIRED_PERMISSIONS)); self.assertEqual(list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"],[])
        outsider=get_user_model().objects.create_user(username=f"outsider-{uuid4()}"); outsider.user_permissions.add(*Permission.objects.filter(content_type__app_label="domain",codename__in=[p.removeprefix("domain.") for p in G8_REQUIRED_PERMISSIONS]))
        with self.assertRaises((PlayerExperimentError,PlayerError)): list_experiments(user=outsider,workspace_id=self.workspace.pk)

    def test_expert_profile_assessment_set_experiment_create_replay_and_receipt_are_atomic(self):
        experiment_id,body=self.aggregate_body(); profile_body=body["expert_profile"]
        profile_operation=uuid4(); created=create_or_update_expert_profile(user=self.user,workspace_id=self.workspace.pk,operation_id=str(profile_operation),if_match=f'"{typed.MANIFEST_SHA256}"',body=profile_body)
        replay=create_or_update_expert_profile(user=self.user,workspace_id=self.workspace.pk,operation_id=str(profile_operation),if_match=f'"{typed.MANIFEST_SHA256}"',body=profile_body)
        self.assertFalse(created.replayed); self.assertTrue(replay.replayed); self.assertEqual(created.body,replay.body)
        profile=list_expert_profiles(user=self.user,workspace_id=self.workspace.pk)["profiles"][0]; profile_body={key:profile_body[key] for key in profile_body}; profile_body["display_name"]="Edited before first use"
        edited=create_or_update_expert_profile(user=self.user,workspace_id=self.workspace.pk,operation_id=str(uuid4()),if_match=f'"{profile["etag"]}"',body=profile_body); self.assertFalse(edited.replayed)
        body["expert_profile"]=profile_body; operation=uuid4(); first=create_experiment(user=self.user,workspace_id=self.workspace.pk,operation_id=str(operation),if_match=f'"{typed.MANIFEST_SHA256}"',body=body); experiment=Experiment.objects.get(pk=experiment_id); second=create_experiment(user=self.user,workspace_id=self.workspace.pk,operation_id=str(operation),if_match=f'"{typed.MANIFEST_SHA256}"',body=body)
        self.assertFalse(first.replayed); self.assertTrue(second.replayed); self.assertEqual(first.body,second.body); self.assertEqual((Experiment.objects.filter(metadata__contract="FOUNDATION_PLAYER_EXPERIMENT_V1").count(),AuditEvent.objects.filter(entity_type="FOUNDATION_PLAYER_EXPERIMENT_V1").count()),(1,1))

    def test_human_and_ai_experiments_keep_independent_values_without_overwrite(self):
        _,ai,_=self.aggregate(kind="AI"); _,human,_=self.aggregate(kind="HUMAN"); ai_value=self.create_value(ai,value=0); human_value=self.create_value(human,value=5)
        self.assertNotEqual(ai.assessment_set_id,human.assessment_set_id); self.assertEqual(ParameterValue.objects.get(pk=ai_value.pk).value,0); self.assertEqual(ParameterValue.objects.get(pk=human_value.pk).value,5)

    def test_used_expert_profile_and_frozen_archived_experiment_guards_fail_closed(self):
        _,experiment,_=self.aggregate(); profile=experiment.expert_profile; body=self.value_body(experiment); operation=uuid4(); value_etag=list_values(user=self.user,experiment_id=experiment.pk)["experiment"]["etag"]
        first=create_manual_value(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{value_etag}"',body=body); self.assertFalse(first.replayed); profile.display_name="changed"
        with self.assertRaises(ValidationError): profile.save()
        with self.assertRaises(ValidationError): ExpertProfile.objects.filter(pk=profile.pk).update(display_name="bulk")
        with self.assertRaises(ValidationError): ExpertProfile.objects.filter(pk=profile.pk).delete()
        profile.refresh_from_db(); profile.display_name="bulk-update"
        with self.assertRaises(ValidationError): ExpertProfile.objects.bulk_update([profile],["display_name"])
        experiment.refresh_from_db()
        with self.assertRaises(ValidationError): Experiment.objects.filter(pk=experiment.pk).update(status=ExperimentStatus.ACTIVE)
        with self.assertRaises(ValidationError): Experiment.objects.filter(pk=experiment.pk).delete()
        experiment.name="bulk-update"
        with self.assertRaises(ValidationError): Experiment.objects.bulk_update([experiment],["name"])
        experiment.refresh_from_db()
        invalid=Experiment(id=uuid4(),workspace=experiment.workspace,expert_profile=profile,assessment_set=experiment.assessment_set,code=f"G8-ACTIVE-{uuid4().hex[:8]}",version="1.0.0",name="Forbidden ACTIVE",experiment_type="ASSESSMENT",status=ExperimentStatus.ACTIVE,metadata={"contract":"FOUNDATION_PLAYER_EXPERIMENT_V1"})
        with self.assertRaises(ValidationError): invalid.save(force_insert=True)
        with self.assertRaises(ValidationError): Experiment.objects.bulk_create([invalid])
        suffix=uuid4().hex[:8]
        legacy_set=AssessmentSet(id=uuid4(),project=self.project,workspace=self.workspace,code=f"LEGACY-SET-{suffix}",version="1.0.0",kind=profile.kind,name="Legacy active set",description="pre-contract")
        legacy_set.save(force_insert=True)
        legacy=Experiment(id=uuid4(),workspace=self.workspace,expert_profile=profile,assessment_set=legacy_set,code=f"LEGACY-EXP-{suffix}",version="1.0.0",name="Legacy active",experiment_type="ASSESSMENT",status=ExperimentStatus.ACTIVE,metadata={})
        legacy.save(force_insert=True); legacy.metadata={"contract":"FOUNDATION_PLAYER_EXPERIMENT_V1"}
        with self.assertRaises(ValidationError): legacy.save(update_fields=["metadata","updated_at"])
        with self.assertRaises(ValidationError): Experiment.objects.filter(pk=legacy.pk).update(metadata={"contract":"FOUNDATION_PLAYER_EXPERIMENT_V1"})
        mutate_experiment(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"][0]["etag"]}"',action="freeze",body={})
        experiment.refresh_from_db(); frozen_at=experiment.frozen_at; self.assertEqual(experiment.status,ExperimentStatus.FROZEN); self.assertIsNotNone(frozen_at)
        frozen_dto=next(row for row in list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"] if row["id"]==str(experiment.pk)); mutate_experiment(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{frozen_dto["etag"]}"',action="archive",body={})
        experiment.refresh_from_db(); self.assertEqual((experiment.status,experiment.frozen_at),(ExperimentStatus.ARCHIVED,frozen_at))
        _,draft,_=self.aggregate(); draft_dto=next(row for row in list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"] if row["id"]==str(draft.pk)); mutate_experiment(user=self.user,experiment_id=draft.pk,operation_id=str(uuid4()),if_match=f'"{draft_dto["etag"]}"',action="archive",body={}); draft.refresh_from_db(); self.assertEqual((draft.status,draft.frozen_at),(ExperimentStatus.ARCHIVED,None))
        replay=create_manual_value(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{value_etag}"',body=body); self.assertTrue(replay.replayed); self.assertEqual(replay.body,first.body)
        with self.assertRaises(PlayerExperimentError): self.create_value(experiment)

    def test_manual_first_value_and_successor_correction_preserve_immutable_history(self):
        _,experiment,_=self.aggregate(); first=self.create_value(experiment,value=1); second=self.create_value(experiment,predecessor=first,value=2,version="1.0.1")
        self.assertEqual(second.supersedes_id,first.pk); self.assertEqual(ParameterValue.objects.filter(actor_element_assessment__experiment=experiment).count(),2)
        with self.assertRaises(ValidationError): first.delete()

    def test_frozen_computed_and_a5_blocked_targets_deny_value_writes(self):
        _,experiment,_=self.aggregate(); dto=list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"][0]
        mutate_experiment(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{dto["etag"]}"',action="freeze",body={})
        with self.assertRaises(PlayerExperimentError): self.create_value(experiment)
        self.assertFalse(any(row["canonical_parameter_code"] for row in load_profile()["records"] if row["migration_status"]!="TRANSFER_WITH_REVIEW"))

    def test_general_comparison_returns_raw_values_without_aggregation_or_fill_across(self):
        _,experiment,_=self.aggregate(); self.create_value(experiment,value=0); result=comparison(user=self.user,workspace_id=self.workspace.pk)
        self.assertIsNone(result["aggregation"]); self.assertEqual(len(result["values"]),1); self.assertEqual(result["values"][0]["value"],0)

    def test_import_candidates_are_experiment_scoped_and_general_does_not_leak_them(self):
        _,one,_=self.aggregate(); _,two,_=self.aggregate(); raw=profile_workbook(); operation=uuid4()
        request={"raw_file":raw,"profile_id":"KZ_ZHANAOZEN_EXPERT_V2_A5_0_1","sheet":"По_главам","source_column":"ИИ_Значение"}; preview=preview_xlsx(user=self.user,experiment_id=one.pk,body=request)
        ticket=self.import_ticket(preview=preview,experiment=one,operation=operation,request=request)
        commit={**request,"preview_sha256":preview["preview_sha256"],"excluded_42_acknowledged":True,"ticket":ticket}; result=import_xlsx(user=self.user,experiment_id=one.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=commit)
        self.assertFalse(result.replayed); run=ImportRun.objects.get(pk=operation); self.assertEqual(run.intended_changes["source_snapshot"]["schema"],"POLARIZATION_V1_IMPORT_SNAPSHOT_V1"); self.assertEqual(run.intended_changes["source_snapshot"]["source_row_count"],330)
        self.assertEqual((ActorElementAssessment.objects.filter(experiment=one).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=one).count()),(144,288)); self.assertFalse(ImportRun.objects.filter(target_experiment=two).exists())
        self.assertEqual(recover_import(user=self.user,experiment_id=one.pk,operation_id=operation)["receipt_sha256"],run.intended_changes["receipt"]["receipt_sha256"])
        dto=next(row for row in list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"] if row["id"]==str(one.pk)); mutate_experiment(user=self.user,experiment_id=one.pk,operation_id=str(uuid4()),if_match=f'"{dto["etag"]}"',action="freeze",body={}); one.refresh_from_db(); self.assertEqual(one.status,"FROZEN")
        replay=import_xlsx(user=self.user,experiment_id=one.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=commit); self.assertTrue(replay.replayed); self.assertEqual(replay.body,result.body)
        with self.assertRaises(PlayerExperimentError) as different_bytes:
            import_xlsx(user=self.user,experiment_id=one.pk,operation_id=str(operation),if_match="not-reparsed",body={**commit,"raw_file":b"not an OOXML package"})
        self.assertEqual(different_bytes.exception.code,"PLAYER_OPERATION_KEY_REUSE")
        with self.assertRaises(PlayerExperimentError) as different_mapping:
            import_xlsx(user=self.user,experiment_id=one.pk,operation_id=str(operation),if_match="not-reparsed",body={**commit,"source_column":"Эксперт_Значение"})
        self.assertEqual(different_mapping.exception.code,"PLAYER_OPERATION_KEY_REUSE")
        with self.assertRaises(PlayerExperimentError): recover_import(user=self.user,experiment_id=two.pk,operation_id=operation)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only frozen G8 concurrency gate")
class PlayerExperimentsPostgreSQLTests(PlayerExperimentsFixture, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.project = seed_zhanaozen_demo()
        self.workspace = ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        self.user = get_user_model().objects.create_user(username="g8-experiment-author")
        codenames = [item.removeprefix("domain.") for item in G8_REQUIRED_PERMISSIONS]
        permissions = list(Permission.objects.filter(
            content_type__app_label="domain", codename__in=codenames,
        ))
        if len(permissions) != len(codenames):
            raise AssertionError("G8 permission fixture drift")
        self.user.user_permissions.add(*permissions)
        group, _ = Group.objects.get_or_create(
            name=project_access_group_name(self.project.pk)
        )
        self.user.groups.add(group)

    def _parallel(self, calls):
        barrier=threading.Barrier(len(calls)); results=[]
        def run(call):
            close_old_connections(); barrier.wait()
            try: results.append(("ok",call()))
            except Exception as exc: results.append(("error",exc))
            finally: close_old_connections()
        threads=[threading.Thread(target=run,args=(call,)) for call in calls]
        for thread in threads: thread.start()
        for thread in threads: thread.join(30)
        self.assertTrue(all(not thread.is_alive() for thread in threads)); return results

    def test_concurrent_experiment_same_key_creates_one_aggregate_and_one_exact_replay(self):
        operation=uuid4(); experiment_id,body=self.aggregate_body()
        results=self._parallel([lambda:create_experiment(user=self.user,workspace_id=self.workspace.pk,operation_id=str(operation),if_match=f'"{typed.MANIFEST_SHA256}"',body=body)]*2)
        self.assertEqual(sum(kind=="ok" for kind,_ in results),2)
        self.assertEqual(sorted(value.replayed for kind,value in results if kind=="ok"),[False,True])
        self.assertEqual((Experiment.objects.filter(pk=experiment_id).count(),AssessmentSet.objects.filter(pk=body["assessment_set"]["id"]).count(),ExpertProfile.objects.filter(pk=body["expert_profile"]["id"]).count(),AuditEvent.objects.filter(pk=operation).count()),(1,1,1,1))
        self.assertEqual(len({value.body for kind,value in results if kind=="ok"}),1)

    def test_concurrent_import_same_key_creates_one_graph_and_one_exact_replay(self):
        _,experiment,_=self.aggregate(); raw=profile_workbook(); operation=uuid4()
        request={"raw_file":raw,"profile_id":"KZ_ZHANAOZEN_EXPERT_V2_A5_0_1","sheet":"По_главам","source_column":"ИИ_Значение"}; preview=preview_xlsx(user=self.user,experiment_id=experiment.pk,body=request)
        ticket=self.import_ticket(preview=preview,experiment=experiment,operation=operation,request=request)
        body={**request,"preview_sha256":preview["preview_sha256"],"excluded_42_acknowledged":True,"ticket":ticket}
        call=lambda:import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=body)
        results=self._parallel([call,call])
        self.assertEqual(sum(kind=="ok" for kind,_ in results),2)
        self.assertEqual(sorted(value.replayed for kind,value in results if kind=="ok"),[False,True])
        self.assertEqual(len({value.body for kind,value in results if kind=="ok"}),1)
        self.assertEqual((ImportRun.objects.filter(pk=operation,target_experiment=experiment).count(),ActorElementAssessment.objects.filter(experiment=experiment).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=experiment).count()),(1,144,288))

    def test_competing_import_keys_into_one_empty_experiment_have_one_commit_and_one_typed_loser(self):
        _,experiment,_=self.aggregate(); raw=profile_workbook(); request={"raw_file":raw,"profile_id":"KZ_ZHANAOZEN_EXPERT_V2_A5_0_1","sheet":"По_главам","source_column":"ИИ_Значение"}; preview=preview_xlsx(user=self.user,experiment_id=experiment.pk,body=request)
        operations=[uuid4(),uuid4()]
        def call(operation):
            ticket=self.import_ticket(preview=preview,experiment=experiment,operation=operation,request=request)
            return import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body={**request,"preview_sha256":preview["preview_sha256"],"excluded_42_acknowledged":True,"ticket":ticket})
        results=self._parallel([lambda:call(operations[0]),lambda:call(operations[1])])
        self.assertEqual(sum(kind=="ok" for kind,_ in results),1)
        errors=[value for kind,value in results if kind=="error"]
        self.assertEqual((len(errors),errors[0].code),(1,"G8_IMPORT_NONEMPTY_EXPERIMENT"))
        self.assertEqual((ImportRun.objects.filter(target_experiment=experiment).count(),ActorElementAssessment.objects.filter(experiment=experiment).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=experiment).count()),(1,144,288))

    def test_concurrent_manual_corrections_have_one_successor_and_one_stale_loser(self):
        _,experiment,_=self.aggregate(); first=self.create_value(experiment); etag=list_values(user=self.user,experiment_id=experiment.pk)["values"][-1]["etag"]
        bodies=[self.value_body(experiment,predecessor=first,value=value,version="1.0.1") for value in (2,3)]
        operations=[uuid4(),uuid4()]
        results=self._parallel([lambda index=index:create_manual_value(user=self.user,experiment_id=experiment.pk,operation_id=str(operations[index]),if_match=f'"{etag}"',body=bodies[index]) for index in range(2)])
        self.assertEqual(sum(kind=="ok" for kind,_ in results),1)
        errors=[value for kind,value in results if kind=="error"]
        self.assertEqual((len(errors),errors[0].code),(1,"PLAYER_STALE"))
        self.assertEqual(ParameterValue.objects.filter(supersedes=first).count(),1)
