"""Exercise setup control flow with inert command adapters; never install packages."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/install_linux_prereqs.sh"


def run_setup(tmp_path, arguments=(), apt_exit=0):
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "calls.txt"
    for name, body in {
        "sudo": 'exec "$@"',
        "apt-get": 'printf "apt-get %s\\n" "$*" >> "$PREREQ_LOG"; exit "$APT_EXIT"',
        "curl": 'printf "curl %s\\n" "$*" >> "$PREREQ_LOG"; exit 22',
    }.items():
        candidate = tools / name
        candidate.write_text("#!/bin/sh\n" + body + "\n")
        candidate.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": str(tools) + os.pathsep + "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PREREQ_LOG": str(log),
        "APT_EXIT": str(apt_exit),
    }
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), *arguments], env=environment, capture_output=True, text=True, timeout=5
    )
    return result, log.read_text().splitlines() if log.exists() else []


def test_quality_prerequisites_skip_unused_packaging_download(tmp_path):
    result, calls = run_setup(tmp_path, ("--skip-appimage",))
    assert result.returncode == 0 and "AppImage tooling skipped" in result.stdout
    assert calls[0] == "apt-get update"
    assert len(calls) == 2 and calls[1].startswith("apt-get install -y ")
    assert "gettext" in calls[1] and "libhidapi-hidraw0" in calls[1]
    assert not (tmp_path / ".local").exists()


def test_prerequisite_failure_stops_before_install_or_download(tmp_path):
    result, calls = run_setup(tmp_path, ("--skip-appimage",), apt_exit=42)
    assert result.returncode == 42 and calls == ["apt-get update"]


def test_release_download_is_bounded_and_http_failure_is_fatal(tmp_path):
    result, calls = run_setup(tmp_path)
    assert result.returncode == 1 and "Failed to download" in result.stdout
    assert len(calls) == 3
    assert calls[-1].startswith("curl --fail --location --connect-timeout 10 --max-time 120 --retry 2 ")
    assert not (tmp_path / ".local").exists()


@pytest.mark.parametrize("arguments", [("--unknown",), ("--skip-appimage", "--skip-appimage")])
def test_unknown_setup_arguments_fail_before_any_system_command(tmp_path, arguments):
    result, calls = run_setup(tmp_path, arguments)
    assert result.returncode == 2 and "Usage:" in result.stderr and not calls


def test_quality_workflow_bounds_dependency_setup_and_keeps_quality_gates():
    workflow = yaml.safe_load((SCRIPT.parents[1] / ".github/workflows/quality.yaml").read_text())
    steps = {step["name"]: step for step in workflow["jobs"]["quality"]["steps"] if "name" in step}
    assert steps["Install Linux prerequisites"]["timeout-minutes"] == 15
    assert steps["Install Linux prerequisites"]["run"].endswith("--skip-appimage")
    assert steps["Install Linux test prerequisites"]["timeout-minutes"] == 10
    assert "pre-commit run --all-files" in steps["Run quality hooks"]["run"]
    assert "pytest tests" in steps["Run tests"]["run"]
