#!/usr/bin/env python3
"""Fail-closed source, payload and archive verification for the bounded G10 slice."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

CONTROL = json.loads('{"base_head":"c6c7118080ab1a1dcb86216f4092dabcf8125be7","base_tree":"5a4a40431e72fb6b942b895225ce11bba2898052","base_parent":"22f0f173a941de88d6920b6e19821168e9b30cc8","readme_blob":"e0da5bcf5f24809f6ca788a1a8f6b0f0144bf1f3","migration":"domain/migrations/0019_analysis_geography.py","migration_blob":"8a2a5b3dfa750932ddb17228dfb476c5e3e88b03","allowlist":["software/conflict_analysis/README.md",".github/workflows/conflict-analysis-owner-alpha-package.yml","software/conflict_analysis/docs/adr/0017-owner-alpha-windows-wsl-package.md","software/conflict_analysis/owner_alpha_package/START_HERE_RU.txt","software/conflict_analysis/owner_alpha_package/manifest.schema.json","software/conflict_analysis/owner_alpha_package/linux/Containerfile","software/conflict_analysis/owner_alpha_package/linux/build-rootfs.sh","software/conflict_analysis/owner_alpha_package/linux/owner-alpha-supervisor.sh","software/conflict_analysis/owner_alpha_package/linux/owner-alpha-health.sh","software/conflict_analysis/owner_alpha_package/linux/nginx.conf","software/conflict_analysis/owner_alpha_package/linux/gunicorn.conf.py","software/conflict_analysis/owner_alpha_package/linux/wsl.conf","software/conflict_analysis/owner_alpha_package/windows/OwnerAlpha.Common.psm1","software/conflict_analysis/owner_alpha_package/windows/OwnerAlpha.Cdp.psm1","software/conflict_analysis/owner_alpha_package/windows/Install-OwnerAlpha.ps1","software/conflict_analysis/owner_alpha_package/windows/Start-OwnerAlpha.ps1","software/conflict_analysis/owner_alpha_package/windows/Grant-Publisher.ps1","software/conflict_analysis/owner_alpha_package/windows/Status-OwnerAlpha.ps1","software/conflict_analysis/owner_alpha_package/windows/Stop-OwnerAlpha.ps1","software/conflict_analysis/owner_alpha_package/windows/Reset-OwnerAlpha.ps1","software/conflict_analysis/owner_alpha_package/windows/Uninstall-OwnerAlpha.ps1","software/conflict_analysis/owner_alpha_package/tests/test_manifest.py","software/conflict_analysis/owner_alpha_package/tests/test_linux_contract.py","software/conflict_analysis/owner_alpha_package/tests/OwnerAlpha.Windows.Contract.Tests.ps1","software/conflict_analysis/owner_alpha_package/tests/OwnerAlpha.Windows.WslE2E.Tests.ps1","software/conflict_analysis/scripts/build_owner_alpha_package.py","software/conflict_analysis/scripts/verify_owner_alpha_package.py","software/conflict_analysis/scripts/verify_owner_alpha_windows_evidence.py"],"tests":{"portable":["test_manifest_schema_exact_chain_refs_versions_hashes_artifacts_and_nonclaims","test_archive_is_deterministic_case_safe_traversal_free_and_cmd_wrappers_are_exact","test_rootfs_has_exact_runtime_versions_users_permissions_and_no_secrets_build_tools_or_source_tree","test_postgresql_socket_nginx_static_gunicorn_loopback_and_no_lan_configuration_are_exact","test_clean_rootfs_runs_migrations_collectstatic_help_and_readiness_without_schema_drift","test_access_secret_transport_public_receipt_and_three_profile_material_never_leak","test_build_binds_exact_accepted_chain_g10_tree_wheel_sbom_notices_and_normalized_rootfs","test_package_scripts_verify_integrity_before_install_and_never_bypass_execution_policy","test_backup_restore_stop_reset_and_uninstall_have_exact_nondestructive_or_destructive_boundaries","test_preexisting_empty_private_pid_files_start_and_restart_without_traceback"],"pester":["test_preflight_rejects_unsupported_windows_wsl_edge_path_port_acl_and_stale_identity_before_import","test_install_verifies_all_bytes_imports_one_exact_wsl2_distribution_and_reconciles_exact_replay","test_start_generates_no_public_secret_and_binds_only_the_frozen_loopback_origin","test_access_prepare_stream_is_memory_only_and_exact_three_profile_permissions_are_preserved","test_cdp_sets_exact_cookie_in_three_acl_profiles_then_closes_every_debug_endpoint","test_studio_editor_publisher_and_player_assessor_sessions_and_project_scope_are_separate","test_status_restart_and_stop_are_replay_safe_and_database_and_receipt_state_persists","test_stop_requires_no_busy_unknown_confirmation_and_revokes_before_profile_deletion","test_backup_restore_reset_and_uninstall_require_exact_confirmation_and_leave_the_declared_state","test_no_lan_postgres_gunicorn_debug_port_normal_edge_profile_or_secret_exposure"],"windows":["test_windows_owner_alpha_complete_three_profile_studio_player_xlsx_evidence_package_backup_and_restart","test_windows_owner_alpha_loss_scope_negative_recovery_restore_and_destructive_cleanup"]},"predecessors":[{"name":"F0L","head":"bfbd6b94c98ad27378c1452e38a69bf8b1fb169f","tree":"4806308745d46726c71eec38b3acac71f31b1542","acceptance":"#85/5530604165"},{"name":"F1","head":"d2f5a881e10dbb688371e8c5add6bf9375404738","tree":"7f5fd4f321282a48a799698861ce6f2bd3940cd1","acceptance":"#84/5561033107"},{"name":"FD08","head":"68b14882a06b2e90710ebd06e584dc5300fdfe7e","tree":"5969ee705ae935bf305a1b2531bc3bc77ade03cb","acceptance":"#23/5585330480"},{"name":"G7","head":"319450a64cb381df2e392027c64de157e2ed830c","tree":"95a8a2a5a7248dd3ec030963c3b25709d49364b0","acceptance":"#25/5591235510"},{"name":"G8","head":"df537ee138088a1fc691cc89a257259817db4644","tree":"67739a84d7bcc9406cbb830d9a58656b05eee06a","acceptance":"#29/5624279071"},{"name":"G9","head":"561ef5327bf655a558adb21c54d0fdf0559d7024","tree":"5b209c782e1ac1a4783b01391dd59d813559ce57","acceptance":"#26/5632713857"}],"sentinels":{"software/conflict_analysis/README.md":"e0da5bcf5f24809f6ca788a1a8f6b0f0144bf1f3","software/conflict_analysis/pyproject.toml":"61befae98fa81af0ffd2e40f3943c5b9c77a796a","software/conflict_analysis/conflict_analysis/settings.py":"c384d860388b328b897d8b808867d330d029f1fd","software/conflict_analysis/conflict_analysis/urls.py":"aa290e9b4b28720864001dfe44e113f16aedfdf6","software/conflict_analysis/domain/models.py":"f2352f54d938ce377f5a2cfd9d6b90e67c039193","software/conflict_analysis/domain/enums.py":"dd50f597199711bfa66d37fc40e8908f9ea9879b","software/conflict_analysis/domain/urls.py":"a834024cd4dfb666812147b0e9c830168bd489cf","software/conflict_analysis/domain/migrations/0018_workspace_assessment_projection.py":"292a8eb4abafeef80d6efc7d3c2d4cda5f771fd9",".github/workflows/conflict-analysis.yml":"773515daf483050fa936fcaa1709fadf73c5b0df","software/conflict_analysis/domain":"78e3f0aa20f4e8b9bdb0853eee5678c82efc244c","software/conflict_analysis/production_player":"b1dc6c79704f9fcafa8272e2c22489dbd06a209e","software/conflict_analysis/production_studio":"6e953eaf47101b441cb703d4da2d784eb69f3eff"}}')
CONTROL["tests"]["portable"].append("test_mvp7_zero_permission_profile_matrix_geography_write_and_restart_persistence")
SCHEMA = "MVP7_PACKAGE_MANIFEST_V1"
PACKAGE_VERSION = "0.7.0-r1-candidate"
MANIFEST_NAME = SCHEMA + ".json"
PROFILE_NAMES = ("STUDIO_EDITOR", "STUDIO_PUBLISHER", "PLAYER_ASSESSOR")
WRAPPERS = {
    "INSTALL_CONFLICT_ANALYSIS.cmd": ("Install-OwnerAlpha.ps1", ""),
    "START_CONFLICT_ANALYSIS.cmd": ("Start-OwnerAlpha.ps1", ""),
    "STOP_CONFLICT_ANALYSIS.cmd": ("Stop-OwnerAlpha.ps1", ""),
    "DIAGNOSTICS.cmd": ("Status-OwnerAlpha.ps1", ""),
    "BACKUP_CONFLICT_ANALYSIS.cmd": ("Stop-OwnerAlpha.ps1", "-Backup"),
    "RESTORE_CONFLICT_ANALYSIS.cmd": ("Install-OwnerAlpha.ps1", "-Restore"),
    "RESET_CONFLICT_ANALYSIS.cmd": ("Reset-OwnerAlpha.ps1", ""),
    "UNINSTALL_CONFLICT_ANALYSIS.cmd": ("Uninstall-OwnerAlpha.ps1", ""),
}
WINDOWS_FILES = tuple(Path(p).name for p in CONTROL["allowlist"]
                      if "/owner_alpha_package/windows/" in p)
PAYLOAD_NAMES = frozenset({
    "START_HERE_RU.txt", "manifest.schema.json", "SBOM.cdx.json",
    "THIRD_PARTY_NOTICES.txt", "evidence/package-build-evidence.json",
    "rootfs/conflict-analysis-functional-alpha-rootfs.tar",
    *WRAPPERS, *("windows/" + name for name in WINDOWS_FILES),
})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


class GateError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(code + ": " + detail)
        self.code = code


def require(condition: Any, code: str, detail: str) -> None:
    if not condition:
        raise GateError(code, detail)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError) as exc:
        raise GateError("BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "invalid JSON") from exc


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(),
            "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "regular artifact required")
    return {"filename": path.name, "bytes": path.stat().st_size,
            "sha256": sha256_file(path)}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, "BLOCKED_G10_PARENT_IDENTITY_DRIFT",
            "Git identity query failed: " + args[0])
    return result.stdout.strip()


LOCK = strict_json((Path(__file__).resolve().parents[1] / "installer/source.lock.json").read_bytes())

def allowed_installer_path(path: str) -> bool:
    return (path == ".github/workflows/conflict-analysis-mvp7-installer.yml"
            or path.startswith("software/conflict_analysis/installer/")
            or path.startswith("software/conflict_analysis/owner_alpha_package/")
            or path in {"software/conflict_analysis/scripts/build_owner_alpha_package.py",
                        "software/conflict_analysis/scripts/verify_owner_alpha_package.py",
                        "software/conflict_analysis/scripts/verify_owner_alpha_windows_evidence.py"}
            or (path.startswith("software/conflict_analysis/docs/") and "/" not in path.removeprefix("software/conflict_analysis/docs/") and "installer" in path))

CORRECTIVE_PATHS = frozenset({
    "software/conflict_analysis/owner_alpha_package/linux/nginx.conf",
    "software/conflict_analysis/owner_alpha_package/linux/owner-alpha-supervisor.sh",
    "software/conflict_analysis/owner_alpha_package/tests/test_linux_contract.py",
    "software/conflict_analysis/owner_alpha_package/tests/test_manifest.py",
    "software/conflict_analysis/installer/test_contract.py",
    "software/conflict_analysis/installer/source.lock.json",
    "software/conflict_analysis/scripts/verify_owner_alpha_package.py",
})

READINESS_PATHS = CORRECTIVE_PATHS - {"software/conflict_analysis/owner_alpha_package/linux/nginx.conf"}

RESTORE_PATHS = READINESS_PATHS

TRANSACTION_PATHS = frozenset(['software/conflict_analysis/installer/Install-Mvp7.ps1', 'software/conflict_analysis/installer/Mvp7.Setup.psm1', 'software/conflict_analysis/installer/Mvp7.Preflight.Tests.ps1', 'software/conflict_analysis/installer/Test-Mvp7Contract.ps1', 'software/conflict_analysis/installer/test_contract.py', 'software/conflict_analysis/installer/source.lock.json', 'software/conflict_analysis/installer/build_setup.py', 'software/conflict_analysis/owner_alpha_package/windows/Install-OwnerAlpha.ps1', 'software/conflict_analysis/owner_alpha_package/windows/OwnerAlpha.Common.psm1', 'software/conflict_analysis/owner_alpha_package/tests/OwnerAlpha.Windows.Contract.Tests.ps1', 'software/conflict_analysis/scripts/verify_owner_alpha_package.py'])

UNINSTALL_PATHS = frozenset([
    "software/conflict_analysis/installer/Mvp7.Setup.psm1",
    "software/conflict_analysis/owner_alpha_package/tests/OwnerAlpha.Windows.Contract.Tests.ps1",
    "software/conflict_analysis/installer/test_contract.py",
    "software/conflict_analysis/installer/source.lock.json",
    "software/conflict_analysis/scripts/verify_owner_alpha_package.py",
])

def delivery_identity(repo: Path, *, final: bool = True) -> dict[str, Any]:
    head=git(repo,"rev-parse","HEAD")
    base=LOCK["installer_parent"]  # Accepted R1 run still belongs to F, never A.
    first=LOCK["installer_commit_a"]
    second=LOCK["installer_commit_b"]
    third=LOCK["installer_commit_c"]
    fourth=LOCK["installer_commit_d"]
    fifth=LOCK["installer_commit_e"]
    require(git(repo,"branch","--show-current") in ("",LOCK["installer_branch"]),"BLOCKED_MVP7_HISTORY","branch")
    require(git(repo,"show","-s","--format=%P",first)==base,"BLOCKED_MVP7_HISTORY","A ordinary parent F")
    require(git(repo,"show","-s","--format=%B",first)==LOCK["installer_message"],"BLOCKED_MVP7_HISTORY","A message")
    require(git(repo,"show","-s","--format=%P",second)==first,"BLOCKED_MVP7_HISTORY","B ordinary parent A")
    require(git(repo,"show","-s","--format=%B",second)==LOCK["correction_message"],"BLOCKED_MVP7_HISTORY","B message")
    delta_b=git(repo,"diff","--name-status","--no-renames",first,second).splitlines()
    require(set(delta_b)=={"M\t"+p for p in CORRECTIVE_PATHS},"BLOCKED_MVP7_SOURCE_MUTATION","exact B modified paths")
    require(git(repo,"show","-s","--format=%P",third)==second,"BLOCKED_MVP7_HISTORY","C ordinary parent B")
    require(git(repo,"show","-s","--format=%B",third)==LOCK["readiness_correction_message"],"BLOCKED_MVP7_HISTORY","C message")
    delta_c=git(repo,"diff","--name-status","--no-renames",second,third).splitlines()
    require(set(delta_c)=={"M\t"+p for p in READINESS_PATHS},"BLOCKED_MVP7_SOURCE_MUTATION","exact C modified paths")
    require(git(repo,"show","-s","--format=%P",fourth)==third,"BLOCKED_MVP7_HISTORY","D ordinary parent C")
    require(git(repo,"show","-s","--format=%B",fourth)==LOCK["restore_correction_message"],"BLOCKED_MVP7_HISTORY","D message")
    delta_d=git(repo,"diff","--name-status","--no-renames",third,fourth).splitlines()
    require(set(delta_d)=={"M\t"+p for p in RESTORE_PATHS},"BLOCKED_MVP7_SOURCE_MUTATION","exact D modified paths")
    require(git(repo,"rev-list","--count",base+".."+fourth)=="4","BLOCKED_MVP7_HISTORY","four frozen installer predecessors")
    require(git(repo,"show","-s","--format=%P",fifth)==fourth,"BLOCKED_MVP7_HISTORY","E ordinary parent D")
    require(git(repo,"show","-s","--format=%B",fifth)==LOCK["transaction_correction_message"],"BLOCKED_MVP7_HISTORY","E message")
    delta_e=git(repo,"diff","--name-status","--no-renames",fourth,fifth).splitlines()
    require(set(delta_e)=={"M\t"+p for p in TRANSACTION_PATHS},"BLOCKED_MVP7_SOURCE_MUTATION","exact E modified paths")
    require(git(repo,"rev-list","--count",base+".."+fifth)=="5","BLOCKED_MVP7_HISTORY","five frozen installer predecessors")
    if final:
        require(not git(repo,"status","--porcelain=v1","--untracked-files=all"),"BLOCKED_MVP7_HISTORY","clean committed checkout required")
        require(git(repo,"show","-s","--format=%P",head)==fifth,"BLOCKED_MVP7_HISTORY","E2 ordinary parent E")
        require(git(repo,"rev-list","--count",base+".."+head)=="6","BLOCKED_MVP7_HISTORY","six installer commits")
        require(git(repo,"show","-s","--format=%B",head)==LOCK["uninstall_correction_message"],"BLOCKED_MVP7_HISTORY","E2 message")
        delta=git(repo,"diff","--name-status","--no-renames",fifth,head).splitlines()
        require(set(delta)=={"M\t"+p for p in UNINSTALL_PATHS},"BLOCKED_MVP7_SOURCE_MUTATION","exact E2 modified paths")
        parent=fifth
    else:
        require(head==fifth,"BLOCKED_MVP7_HISTORY","precommit parent E")
        parent=fourth
    paths=git(repo,"diff","--name-only",base,head).splitlines()
    require(all(allowed_installer_path(p) for p in paths),"BLOCKED_MVP7_SOURCE_MUTATION","installer allowlist")
    return {"head":head,"tree":git(repo,"rev-parse","HEAD^{tree}"),"parent":parent}

def source_identity(repo: Path, *, final: bool = True) -> dict[str, Any]:
    delivery_identity(repo,final=final)
    source=LOCK["source"];head=source["head"]
    require(git(repo,"rev-parse",head+"^{tree}")==source["tree"],"BLOCKED_MVP7_SOURCE_MUTATION","exact C tree")
    require(git(repo,"show","-s","--format=%P",head)==source["parent"],"BLOCKED_MVP7_SOURCE_MUTATION","exact C parent")
    require(git(repo,"rev-parse",head+":software/conflict_analysis/"+CONTROL["migration"])==CONTROL["migration_blob"],"BLOCKED_MVP7_SOURCE_MUTATION","migration 0019")
    return source.copy()


def safe_member(name: str) -> bool:
    if not name or name != unicodedata.normalize("NFC", name) or "\\" in name:
        return False
    p = PurePosixPath(name)
    return (not p.is_absolute() and all(part not in ("", ".", "..") for part in name.split("/"))
            and ":" not in name and all(ord(c) >= 32 for c in name)
            and not any(part.endswith((".", " ")) for part in p.parts))


def safe_rootfs_member(name: str) -> bool:
    if not name or name != unicodedata.normalize("NFC", name) or "\\" in name:
        return False
    p = PurePosixPath(name)
    return (not p.is_absolute() and all(part not in ("", ".", "..") for part in name.split("/"))
            and all(ord(c) >= 32 for c in name)
            and not any(part.endswith((".", " ")) for part in p.parts))


def verify_manifest(manifest: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator
    schema_path = Path(__file__).resolve().parents[1] / "owner_alpha_package/manifest.schema.json"
    errors = list(Draft202012Validator(strict_json(schema_path.read_bytes())).iter_errors(manifest))
    require(not errors, "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "manifest schema validation")
    from build_owner_alpha_package import PINS
    require(manifest["runtime"] == {**PINS, "offline_install": True},
            "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "exact frozen dependency closure")
    require(manifest["schema"] == SCHEMA and manifest["package_version"] == PACKAGE_VERSION,
            "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "manifest contract")
    source = manifest["source"]
    require(source == LOCK["source"], "BLOCKED_MVP7_SOURCE_MUTATION", "application wheel must be exact C")
    delivery=manifest["delivery"]
    require(set(delivery)=={"head","tree","parent"} and all(GIT_SHA.fullmatch(v) for v in delivery.values())
            and delivery["parent"]==LOCK["installer_commit_e"],"BLOCKED_MVP7_HISTORY","delivery identity")
    require(manifest["acceptance"] == {"acceptance_run":35216652773,"WINDOWS11_WSL2_E2E":"BLOCKED_NO_RUNNER",
            "CLEAN_PC_SMOKE":"NOT_EXECUTED","PARTNER_RELEASE_READY":False},"BLOCKED_MVP7_NONCLAIM","acceptance boundary")
    require(manifest["migration"] == {"path": CONTROL["migration"], "blob": CONTROL["migration_blob"]},
            "BLOCKED_G10_UNAUTHORIZED_MIGRATION", "migration identity")
    require(manifest["test_registry"] == CONTROL["tests"],
            "BLOCKED_G10_TEST_REGISTRY_DRIFT", "literal test registry")
    require(manifest["profiles"] == list(PROFILE_NAMES),
            "BLOCKED_G10_PROFILE_ISOLATION_GAP", "three isolated profiles")
    require(set(manifest["payload"]) == PAYLOAD_NAMES,
            "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "payload membership")
    require(manifest["artifact_order"] == ["P", "M", "S", "Z", "E", "acceptance_index"],
            "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "artifact order")
    require(manifest["nonclaims"] == {
        "production_ready": False, "owner_test_authorized": False, "release": False,
        "final_windows_acceptance": False, "sqlite_runtime": False, "native_windows_server": False,
    }, "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "nonclaims")
    for name, meta in manifest["payload"].items():
        require(safe_member(name) and set(meta) == {"bytes", "sha256"} and
                type(meta["bytes"]) is int and meta["bytes"] >= 0 and SHA256.fullmatch(meta["sha256"]),
                "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "invalid member identity")
    require(manifest["runtime"]["python"] == "3.12.14" and
            manifest["runtime"]["postgresql"] == "18.4",
            "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "CPython/PostgreSQL pin")
    for image in manifest["runtime"]["oci"].values():
        require(re.fullmatch(r"docker\.io/library/(python|postgres)@sha256:[0-9a-f]{64}", image),
                "BLOCKED_G10_NONDETERMINISTIC_BUILD", "immutable OCI image required")
    require(manifest["runtime"]["offline_install"] is True,
            "BLOCKED_G10_NONDETERMINISTIC_BUILD", "offline wheel installation required")


def expected_sums(manifest: dict[str, Any], manifest_raw: bytes) -> bytes:
    entries = {name: item["sha256"] for name, item in manifest["payload"].items()}
    entries[MANIFEST_NAME] = hashlib.sha256(manifest_raw).hexdigest()
    return "".join(f"{entries[name]}  {name}\n" for name in sorted(entries)).encode("ascii")


def verify_zip(path: Path, *, expected_sha256: str | None = None,
               expected_bytes: int | None = None) -> dict[str, Any]:
    observed = identity(path)
    if expected_sha256 is not None:
        require(observed["sha256"] == expected_sha256 and observed["bytes"] == expected_bytes,
                "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "downloaded ZIP byte identity")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        require(len(names) == len(set(n.casefold() for n in names)) and
                all(safe_member(n) for n in names),
                "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "unsafe or case-colliding archive")
        require(all(not i.is_dir() and not (i.flag_bits & 1) and
                    (i.external_attr >> 16) & 0o170000 != 0o120000 for i in infos),
                "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "ZIP links/encryption/directories forbidden")
        require(set(names) == PAYLOAD_NAMES | {MANIFEST_NAME, "SHA256SUMS"},
                "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "exact archive membership")
        manifest_raw = archive.read(MANIFEST_NAME)
        manifest = strict_json(manifest_raw)
        verify_manifest(manifest)
        require(manifest_raw == canonical(manifest),
                "BLOCKED_G10_NONDETERMINISTIC_BUILD", "noncanonical manifest")
        require(archive.read("SHA256SUMS") == expected_sums(manifest, manifest_raw),
                "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "SHA256SUMS coverage/order")
        for name, meta in manifest["payload"].items():
            with archive.open(name) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            require(actual == meta["sha256"] and archive.getinfo(name).file_size == meta["bytes"],
                    "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", name)
        build = strict_json(archive.read("evidence/package-build-evidence.json"))
        require(build["source"] == manifest["source"] and build["final_windows_acceptance"] is False,
                "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "build evidence source/nonclaim")
    return {"zip": observed, "manifest": manifest, "verified": True}


def rootfs_inventory(path: Path) -> dict[str, Any]:
    files, seen = [], set()
    with tarfile.open(path, mode="r:") as archive:
        for member in archive:
            name = member.name.removeprefix("./").rstrip("/")
            if not name:
                continue
            require(safe_rootfs_member(name) and name not in seen,
                    "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "rootfs path collision/traversal")
            seen.add(name)
            require(not member.isdev() and not member.isfifo(),
                    "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "rootfs special file")
            require(member.mtime == 0 and not member.pax_headers and
                    not (member.mode & 0o6000),
                    "BLOCKED_G10_NONDETERMINISTIC_BUILD", "rootfs metadata")
            entry = {"path": name, "mode": member.mode, "uid": member.uid,
                     "gid": member.gid, "type": member.type.decode("ascii"),
                     "bytes": member.size, "link": member.linkname}
            if member.isfile():
                stream = archive.extractfile(member)
                entry["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            if member.issym() or member.islnk():
                resolved = os.path.normpath("/" + str(PurePosixPath(name).parent) + "/" +
                                            member.linkname).replace("\\", "/")
                require(not member.linkname.startswith("../" * 16) and resolved.startswith("/"),
                        "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "rootfs link")
            files.append(entry)
    require(files == sorted(files, key=lambda x: x["path"]),
            "BLOCKED_G10_NONDETERMINISTIC_BUILD", "rootfs order")
    return {"files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    source = sub.add_parser("source")
    source.add_argument("--repository", type=Path, required=True)
    package = sub.add_parser("zip")
    package.add_argument("path", type=Path)
    package.add_argument("--sha256")
    package.add_argument("--bytes", type=int)
    rootfs = sub.add_parser("rootfs")
    rootfs.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "source":
            result = source_identity(args.repository)
        elif args.command == "zip":
            result = verify_zip(args.path, expected_sha256=args.sha256, expected_bytes=args.bytes)
        else:
            result = rootfs_inventory(args.path)
        print(canonical(result).decode("utf-8"), end="")
        return 0
    except (GateError, ValueError, OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        code = getattr(exc, "code", "BLOCKED_G10_PACKAGE_MEMBER_DRIFT")
        print(json.dumps({"result": code, "detail": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
