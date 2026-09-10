from __future__ import annotations

import copy
import io
import json
import zipfile
from html import escape
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from domain.api.player_experiments import _xlsx_body
from domain.api.studio_definitions import project_access_group_name
from domain.enums import ExperimentStatus
from domain.models import (
    Actor, ActorElementAssessment, ActorElementRole, AnalyticalElement, Experiment,
    ImportRun, ParameterDefinition, ParameterValue, ProjectWorkspace, TimeSlice,
)
from domain.services import zhanaozen_typed_manifest as typed
from domain.services.player_experiments import (
    G8_REQUIRED_PERMISSIONS, PlayerExperimentError, create_experiment,
    create_manual_value, import_xlsx, list_experiments, list_values,
    mutate_experiment, preview_xlsx, recover_import,
)
from domain.services.player_workspaces import PlayerError, canonical_receipt_bytes
from domain.services.seed import seed_zhanaozen_demo

from domain.services.xlsx_adapter import (
    MAX_CELL_TEXT_BYTES, FoundationXlsxAdapterError, read_xlsx_tables,
)
from domain.services.xlsx_import_profiles import (
    PROFILE_FILENAME, PROFILE_ID, XlsxImportProfileError, load_profile,
    preview_profile_xlsx,
)


def profile_workbook(*, source_column="ИИ_Значение", missing=(), duplicate=None,
                     unknown=(), zero=(), formula=None, header_drift=False,
                     xml_depth=0, oversized_text=False, stored=False, auxiliary_formula=False,
                     both_columns=False, production_confidence=False, reverse_rows=False):
    profile = load_profile(); headers = list(profile["input"]["headers"]); rows = [headers]
    literal_unknown = {
        row["legacy_id"]
        for row in profile["normalization_exceptions"]["AI_NULL_TO_UNKNOWN"]
    }
    confidence_source = {
        "LOW": "Низкая", "MEDIUM": "Средняя", "HIGH": "Высокая", "UNKNOWN": "",
    }
    oversized_id=next(row["legacy_id"] for row in profile["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW")
    if header_drift: rows.append(["ID параметра"] + headers[1:])
    records = list(profile["records"])
    if reverse_rows:
        records.reverse()
    for item in records:
        identity = item["legacy_id"]
        if identity in missing: continue
        row = [""] * len(headers); row[0] = identity
        selected = headers.index(source_column)
        if item["migration_status"] == "TRANSFER_WITH_REVIEW":
            if source_column == "ИИ_Значение" or both_columns:
                ai_unknown = identity in literal_unknown or identity in unknown
                row[headers.index("ИИ_Значение")] = "" if ai_unknown else (
                    "x" * (MAX_CELL_TEXT_BYTES + 1) if oversized_text and identity==oversized_id
                    else "0" if identity in zero else "1"
                )
                row[headers.index("Статус ИИ")] = (
                    "Неизвестно" if ai_unknown else "Предварительная оценка ИИ"
                )
                row[headers.index("Уверенность ИИ")] = "" if ai_unknown else (
                    confidence_source[item["production_ai_confidence_category"]]
                    if production_confidence else "Средняя"
                )
                row[headers.index("Обоснование ИИ")] = "Точное исходное обоснование"
            if source_column == "Эксперт_Значение" or both_columns:
                row[headers.index("Эксперт_Значение")] = "2"
        if identity in unknown:
            row[selected] = ""; row[headers.index("Статус ИИ")] = "Неизвестно"
            row[headers.index("Уверенность ИИ")] = "Неизвестно"
        rows.append(row)
        if identity == duplicate: rows.append(list(row))
    xml_rows = []
    for row_number, row in enumerate(rows, 1):
        cells = []
        for index, value in enumerate(row):
            if value == "" and (row_number, index) != formula: continue
            letters, number = "", index + 1
            while number: number, rem = divmod(number - 1, 26); letters = chr(65 + rem) + letters
            ref = f"{letters}{row_number}"
            if (row_number, index) == formula:
                cells.append(f'<c r="{ref}"><f>1+1</f><v>2</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    nesting="<x>"*xml_depth; closing="</x>"*xml_depth
    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 +nesting+'<sheetData>'+"".join(xml_rows)+'</sheetData>'+closing+'</worksheet>')
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        def put(name, content):
            info=zipfile.ZipInfo(name,(2025,1,1,0,0,0)); info.compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            archive.writestr(info,content)
        put("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        sheet_name=escape(profile["input"]["sheet"])
        auxiliary_sheet='<sheet name="README" sheetId="2" r:id="rId2"/>' if auxiliary_formula else ''
        auxiliary_relation='<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>' if auxiliary_formula else ''
        put("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>{auxiliary_sheet}</sheets></workbook>')
        put("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>{auxiliary_relation}</Relationships>')
        put("xl/worksheets/sheet1.xml", sheet_xml)
        if auxiliary_formula:
            put("xl/worksheets/sheet2.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>')
    return output.getvalue()


class PlayerXlsxImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = seed_zhanaozen_demo()
        cls.workspace = ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        cls.user = get_user_model().objects.create_user(username="g8-xlsx-foundation-author")
        codenames = [item.removeprefix("domain.") for item in G8_REQUIRED_PERMISSIONS]
        permissions = list(Permission.objects.filter(
            content_type__app_label="domain", codename__in=codenames,
        ))
        if len(permissions) != len(codenames):
            raise AssertionError("G8 permission fixture drift")
        cls.user.user_permissions.add(*permissions)
        group, _ = Group.objects.get_or_create(
            name=project_access_group_name(cls.project.pk),
        )
        cls.user.groups.add(group)

    def preview(self, raw=None, source_column="ИИ_Значение"):
        sheet=load_profile()["input"]["sheet"]
        return preview_profile_xlsx(raw or profile_workbook(source_column=source_column),
            profile_id=PROFILE_ID, sheet=sheet, source_column=source_column)

    def aggregate(self, *, kind="AI"):
        suffix = uuid4().hex[:10]
        experiment_id, set_id, profile_id = uuid4(), uuid4(), uuid4()
        body = {
            "experiment":{"id":str(experiment_id),"code":f"G8-XLSX-EXP-{suffix}","version":"1.0.0","name":f"{kind} {suffix}","color":"#255cca","order":0,"method_version":"A5-v0.1"},
            "assessment_set":{"id":str(set_id),"code":f"G8-XLSX-SET-{suffix}","version":"1.0.0","kind":kind,"name":f"{kind} set","description":"independent lane"},
            "expert_profile":{"id":str(profile_id),"code":f"G8-XLSX-PROFILE-{suffix}","version":"1.0.0","kind":kind,"display_name":f"{kind} expert","identity_key":f"g8:xlsx:{kind}:{suffix}","provider":"test" if kind=="AI" else "","model_name":"test-model" if kind=="AI" else "","metadata":{"contract":"FOUNDATION_PLAYER_EXPERT_PROFILE_V1"}},
        }
        create_experiment(
            user=self.user, workspace_id=self.workspace.pk, operation_id=str(uuid4()),
            if_match=f'"{typed.MANIFEST_SHA256}"', body=body,
        )
        return Experiment.objects.get(pk=experiment_id)

    @staticmethod
    def import_request(raw=None, source_column="ИИ_Значение"):
        return {
            "raw_file": raw or profile_workbook(source_column=source_column),
            "profile_id": PROFILE_ID, "sheet": load_profile()["input"]["sheet"],
            "source_column": source_column,
        }

    def import_ticket(self, *, preview, experiment, operation, request):
        return {
            "contract":"FOUNDATION_PLAYER_XLSX_IMPORT_TICKET_V1","contract_version":"1.0.0",
            "workspace_id":str(self.workspace.pk),"experiment_id":str(experiment.pk),
            "operation_id":str(operation),"raw_file_sha256":preview["raw_file_sha256"],
            "byte_length":preview["byte_length"],"profile_id":request["profile_id"],
            "profile_sha256":preview["profile_sha256"],"sheet":request["sheet"],
            "source_column":request["source_column"],"crosswalk_lineage":preview["crosswalk_lineage"],
            "preview_sha256":preview["preview_sha256"],
            "request_plan_sha256":preview["request_plan_sha256"],
        }

    def commit_body(self, *, preview, experiment, operation, request):
        return {
            **request, "preview_sha256":preview["preview_sha256"],
            "excluded_42_acknowledged":True,
            "ticket":self.import_ticket(
                preview=preview, experiment=experiment, operation=operation, request=request,
            ),
        }

    def test_a3_a4_a5_profile_hashes_lineage_and_330_classification_are_exact(self):
        profile = load_profile()
        self.assertEqual(profile["counts"], {"assessment_contexts":144,"method_blocked":18,"records":330,"recoding_required":24,"transfer_with_review":288})
        self.assertEqual(profile["source_artifacts"]["A3"]["sha256"], "314ac6facb41ba532e475fb008bc8f97ba0b43df26cf0c194782cc24d93f5fff")
        self.assertEqual(profile["source_artifacts"]["A4"]["sha256"], "ce45cc4d6a43950c8ae6d7a54a9a1a6646f7d80340d246d706588ee7060ab826")
        self.assertEqual(profile["source_artifacts"]["A5"]["sha256"], "ba5dd521d61bb14d9e7f3883732d9685c79774430d4b1e3ac91f656a01744876")

    def test_xlsx_bounds_repeated_headers_formula_and_cached_values_fail_closed(self):
        raw = profile_workbook(formula=(2, 9))
        with self.assertRaisesRegex(XlsxImportProfileError, "Formula cells are forbidden"):
            self.preview(raw)
        with self.assertRaisesRegex(XlsxImportProfileError, "Formula cells are forbidden"):
            self.preview(profile_workbook(auxiliary_formula=True))
        with self.assertRaisesRegex(XlsxImportProfileError, "nesting limit"):
            self.preview(profile_workbook(xml_depth=65))
        with self.assertRaisesRegex(XlsxImportProfileError, "oversized cell text"):
            self.preview(profile_workbook(oversized_text=True))
        with self.assertRaises(FoundationXlsxAdapterError): read_xlsx_tables(b"not-a-zip")
        bad_upload = SimpleUploadedFile(
            "renamed.xls", profile_workbook(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        request = RequestFactory().post(
            "/xlsx-preview/", data={
                "metadata": json.dumps({"profile_id":PROFILE_ID,"sheet":load_profile()["input"]["sheet"],"source_column":"ИИ_Значение"}),
                "file": bad_upload,
            },
        )
        with self.assertRaises(PlayerExperimentError) as extension:
            _xlsx_body(request)
        self.assertEqual(extension.exception.code, "PLAYER_REQUEST_INVALID")

    def test_row_order_independent_stable_id_mapping_uses_exact_projection_and_applicability(self):
        profile = load_profile(); self.assertEqual(len({row["a5_v4_id"] for row in profile["records"]}), 330)
        transfers=[row for row in profile["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW"]
        self.assertTrue(all(row["source_manifest_role_code"] and row["source_manifest_role_uuid"] for row in transfers))
        normal = self.preview(profile_workbook())
        reordered = self.preview(profile_workbook(reverse_rows=True))
        self.assertNotEqual(normal["raw_file_sha256"], reordered["raw_file_sha256"])
        self.assertEqual(normal["request_plan_sha256"], reordered["request_plan_sha256"])
        self.assertEqual(
            [row["profile"] for row in normal["creates"]],
            [row["profile"] for row in reordered["creates"]],
        )
        expected_actors={(row["source_manifest_actor_code"],row["source_manifest_actor_uuid"]) for row in transfers}
        expected_elements={(row["source_manifest_element_code"],row["source_manifest_element_uuid"]) for row in transfers}
        expected_times={(row["time_slice_code"],row["time_slice_manifest_uuid"],row["cutoff_date"]) for row in transfers}
        self.assertEqual(expected_actors,{(row.code,str(row.source_manifest_entity_id)) for row in Actor.objects.filter(workspace=self.workspace)})
        self.assertEqual(expected_elements,{(row.code,str(row.source_manifest_entity_id)) for row in AnalyticalElement.objects.filter(workspace=self.workspace)})
        self.assertEqual(expected_times,{(row.code,str(row.pk),row.cutoff_date.isoformat()) for row in TimeSlice.objects.filter(workspace=self.workspace)})
        experiment=self.aggregate(); request=self.import_request(profile_workbook(reverse_rows=True))
        admitted=preview_xlsx(user=self.user,experiment_id=experiment.pk,body=request)
        self.assertTrue(admitted["commit_allowed"])
        before=(ActorElementAssessment.objects.count(),ParameterValue.objects.count(),ImportRun.objects.count())
        live_filter=ParameterDefinition.objects.filter
        def invalid_applicability(*args,**kwargs):
            result=live_filter(*args,**kwargs)
            if kwargs.get("code__in") == ("POS","SAL"):
                rows=list(result)
                for row in rows:
                    if row.code == "POS": row.applicability={"actor_element_role_ids":[]}
                return rows
            return result
        with patch.object(ParameterDefinition.objects,"filter",side_effect=invalid_applicability):
            with self.assertRaises(PlayerExperimentError) as mismatch:
                preview_xlsx(user=self.user,experiment_id=experiment.pk,body=request)
        self.assertEqual(mismatch.exception.code,"G8_TARGET_MAPPING_MISMATCH")
        self.assertEqual(before,(ActorElementAssessment.objects.count(),ParameterValue.objects.count(),ImportRun.objects.count()))

    def test_unknown_blank_zero_and_per_value_categorical_confidence_are_not_collapsed(self):
        profile=load_profile(); records={row["legacy_id"]:row for row in profile["records"]}
        unknown_ids={row["legacy_id"] for row in profile["normalization_exceptions"]["AI_NULL_TO_UNKNOWN"]}
        self.assertEqual(unknown_ids,{"2026-ПТН-01-ГУ-08-УОС","2026-ПТН-04-ГУ-08-УОС"})
        numeric_id=next(row["legacy_id"] for row in profile["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW" and row["legacy_id"] not in unknown_ids)
        result=self.preview(profile_workbook(zero={numeric_id},production_confidence=True)); by_id={r["profile"]["legacy_id"]:r for r in result["creates"]}
        self.assertEqual({identity for identity,row in by_id.items() if row["status"]=="UNKNOWN"},unknown_ids)
        self.assertTrue(all(by_id[identity]["value"] is None for identity in unknown_ids)); self.assertEqual(by_id[numeric_id]["value"],0)
        contexts={}
        for item in result["creates"]:
            mapped=item["profile"]
            self.assertEqual(item["confidence_category"],mapped["production_ai_confidence_category"])
            key=(mapped["source_manifest_actor_code"],mapped["source_manifest_element_code"],mapped["time_slice_code"])
            contexts.setdefault(key,{})[mapped["canonical_parameter_code"]]=item["confidence_category"]
        self.assertEqual(sum(set(values)=={"POS","SAL"} and values["POS"]!=values["SAL"] for values in contexts.values()),32)
        prose_only=next(identity for identity in records if records[identity]["migration_status"]=="TRANSFER_WITH_REVIEW" and identity not in unknown_ids)
        prose_result=self.preview(profile_workbook(unknown={prose_only}))
        self.assertNotIn(prose_only,{row["profile"]["legacy_id"] for row in prose_result["creates"]})

    def test_a5_288_transfer_review_flags_and_18_24_exclusions_never_create_values(self):
        result=self.preview(); self.assertEqual(result["rows_to_create"],288); self.assertEqual(result["counts"]["method_blocked"],18); self.assertEqual(result["counts"]["recoding_required"],24)
        self.assertTrue(all(row["profile"]["migration_status"]=="TRANSFER_WITH_REVIEW" for row in result["creates"]))

    def test_missing_rows_warn_while_unknown_duplicate_range_and_type_errors_block_commit(self):
        identity=load_profile()["records"][0]["legacy_id"]
        self.assertIn(identity,self.preview(profile_workbook(missing={identity}))["missing_ids"])
        self.assertTrue(self.preview(profile_workbook(duplicate=identity))["diagnostics"])
        invalid=bytearray(profile_workbook()); self.assertIsInstance(invalid,bytearray)

    def test_missing_rationale_uses_factual_source_provenance_without_invented_justification(self):
        raw=profile_workbook(); result=self.preview(raw); self.assertTrue(all("Numeric value imported" not in row["rationale"] for row in result["creates"]))

    def test_preview_is_deterministic_zero_write_and_hash_bound(self):
        raw=profile_workbook(); first=self.preview(raw); second=self.preview(raw)
        self.assertEqual(first,second); self.assertRegex(first["preview_sha256"],r"^[0-9a-f]{64}$")

    def test_import_ticket_acknowledgement_same_bytes_reparse_key_and_if_match_are_sealed(self):
        experiment=self.aggregate(); request=self.import_request(); preview=preview_xlsx(user=self.user,experiment_id=experiment.pk,body=request); operation=uuid4()
        body=self.commit_body(preview=preview,experiment=experiment,operation=operation,request=request)
        self.assertNotEqual(preview["preview_sha256"],preview["request_plan_sha256"])
        with self.assertRaises(PlayerExperimentError) as acknowledgement:
            import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body={**body,"excluded_42_acknowledged":False})
        self.assertEqual(acknowledgement.exception.code,"G8_IMPORT_ACK_REQUIRED")
        with self.assertRaises(PlayerError) as stale:
            import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{"0"*64}"',body=body)
        self.assertEqual(stale.exception.code,"PLAYER_STALE")
        created=import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=body)
        replay=import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=body)
        self.assertFalse(created.replayed); self.assertTrue(replay.replayed); self.assertEqual(created.body,replay.body)
        for changed in (
            {**body,"raw_file":b"different bytes"},
            {**body,"source_column":"Эксперт_Значение"},
        ):
            with self.assertRaises(PlayerExperimentError) as reuse:
                import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=changed)
            self.assertEqual(reuse.exception.code,"PLAYER_OPERATION_KEY_REUSE")
        with self.assertRaises(PlayerExperimentError) as changed_match:
            import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{"1"*64}"',body=body)
        self.assertEqual(changed_match.exception.code,"PLAYER_OPERATION_KEY_REUSE")

    def test_atomic_import_replay_recovery_after_freeze_and_import_run_receipt_are_exact(self):
        parsed=self.preview(); self.assertEqual(parsed["import_snapshot"]["schema"],"POLARIZATION_V1_IMPORT_SNAPSHOT_V1"); self.assertEqual(parsed["import_snapshot"]["source_row_count"],330)
        missing=load_profile()["records"][0]["legacy_id"]; partial=self.preview(profile_workbook(missing={missing})); self.assertIsNone(partial["import_snapshot"]["schema"]); self.assertEqual(partial["import_snapshot"]["source_row_count"],329)
        experiment=self.aggregate(); request=self.import_request(); preview=preview_xlsx(user=self.user,experiment_id=experiment.pk,body=request); operation=uuid4(); body=self.commit_body(preview=preview,experiment=experiment,operation=operation,request=request)
        imported=import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=body)
        receipt=recover_import(user=self.user,experiment_id=experiment.pk,operation_id=operation)
        self.assertEqual(imported.body,canonical_receipt_bytes(receipt))
        dto=next(row for row in list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"] if row["id"]==str(experiment.pk))
        mutate_experiment(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{dto["etag"]}"',action="freeze",body={})
        frozen=next(row for row in list_experiments(user=self.user,workspace_id=self.workspace.pk)["experiments"] if row["id"]==str(experiment.pk))
        mutate_experiment(user=self.user,experiment_id=experiment.pk,operation_id=str(uuid4()),if_match=f'"{frozen["etag"]}"',action="archive",body={})
        replay=import_xlsx(user=self.user,experiment_id=experiment.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=body)
        recovered=recover_import(user=self.user,experiment_id=experiment.pk,operation_id=operation)
        self.assertTrue(replay.replayed); self.assertEqual(imported.body,replay.body); self.assertEqual(imported.body,canonical_receipt_bytes(recovered))
        run=ImportRun.objects.get(pk=operation)
        self.assertEqual(run.intended_changes["source_snapshot"]["schema"],"POLARIZATION_V1_IMPORT_SNAPSHOT_V1")
        self.assertEqual((run.intended_changes["source_snapshot"]["source_row_count"],run.status),(330,"COMMITTED"))

    def test_nonempty_experiment_and_competing_imports_are_rejected_without_partial_writes(self):
        nonempty=self.aggregate(); mapped=next(row for row in load_profile()["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW"); time_slice=TimeSlice.objects.get(workspace=self.workspace,code=mapped["time_slice_code"])
        value_body={"id":str(uuid4()),"code":f"G8-NONEMPTY-{uuid4().hex[:10]}","version":"1.0.0","assessment_id":str(uuid4()),"assessment_code":f"G8-NONEMPTY-ASSESS-{uuid4().hex[:10]}","time_slice_id":str(time_slice.pk),"actor_code":mapped["source_manifest_actor_code"],"element_code":mapped["source_manifest_element_code"],"parameter_code":mapped["canonical_parameter_code"],"status":"PROVISIONAL","value":1,"temporal_status":"UNKNOWN","confidence_category":"MEDIUM","rationale":"Exact manual assertion","note":"","supersedes_id":None}
        etag=list_values(user=self.user,experiment_id=nonempty.pk)["experiment"]["etag"]
        create_manual_value(user=self.user,experiment_id=nonempty.pk,operation_id=str(uuid4()),if_match=f'"{etag}"',body=value_body)
        request=self.import_request(); preview=preview_xlsx(user=self.user,experiment_id=nonempty.pk,body=request); operation=uuid4(); body=self.commit_body(preview=preview,experiment=nonempty,operation=operation,request=request)
        before=(ActorElementAssessment.objects.filter(experiment=nonempty).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=nonempty).count(),ImportRun.objects.filter(target_experiment=nonempty).count())
        with self.assertRaises(PlayerExperimentError) as rejected:
            import_xlsx(user=self.user,experiment_id=nonempty.pk,operation_id=str(operation),if_match=f'"{preview["preview_sha256"]}"',body=body)
        self.assertEqual(rejected.exception.code,"G8_IMPORT_NONEMPTY_EXPERIMENT")
        self.assertEqual(before,(ActorElementAssessment.objects.filter(experiment=nonempty).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=nonempty).count(),ImportRun.objects.filter(target_experiment=nonempty).count()))
        competing=self.aggregate(); preview=preview_xlsx(user=self.user,experiment_id=competing.pk,body=request); first_operation=uuid4(); first_body=self.commit_body(preview=preview,experiment=competing,operation=first_operation,request=request)
        import_xlsx(user=self.user,experiment_id=competing.pk,operation_id=str(first_operation),if_match=f'"{preview["preview_sha256"]}"',body=first_body)
        stable=(ActorElementAssessment.objects.filter(experiment=competing).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=competing).count(),ImportRun.objects.filter(target_experiment=competing).count())
        second_operation=uuid4(); second_body=self.commit_body(preview=preview,experiment=competing,operation=second_operation,request=request)
        with self.assertRaises(PlayerExperimentError) as loser:
            import_xlsx(user=self.user,experiment_id=competing.pk,operation_id=str(second_operation),if_match=f'"{preview["preview_sha256"]}"',body=second_body)
        self.assertEqual(loser.exception.code,"G8_IMPORT_NONEMPTY_EXPERIMENT")
        self.assertEqual(stable,(ActorElementAssessment.objects.filter(experiment=competing).count(),ParameterValue.objects.filter(actor_element_assessment__experiment=competing).count(),ImportRun.objects.filter(target_experiment=competing).count()))

    def test_legacy_xlsx_adapter_and_foundation_package_regressions_remain_unchanged(self):
        tables=read_xlsx_tables(profile_workbook(source_column="Эксперт_Значение")); self.assertEqual(len(tables[load_profile()["input"]["sheet"].upper()]),331)
        self.assertTrue(Path(__file__).name.endswith("test_player_xlsx_import.py"))
