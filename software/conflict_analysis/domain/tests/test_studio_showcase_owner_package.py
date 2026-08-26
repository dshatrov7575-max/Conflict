from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import warnings
import zipfile

import pytest

from studio_showcase.owner_test import build_owner_test_package as package_builder
from studio_showcase.owner_test.build_owner_test_package import (
    ARCHIVE_ROOT,
    FORMAT,
    SCREENSHOT_PATHS,
    create_package_files,
    write_deterministic_zip,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
HEAD = "1" * 40
TREE = "2" * 40
ZIP_NAME = f"ConflictAnalysis-Studio-OWNER-TEST-{HEAD[:12]}.zip"


def _read_worktree_source(relative_path: str) -> bytes:
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"required package source is missing: {relative_path}"
    return path.read_bytes()


def _package_files() -> tuple[dict[str, bytes], str]:
    return create_package_files(
        _read_worktree_source,
        head=HEAD,
        tree=TREE,
        zip_name=ZIP_NAME,
    )


def test_owner_package_has_required_launcher_payload_evidence_and_boundaries():
    files, manifest_hash = _package_files()

    required = {
        "START_HERE_RU.txt",
        "KNOWN_LIMITATIONS_RU.md",
        "CLEANUP_RU.md",
        "VERIFY_CONTENT.ps1",
        "RUN_BROWSER_SMOKE.ps1",
        "MANIFEST.json",
        "app/manage.py",
        "app/requirements-owner-test.txt",
        "app/scripts/run_studio_showcase.ps1",
        "app/conflict_analysis/studio_showcase_settings.py",
        "app/studio_showcase/session.py",
        "app/studio_showcase/templates/studio_showcase/index.html",
        "app/studio_showcase/static/studio_showcase/studio.js",
        "app/shared_ui/static/shared_ui/tokens.css",
        "screenshots/README.md",
        "screenshots/SHA256SUMS.txt",
    }
    assert required <= files.keys()
    assert "MANIFEST.sha256" not in files
    assert not any(path.endswith(".zip.sha256") for path in files)
    assert not any(path.endswith(".zip.manifest.sha256") for path in files)
    screenshot_files = sorted(
        path
        for path in files
        if path.startswith("screenshots/")
        and Path(path).suffix.lower() in {".jpg", ".png"}
    )
    assert len(screenshot_files) == 6
    assert len(SCREENSHOT_PATHS) == 6
    screenshot_register = files["screenshots/SHA256SUMS.txt"].decode("ascii")
    assert screenshot_register.endswith("\n")
    assert screenshot_register.splitlines() == [
        f"{hashlib.sha256(files[path]).hexdigest()}  {Path(path).name}"
        for path in screenshot_files
    ]

    start_here = files["START_HERE_RU.txt"].decode()
    assert HEAD in start_here
    assert TREE in start_here
    assert ZIP_NAME in start_here
    assert "@@" not in start_here
    assert "RUN_BROWSER_SMOKE.ps1" in start_here
    assert "-File ..\\RUN_BROWSER_SMOKE.ps1" in start_here
    assert (
        "-ManifestSha256RecordPath "
        f"..\\{ZIP_NAME}.manifest.sha256"
    ) in start_here
    assert "требует доступа к PyPI по сети" in start_here
    for boundary in ("session-only", "не публикует", "не изменяет", "Power", "прогноза"):
        assert boundary in start_here
    limitations = files["KNOWN_LIMITATIONS_RU.md"].decode()
    assert "500" in limitations
    assert "10 000" in limitations
    for boundary in ("Foundation ORM", "Power", "прогноза"):
        assert boundary in limitations

    manifest = json.loads(files["MANIFEST.json"])
    assert manifest["format"] == FORMAT
    assert manifest["head"] == HEAD
    assert manifest["tree"] == TREE
    assert manifest["boundary"] == {
        "research_prototype": True,
        "session_only": True,
        "publication": False,
        "foundation_mutation": False,
        "formula_power_prediction": False,
    }
    assert manifest["package_sha256_record"] == f"{ZIP_NAME}.sha256"
    assert manifest["manifest_sha256_record"] == f"{ZIP_NAME}.manifest.sha256"
    assert manifest["screenshot_sha256_register"] == "screenshots/SHA256SUMS.txt"
    assert manifest["build_environment"]["dependency_install_requires_network"] is True
    assert "PyPI" in manifest["build_environment"]["dependency_source"]
    assert hashlib.sha256(files["MANIFEST.json"]).hexdigest() == manifest_hash

    manifested = {entry["path"]: entry for entry in manifest["files"]}
    assert list(manifested) == sorted(manifested)
    assert set(manifested) == set(files) - {"MANIFEST.json"}
    for path, entry in manifested.items():
        assert set(entry) == {"path", "size_bytes", "sha256"}
        assert entry["size_bytes"] == len(files[path])
        assert entry["sha256"] == hashlib.sha256(files[path]).hexdigest()


def test_owner_package_zip_is_byte_reproducible_and_has_stable_metadata(tmp_path: Path):
    files, _ = _package_files()
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    write_deterministic_zip(first, files)
    write_deterministic_zip(second, dict(reversed(list(files.items()))))

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(name.startswith(f"{ARCHIVE_ROOT}/") for name in names)
        assert not any("MANIFEST.sha256" in name for name in names)
        assert not any(name.endswith(".zip.sha256") for name in names)
        assert not any(name.endswith(".zip.manifest.sha256") for name in names)
        assert all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        extracted_manifest = json.loads(
            archive.read(f"{ARCHIVE_ROOT}/MANIFEST.json")
        )
        assert extracted_manifest["head"] == HEAD
        assert extracted_manifest["tree"] == TREE


def test_builder_emits_exactly_three_adjacent_deterministic_delivery_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def read_fake_revision(repository_root: Path, *arguments: str) -> bytes:
        assert repository_root == REPOSITORY_ROOT
        assert arguments[0] == "show"
        revision_path = arguments[1]
        revision, source_path = revision_path.split(":", 1)
        assert revision == HEAD
        return _read_worktree_source(source_path)

    monkeypatch.setattr(package_builder, "verify_exact_revision", lambda *_args: None)
    monkeypatch.setattr(package_builder, "_git", read_fake_revision)

    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first = package_builder.build_package(
        REPOSITORY_ROOT,
        head=HEAD,
        tree=TREE,
        output_directory=first_directory,
    )
    second = package_builder.build_package(
        REPOSITORY_ROOT,
        head=HEAD,
        tree=TREE,
        output_directory=second_directory,
    )

    expected_names = {
        ZIP_NAME,
        f"{ZIP_NAME}.sha256",
        f"{ZIP_NAME}.manifest.sha256",
    }
    assert {path.name for path in first_directory.iterdir()} == expected_names
    assert {path.name for path in second_directory.iterdir()} == expected_names
    for name in expected_names:
        assert (first_directory / name).read_bytes() == (
            second_directory / name
        ).read_bytes()

    zip_path = Path(first["zip_path"])
    zip_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert first["zip_sha256"] == zip_hash
    assert Path(first["sha256_record"]).read_bytes() == (
        f"{zip_hash}  {ZIP_NAME}\n".encode("ascii")
    )
    with zipfile.ZipFile(zip_path) as archive:
        manifest_bytes = archive.read(f"{ARCHIVE_ROOT}/MANIFEST.json")
        names = archive.namelist()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    assert first["manifest_sha256"] == manifest_hash
    assert Path(first["manifest_sha256_record"]).read_bytes() == (
        f"{manifest_hash}  MANIFEST.json\n".encode("ascii")
    )
    assert not any(name.endswith(".sha256") for name in names)
    assert first["file_count"] == len(names)
    assert second["zip_sha256"] == zip_hash
    assert second["manifest_sha256"] == manifest_hash


@pytest.mark.skipif(shutil.which("powershell") is None, reason="PowerShell unavailable")
def test_packaged_verifier_accepts_exact_files_and_rejects_unmanifested_file(
    tmp_path: Path,
):
    files, manifest_hash = _package_files()
    archive_path = tmp_path / ZIP_NAME
    manifest_record = tmp_path / f"{ZIP_NAME}.manifest.sha256"
    manifest_record.write_bytes(f"{manifest_hash}  MANIFEST.json\n".encode("ascii"))
    write_deterministic_zip(archive_path, files)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(tmp_path / "extracted")
    package_root = tmp_path / "extracted" / ARCHIVE_ROOT
    verifier = package_root / "VERIFY_CONTENT.ps1"

    accepted = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(verifier),
            "-ManifestSha256RecordPath",
            str(manifest_record),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert "OWNER-TEST content verified" in accepted.stdout

    (package_root / "unmanifested.txt").write_text("not allowed", encoding="utf-8")
    rejected = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(verifier),
            "-ManifestSha256RecordPath",
            str(manifest_record),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert rejected.returncode != 0
    assert "Unexpected package file" in rejected.stderr


@pytest.mark.skipif(shutil.which("powershell") is None, reason="PowerShell unavailable")
@pytest.mark.parametrize(
    ("entry_names", "expected_error"),
    (
        ([f"{ARCHIVE_ROOT}/../escape.txt"], "Unsafe or non-normalized ZIP entry"),
        (["/absolute.txt"], "Unsafe or non-normalized ZIP entry"),
        (
            [f"{ARCHIVE_ROOT}/same.txt", f"{ARCHIVE_ROOT}/same.txt"],
            "Duplicate ZIP entry path",
        ),
        (
            [f"{ARCHIVE_ROOT}/Case.txt", f"{ARCHIVE_ROOT}/case.txt"],
            "Case-colliding ZIP entry path",
        ),
    ),
)
def test_clean_room_rejects_unsafe_zip_before_extracting_entries(
    tmp_path: Path,
    entry_names: list[str],
    expected_error: str,
):
    archive_path = tmp_path / "unsafe.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive_path, "w") as archive:
            for index, entry_name in enumerate(entry_names):
                archive.writestr(entry_name, f"payload-{index}".encode())

    zip_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    zip_record = tmp_path / "unsafe.zip.sha256"
    manifest_record = tmp_path / "unsafe.zip.manifest.sha256"
    zip_record.write_bytes(f"{zip_hash}  unsafe.zip\n".encode("ascii"))
    manifest_record.write_bytes(f"{'0' * 64}  MANIFEST.json\n".encode("ascii"))
    clean_room = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/run_clean_room_gate.ps1"
    )
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(clean_room),
            "-ZipPath",
            str(archive_path),
            "-Sha256RecordPath",
            str(zip_record),
            "-ManifestSha256RecordPath",
            str(manifest_record),
            "-Head",
            HEAD,
            "-Tree",
            TREE,
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    combined_output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert expected_error in combined_output


def test_packaging_wrapper_requires_exact_head_tree_and_never_commits_an_archive():
    wrapper = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/build_owner_test_package.ps1"
    ).read_text(encoding="utf-8")
    builder = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/build_owner_test_package.py"
    ).read_text(encoding="utf-8")
    clean_room = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/run_clean_room_gate.ps1"
    ).read_text(encoding="utf-8")
    verifier = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/templates/VERIFY_CONTENT.ps1"
    ).read_text(encoding="utf-8")
    browser_smoke = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/templates/RUN_BROWSER_SMOKE.ps1"
    ).read_text(encoding="utf-8")

    assert wrapper.count("ValidatePattern('^[0-9a-f]{40}$')") == 2
    assert "--head $Head --tree $Tree" in wrapper
    assert '"rev-parse", "HEAD^{tree}"' in builder
    assert '"show", f"{head}:{source_path}"' in builder
    for gate in (
        "Expand-SafeOwnerArchive",
        "ZipArchive",
        "VERIFY_CONTENT.ps1",
        "-m venv",
        "pip install",
        "run_studio_showcase.ps1",
        "health/",
        "RUN_BROWSER_SMOKE.ps1",
        "taskkill.exe",
        "Remove-Item -LiteralPath $Scratch -Recurse -Force",
    ):
        assert gate in clean_room
    assert "Unexpected package file not covered by MANIFEST.json" in verifier
    assert "size_bytes" in verifier
    assert "Case-colliding manifest path" in verifier
    assert "Get-Sha256Hex" in verifier
    assert "Get-Sha256Hex" in clean_room
    assert "Case-colliding ZIP entry path" in clean_room
    assert "ManifestSha256RecordPath" in clean_room
    assert "Expand-Archive" not in clean_room
    assert "Get-FileHash" not in verifier
    assert "Get-FileHash" not in clean_room
    assert "--headless=new" in browser_smoke
    assert 'id="studio-workspace"' in browser_smoke
    assert not list(REPOSITORY_ROOT.rglob("*.zip"))
