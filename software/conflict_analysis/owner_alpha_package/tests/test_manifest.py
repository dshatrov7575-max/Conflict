"""Four frozen portable nodes. Artifact checks require a real final build."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/"scripts"))
import build_owner_alpha_package as build
import verify_owner_alpha_package as verify

def artifacts():
    root=Path(os.environ["G10_ARTIFACT_DIR"])
    path=root/build.ZIP_NAME
    return root,path,verify.verify_zip(path)["manifest"]

def test_manifest_schema_exact_chain_refs_versions_hashes_artifacts_and_nonclaims():
    root,path,manifest=artifacts()
    verify.verify_manifest(manifest)
    assert len(manifest["test_registry"]["portable"])==10
    for family,key,value in (
        ("source","base_head","0"*40),("source","base_tree","0"*40),
        ("migration","blob","0"*40),("nonclaims","final_windows_acceptance",True),
        ("runtime","offline_install",False),("runtime","python","3.12.0")):
        broken=copy.deepcopy(manifest); broken[family][key]=value
        with pytest.raises(verify.GateError): verify.verify_manifest(broken)
    broken=copy.deepcopy(manifest)
    broken["payload"][verify.MANIFEST_NAME]={"bytes":1,"sha256":"0"*64}
    with pytest.raises(verify.GateError): verify.verify_manifest(broken)
    for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'\xff'):
        with pytest.raises(verify.GateError): verify.strict_json(raw)

def test_archive_is_deterministic_case_safe_traversal_free_and_cmd_wrappers_are_exact(tmp_path):
    colon_paths = (
        "var/lib/dpkg/info/gcc-14-base:amd64.list",
        "var/lib/ucf/cache/:etc:postgresql-common:createcluster.conf",
    )
    for name in colon_paths:
        assert verify.safe_rootfs_member(name)
        assert not verify.safe_member(name)
    assert not verify.safe_member("a:stream")
    for invalid in ("../outside", "a/../outside", "/absolute", "windows\\module",
                    "a./file", "a /file", "a.", "a ", "a//file", "./file", "",
                    "cafe\u0301"):
        assert not verify.safe_rootfs_member(invalid)
    for code in range(32):
        assert not verify.safe_rootfs_member("a" + chr(code) + "b")
    rootfs = tmp_path/"colon-rootfs.tar"
    payload = b"Linux package metadata\n"
    with tarfile.open(rootfs, "w", format=tarfile.GNU_FORMAT) as out:
        for name in colon_paths:
            member = tarfile.TarInfo(name)
            member.mode, member.size = 0o644, len(payload)
            out.addfile(member, io.BytesIO(payload))
    inventory = verify.rootfs_inventory(rootfs)
    assert [entry["path"] for entry in inventory["files"]] == list(colon_paths)
    assert all(entry["sha256"] == hashlib.sha256(payload).hexdigest()
               for entry in inventory["files"])
    normalized = build.normalize_rootfs(rootfs, tmp_path/"normalized-rootfs.tar")
    assert [entry for entry in normalized["files"] if entry["path"] in colon_paths] == inventory["files"]
    duplicate = tmp_path/"duplicate-rootfs.tar"
    with tarfile.open(duplicate, "w", format=tarfile.GNU_FORMAT) as out:
        for name in (colon_paths[0], "./" + colon_paths[0]):
            member = tarfile.TarInfo(name)
            out.addfile(member, io.BytesIO(b""))
    with pytest.raises(verify.GateError, match="rootfs path collision/traversal"):
        verify.rootfs_inventory(duplicate)
    with pytest.raises(verify.GateError, match="export path"):
        build.normalize_rootfs(duplicate, tmp_path/"duplicate-normalized-rootfs.tar")
    root,path,manifest=artifacts()
    assert verify.sha256_file(path)==verify.sha256_file(root/("repeat-"+build.ZIP_NAME))
    with zipfile.ZipFile(path) as archive:
        for name,target in verify.WRAPPERS.items():
            assert archive.read(name)==build.cmd_wrapper(*target)
        assert archive.read("SHA256SUMS")==verify.expected_sums(manifest,archive.read(verify.MANIFEST_NAME))
    # Exercise the archive writer and parser with real duplicate/case/traversal
    # ZIP structures. No malicious archive is extracted.
    for invalid in ("../outside","/absolute","windows\\module.psm1","a:stream","a./file"):
        assert not verify.safe_member(invalid)
    for names in (("A","a"),("file","file"),("../escape",)):
        target=tmp_path/(str(len(list(tmp_path.iterdir())))+".zip")
        with zipfile.ZipFile(target,"w") as out:
            for name in names: out.writestr(name,b"x")
        with pytest.raises(verify.GateError): verify.verify_zip(target)
    first,second=tmp_path/"first.zip",tmp_path/"second.zip"
    build.write_zip(first,{"a":b"alpha","b":b"beta"})
    build.write_zip(second,{"b":b"beta","a":b"alpha"})
    assert first.read_bytes()==second.read_bytes()

def test_build_binds_exact_accepted_chain_g10_tree_wheel_sbom_notices_and_normalized_rootfs():
    root,path,manifest=artifacts()
    repo=APP.parents[1]
    assert verify.source_identity(repo)==manifest["source"]
    assert verify.identity(root/manifest["wheel"]["filename"])==manifest["wheel"]
    assert build.validate_closure()
    rootfs=root/build.ROOTFS_NAME
    inventory=verify.rootfs_inventory(rootfs)
    with zipfile.ZipFile(path) as archive:
        report=verify.strict_json(archive.read("evidence/package-build-evidence.json"))
        assert report["rootfs"]==verify.identity(rootfs)
        assert report["rootfs_inventory_sha256"]==inventory["sha256"]
        assert report["wheel"]==manifest["wheel"]
        assert report["source"]==manifest["source"]
        assert report["final_windows_acceptance"] is False
        assert len(archive.read("THIRD_PARTY_NOTICES.txt"))>10000
        sbom=verify.strict_json(archive.read("SBOM.cdx.json"))
        assert sbom["metadata"]["component"]["hashes"][0]["content"]==manifest["wheel"]["sha256"]
        assert len(sbom["components"])==len(build.PINS["wheels"])+len(build.PINS["debs"])
    with pytest.raises(verify.GateError):
        verify.verify_zip(path,expected_sha256="0"*64,expected_bytes=path.stat().st_size)

def test_package_scripts_verify_integrity_before_install_and_never_bypass_execution_policy():
    root,path,manifest=artifacts()
    with zipfile.ZipFile(path) as archive:
        text="\n".join(archive.read(name).decode("utf-8") for name in verify.PAYLOAD_NAMES
                       if name.endswith((".ps1",".psm1",".cmd")))
        forbidden=("Set-ExecutionPolicy","-ExecutionPolicy Bypass","Unblock-File",
                   "Zone.Identifier -Value","Import-Certificate","New-NetFirewallRule",
                   "Start-Process -Verb RunAs","wsl --install","wsl --update")
        for command in forbidden: assert command.casefold() not in text.casefold()
        for name in verify.WRAPPERS:
            wrapper=archive.read(name).decode()
            assert wrapper.index("Get-ExecutionPolicy")<wrapper.index("& (Join-Path")
            for token in ("Zone.Identifier","Get-AuthenticodeSignature","TrustedPublisher",
                          "AllSigned","RemoteSigned","-NoProfile"):
                assert token in wrapper
            assert "Bypass" not in wrapper
        install=archive.read("windows/Install-OwnerAlpha.ps1").decode()
        assert install.index("Get-OwnerContext")<install.index("New-OwnerInstall")

