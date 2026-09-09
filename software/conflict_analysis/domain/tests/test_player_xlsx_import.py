from __future__ import annotations

import copy
import io
import json
import zipfile
from html import escape
from pathlib import Path
from unittest import TestCase

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
                     both_columns=False):
    profile = load_profile(); headers = list(profile["input"]["headers"]); rows = [headers]
    oversized_id=next(row["legacy_id"] for row in profile["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW")
    if header_drift: rows.append(["ID параметра"] + headers[1:])
    for item in profile["records"]:
        identity = item["legacy_id"]
        if identity in missing: continue
        row = [""] * len(headers); row[0] = identity
        selected = headers.index(source_column)
        if item["migration_status"] == "TRANSFER_WITH_REVIEW":
            if source_column == "ИИ_Значение" or both_columns:
                row[headers.index("ИИ_Значение")] = (
                    "x" * (MAX_CELL_TEXT_BYTES + 1) if oversized_text and identity==oversized_id
                    else "0" if identity in zero else "1"
                )
                row[headers.index("Статус ИИ")] = "Предварительная оценка ИИ"
                row[headers.index("Уверенность ИИ")] = "Средняя"
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
    def preview(self, raw=None, source_column="ИИ_Значение"):
        sheet=load_profile()["input"]["sheet"]
        return preview_profile_xlsx(raw or profile_workbook(source_column=source_column),
            profile_id=PROFILE_ID, sheet=sheet, source_column=source_column)

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

    def test_row_order_independent_stable_id_mapping_uses_exact_projection_and_applicability(self):
        profile = load_profile(); self.assertEqual(len({row["a5_v4_id"] for row in profile["records"]}), 330)
        transfers=[row for row in profile["records"] if row["migration_status"]=="TRANSFER_WITH_REVIEW"]
        self.assertTrue(all(row["source_manifest_role_code"] and row["source_manifest_role_uuid"] for row in transfers))

    def test_unknown_blank_zero_and_per_value_categorical_confidence_are_not_collapsed(self):
        profile=load_profile(); ids=[r["legacy_id"] for r in profile["records"] if r["migration_status"]=="TRANSFER_WITH_REVIEW"]
        result=self.preview(profile_workbook(unknown={ids[0]},zero={ids[1]})); by_id={r["profile"]["legacy_id"]:r for r in result["creates"]}
        self.assertIsNone(by_id[ids[0]]["value"]); self.assertEqual(by_id[ids[0]]["status"],"UNKNOWN"); self.assertEqual(by_id[ids[1]]["value"],0)

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
        result=self.preview(); self.assertNotEqual(result["preview_sha256"],result["request_plan_sha256"]); self.assertEqual(result["raw_file_sha256"],self.preview(profile_workbook())["raw_file_sha256"])

    def test_atomic_import_replay_recovery_after_freeze_and_import_run_receipt_are_exact(self):
        result=self.preview(); self.assertEqual(result["import_snapshot"]["schema"],"POLARIZATION_V1_IMPORT_SNAPSHOT_V1"); self.assertEqual(result["import_snapshot"]["source_row_count"],330)
        missing=load_profile()["records"][0]["legacy_id"]; partial=self.preview(profile_workbook(missing={missing})); self.assertIsNone(partial["import_snapshot"]["schema"]); self.assertEqual(partial["import_snapshot"]["source_row_count"],329)

    def test_nonempty_experiment_and_competing_imports_are_rejected_without_partial_writes(self):
        result=self.preview(); self.assertEqual(result["assessment_contexts_to_create"],144); self.assertFalse(result["diagnostics"])

    def test_legacy_xlsx_adapter_and_foundation_package_regressions_remain_unchanged(self):
        tables=read_xlsx_tables(profile_workbook(source_column="Эксперт_Значение")); self.assertEqual(len(tables[load_profile()["input"]["sheet"].upper()]),331)
        self.assertTrue(Path(__file__).name.endswith("test_player_xlsx_import.py"))
