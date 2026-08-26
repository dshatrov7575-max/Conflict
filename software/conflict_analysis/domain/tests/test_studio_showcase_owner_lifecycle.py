from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest


APP_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = APP_ROOT / "scripts" / "run_studio_showcase.ps1"


def _powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which(
        "pwsh"
    )


def _ps_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _run_powershell(command: str, *, cwd: Path = APP_ROOT) -> subprocess.CompletedProcess[str]:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is unavailable; Windows launcher lifecycle is skipped")
    return subprocess.run(
        [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _copy_launcher(package_root: Path) -> Path:
    scripts = package_root / "scripts"
    scripts.mkdir(parents=True)
    copied = scripts / LAUNCHER.name
    shutil.copy2(LAUNCHER, copied)
    (package_root / "manage.py").write_text("# launcher diagnostic fixture\n", encoding="utf-8")
    return copied


def _wait_for_http(url: str, *, timeout: float = 20.0) -> tuple[int, bytes]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:  # noqa: S310 - fixed loopback URL
                return response.status, response.read()
        except (OSError, URLError) as error:
            last_error = error
            time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


def _wait_for_port_closed(port: int, *, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.1)
    return False


def _kill_exact_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _domain_write_sentinel() -> dict[str, tuple[int, int]]:
    domain_root = APP_ROOT / "domain"
    return {
        str(path.relative_to(domain_root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in domain_root.rglob("*")
        if path.is_file()
    }


def _database_file_sentinel() -> set[str]:
    suffixes = {".db", ".sqlite", ".sqlite3"}
    return {
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows foreground lifecycle contract")
def test_windows_launcher_serves_root_and_health_then_stops_without_orphan():
    powershell = _powershell()
    if powershell is None:
        pytest.skip("PowerShell is unavailable; Windows launcher lifecycle is skipped")

    port = _free_loopback_port()
    before_domain = _domain_write_sentinel()
    before_database_files = _database_file_sentinel()
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "-ListenAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        ],
        cwd=APP_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )
    output = ""
    graceful_stop = False
    try:
        health_status, health_body = _wait_for_http(
            f"http://127.0.0.1:{port}/health/"
        )
        root_status, root_body = _wait_for_http(f"http://127.0.0.1:{port}/")

        assert health_status == 200
        assert json.loads(health_body) == {
            "status": "ok",
            "application": "ConflictAnalysis Studio — Прототип",
            "persistence": "session-only",
        }
        assert root_status == 200
        assert b"ConflictAnalysis Studio" in root_body
        assert process.poll() is None

        process.send_signal(signal.CTRL_BREAK_EVENT)
        process.wait(timeout=15)
        graceful_stop = True
        assert _wait_for_port_closed(port), "runserver listener survived Ctrl+C"
    finally:
        _kill_exact_process_tree(process)
        if process.stdout is not None:
            output = process.stdout.read()

    assert graceful_stop, output
    assert _wait_for_port_closed(port), output
    assert _domain_write_sentinel() == before_domain
    assert _database_file_sentinel() == before_database_files
    assert "DJANGO_SECRET_KEY" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher diagnostic contract")
def test_launcher_missing_python_error_is_actionable_and_pre_server():
    result = _run_powershell(
        f". {_ps_literal(LAUNCHER)}; "
        "Throw-StudioShowcaseMissingPython "
        "-ExpectedPath 'C:\\owner-test\\app\\.venv\\Scripts\\python.exe'"
    )
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert "Python 3.12" in combined
    assert "py -3.12" in combined
    assert "START_HERE_RU.txt" in combined
    assert "Open:" not in combined


def test_launcher_wrong_python_version_error_is_actionable():
    result = _run_powershell(
        f". {_ps_literal(LAUNCHER)}; "
        "Assert-StudioShowcasePythonVersion -Version '3.10' "
        "-PythonSource 'test interpreter'"
    )
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert "Python 3.12" in combined
    assert "3.10" in combined
    assert "py -3.12 -m venv .venv" in combined


def test_launcher_wrong_django_version_error_is_actionable_and_pre_server():
    result = _run_powershell(
        f". {_ps_literal(LAUNCHER)}; "
        "Assert-StudioShowcaseDjangoVersion -Version '5.2.16' "
        "-PythonSource 'test interpreter'"
    )
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert "Django 5.2.17" in combined
    assert "5.2.16" in combined
    assert "pip install -r requirements-owner-test.txt" in combined
    assert "Open:" not in combined


@pytest.mark.skipif(
    os.name != "nt" or sys.version_info[:2] != (3, 12),
    reason="Windows OWNER-TEST targets Python 3.12",
)
def test_launcher_missing_django_error_is_actionable_and_pre_server(tmp_path: Path):
    package_root = tmp_path / "owner-test"
    copied_launcher = _copy_launcher(package_root)
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(package_root / ".venv")],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    port = _free_loopback_port()
    result = _run_powershell(
        f"& {_ps_literal(copied_launcher)} -ListenAddress '127.0.0.1' -Port {port}",
        cwd=package_root,
    )
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert "Django" in combined
    assert "pip install -r requirements-owner-test.txt" in combined
    assert "Open:" not in combined
    assert _wait_for_port_closed(port)


def test_launcher_and_showcase_composition_have_no_persistence_commands():
    launcher_source = LAUNCHER.read_text(encoding="utf-8-sig").lower()
    settings_source = (
        APP_ROOT / "conflict_analysis" / "studio_showcase_settings.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("makemigrations", " migrate", ".objects", "django.db"):
        assert forbidden not in launcher_source
    assert '"ENGINE": "django.db.backends.dummy"' in settings_source
    assert '"domain"' not in settings_source
