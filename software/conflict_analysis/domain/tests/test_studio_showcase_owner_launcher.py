from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest


APP_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = APP_ROOT / "scripts" / "run_studio_showcase.ps1"
SETTINGS_MODULE = "conflict_analysis.studio_showcase_settings"


def _powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which(
        "pwsh"
    )


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is unavailable; Windows launcher integration is skipped")
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
        cwd=APP_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def _ps_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _settings_subprocess(*, secret: str | None, hosts: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DJANGO_SETTINGS_MODULE"] = SETTINGS_MODULE
    environment["DJANGO_ALLOWED_HOSTS"] = hosts
    if secret is None:
        environment.pop("DJANGO_SECRET_KEY", None)
    else:
        environment["DJANGO_SECRET_KEY"] = secret
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from django.conf import settings; "
                "print(json.dumps({'debug': settings.DEBUG, "
                "'hosts': settings.ALLOWED_HOSTS, "
                "'apps': settings.INSTALLED_APPS, "
                "'database': settings.DATABASES['default']['ENGINE']}))"
            ),
        ],
        cwd=APP_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def test_launcher_rejects_unsafe_bind_before_python_or_django_startup():
    result = _run_powershell(
        f"& {_ps_literal(LAUNCHER)} -ListenAddress '0.0.0.0' -Port 8179"
    )

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "Unsafe listen address '0.0.0.0'" in combined
    assert "Interpreter:" not in combined
    assert "Django 5." not in combined


def test_launcher_helpers_accept_only_supported_loopbacks_and_generate_fresh_secrets():
    command = (
        f". {_ps_literal(LAUNCHER)}; "
        "$accepted = @('127.0.0.1', 'localhost'); "
        "if ([System.Net.Sockets.Socket]::OSSupportsIPv6) { "
        "$accepted += @('::1', '[::1]') }; "
        "$resolved = @($accepted | ForEach-Object { "
        "(Resolve-StudioShowcaseLoopbackEndpoint -Address $_).BindAddress }); "
        "$first = New-StudioShowcaseSecret; $second = New-StudioShowcaseSecret; "
        "$rejected = $false; try { "
        "Resolve-StudioShowcaseLoopbackEndpoint -Address '192.168.1.10' | Out-Null "
        "} catch { $rejected = $true }; "
        "[PSCustomObject]@{ resolved = $resolved; rejected = $rejected; "
        "secretsDiffer = ($first -cne $second); firstLength = $first.Length; "
        "secondLength = $second.Length } | ConvertTo-Json -Compress"
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr
    contract = json.loads(result.stdout.strip().splitlines()[-1])
    assert contract["resolved"][:2] == ["127.0.0.1", "127.0.0.1"]
    assert contract["rejected"] is True
    assert contract["secretsDiffer"] is True
    assert contract["firstLength"] >= 64
    assert contract["secondLength"] >= 64


def test_launcher_reports_port_conflict_before_python_startup():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]
        result = _run_powershell(
            f"& {_ps_literal(LAUNCHER)} -ListenAddress '127.0.0.1' -Port {port}"
        )

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert f"Port {port}" in combined
    assert "unavailable" in combined
    assert "Interpreter:" not in combined


def test_showcase_settings_are_debug_off_loopback_only_and_foundation_free():
    result = _settings_subprocess(
        secret="owner-test-ephemeral-secret-00000000000000000000",
        hosts="127.0.0.1,localhost,[::1]",
    )

    assert result.returncode == 0, result.stderr
    contract = json.loads(result.stdout.strip())
    assert contract == {
        "debug": False,
        "hosts": ["127.0.0.1", "[::1]", "localhost"],
        "apps": [
            "django.contrib.staticfiles",
            "shared_ui.apps.SharedUiConfig",
            "studio_showcase.apps.StudioShowcaseConfig",
        ],
        "database": "django.db.backends.dummy",
    }


@pytest.mark.parametrize("hosts", ["0.0.0.0", "example.test", "127.0.0.1,10.0.0.2"])
def test_showcase_settings_reject_non_loopback_allowed_hosts(hosts: str):
    result = _settings_subprocess(
        secret="owner-test-ephemeral-secret-00000000000000000000",
        hosts=hosts,
    )

    assert result.returncode != 0
    assert "accepts loopback hosts only" in result.stderr


def test_showcase_settings_refuse_missing_or_short_secret():
    for secret in (None, "short"):
        result = _settings_subprocess(secret=secret, hosts="127.0.0.1")
        assert result.returncode != 0
        assert "cryptographically generated per-run" in result.stderr


def test_launcher_source_contains_no_committed_secret_or_secret_output():
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "showcase-session-only-not-for-production" not in source
    assert "RandomNumberGenerator]::Create()" in source
    assert "DJANGO_DEBUG = \"false\"" in source
    assert "--insecure" in source
    assert "Write-Host $PerRunSecret" not in source
    assert "Write-Output $PerRunSecret" not in source
    assert "Write-Verbose $PerRunSecret" not in source

    validation_offset = source.index(
        "$Endpoint = Resolve-StudioShowcaseLoopbackEndpoint -Address $ListenAddress"
    )
    python_discovery_offset = source.index('$ProjectRoot =')
    assert validation_offset < python_discovery_offset
