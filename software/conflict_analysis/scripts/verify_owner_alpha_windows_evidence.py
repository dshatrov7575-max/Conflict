#!/usr/bin/env python3
"""Verify external exact-Z Windows evidence; absence is never a passing node."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from verify_owner_alpha_package import CONTROL, GateError, canonical, identity, require, strict_json, verify_zip

LAUNCH=("L01","L02","L03","L04","L05","L06")
JOURNEY=(
 "editor_bootstrap_and_arbitrary_structure","publisher_hidden_before_project_grant",
 "exact_project_grant","immutable_definition_publication","nondefault_workspace_projection_complete",
 "immutable_timeslice_reopen","human_ai_distinct_experiments","same_xlsx_distinct_columns",
 "transfer288_method18_recoding24","unknown_distinct_from_zero","general_raw_comparison",
 "exact_fact_fragment_document_original","hidden_private_revoked_nonfingerprinting",
 "restart_identity_receipt_continuity","foundation22_reconciliation_not_full_backup",
 "full_private_backup_restore_graph","restored_sessions_revoked","source_preserved_on_failure",
 "role_scope_and_tab_loss_recovery","destructive_cleanup_disposable_only",
)
NEGATIVES=("interrupted_backup","interrupted_restore","stored_original_missing",
           "runtime_mismatch","migration_mismatch","permission_mismatch","receipt_changed")
def verify_report(report, package, junit_path):
    verified=verify_zip(package)
    manifest=verified["manifest"]
    require(report["schema"]=="G10_WINDOWS_FINAL_ZIP_EVIDENCE_V1"
            and report["zip"]==identity(package)
            and report["source"]==manifest["source"],
            "BLOCKED_G10_ARTIFACT_IDENTITY_GAP","external Windows source/ZIP identity")
    require(report["channel_id"] not in ("",None,"NOT_YET_BOUND","UNKNOWN"),
            "BLOCKED_G10_CI_EVIDENCE_GAP","independently bound execution channel required")
    host=report["host"]
    require(host["os_product_type"]==1 and "Windows 11" in host["caption"]
            and host["os_architecture"]=="x64" and host["process_architecture"]=="x64"
            and int(host["build"])>=22000 and host["virtualization_available"] is True
            and host["wsl2_usable"] is True and host["wsl_import_supported"] is True
            and host["edge_executable_architecture"]=="x64"
            and re.fullmatch(r"\d+\.\d+\.\d+\.\d+",host["edge_version"]) is not None,
            "BLOCKED_G10_WINDOWS_CAPACITY","real Windows 11 x64/WSL2/Edge required")
    require(report["shell"]["executable"] and report["shell"]["version"]
            and report["shell"]["effective_policy"] in ("RemoteSigned","AllSigned","Unrestricted")
            and report["shell"]["policy_list"] and report["shell"]["required_files"],
            "BLOCKED_G10_LAUNCH_ADMISSION","shell/policy/zone/signature/trust observations")
    require(report["offline"] is True and report["download_method"] and report["extraction_method"]
            and report["package_source"]=="downloaded_final_zip"
            and report["configuration_changes"]==[] and report["mocked"] is False,
            "BLOCKED_G10_LAUNCH_ADMISSION","actual downloaded ZIP offline launch")
    require(set(report["launch_cases"])==set(LAUNCH)
            and all(v["result"]=="PASS" and v["observation_sha256"] and v["host_id"]
                    for v in report["launch_cases"].values()),
            "BLOCKED_G10_LAUNCH_ADMISSION","L01-L06 observations cannot be omitted or simulated")
    require(report["launch_cases"]["L05"]["zip"]==identity(package),
            "BLOCKED_G10_ARTIFACT_IDENTITY_GAP","L05 final bytes")
    require(report["journey"].keys()==dict.fromkeys(JOURNEY).keys()
            and all(v is True for v in report["journey"].values()),
            "BLOCKED_G10_CI_EVIDENCE_GAP","full Studio/Player/XLSX/Evidence journey")
    require(set(report["backup_negatives"])==set(NEGATIVES)
            and all(v is True for v in report["backup_negatives"].values()),
            "BLOCKED_G10_BACKUP_RESTORE_GAP","complete R2 failure preservation")
    require(report["user_pks_before"]==report["user_pks_after"]==report["user_pks_restored"]
            and set(report["user_pks_before"])=={"STUDIO_EDITOR","STUDIO_PUBLISHER","PLAYER_ASSESSOR"}
            and len(set(report["user_pks_before"].values()))==3,
            "BLOCKED_G10_ACCESS_PROVISIONING_GAP","canonical principal continuity")
    require(report["public_artifacts_contain_user_backups"] is False
            and report["secrets_in_public_evidence"] is False
            and report["debug_endpoints_after_injection"]==[],
            "BLOCKED_G10_SECRET_LEAK","private bytes/debug endpoint boundary")
    root=ET.parse(junit_path).getroot()
    nodes=root.findall(".//test-case")
    require(len(nodes)==2 and {n.attrib["name"] for n in nodes}==set(CONTROL["tests"]["windows"])
            and all(n.attrib.get("executed")=="True" and n.attrib.get("success")=="True"
                    and n.attrib.get("result")=="Success" for n in nodes),
            "BLOCKED_G10_CI_EVIDENCE_GAP","exact two actually executed Windows tests")
    return {"schema":"G10_VERIFIED_WINDOWS_EVIDENCE_V1","source":manifest["source"],
            "zip":identity(package),"evidence_sha256":hashlib.sha256(canonical(report)).hexdigest(),
            "junit":identity(junit_path),"result":"PASS"}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip",type=Path,required=True)
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--junit",type=Path,required=True)
    args=parser.parse_args()
    print(canonical(verify_report(strict_json(args.evidence.read_bytes()),args.zip,args.junit)).decode(),end="")

if __name__=="__main__":
    main()

