from types import SimpleNamespace

import pytest

from scripts import build_adaptive_macos as build


def test_output_and_temporary_storage_checked_before_build(tmp_path, monkeypatch):
    output = tmp_path / "new" / "build"
    temp = tmp_path / "temporary"
    temp.mkdir()
    monkeypatch.setattr(build.tempfile, "gettempdir", lambda: str(temp))
    seen = []

    def usage(root):
        seen.append(root)
        return SimpleNamespace(free=2 * 1024**3)

    monkeypatch.setattr(build.shutil, "disk_usage", usage)
    build.storage_preflight(output)
    assert seen == [tmp_path, temp] and not output.exists()
    monkeypatch.setattr(
        build.shutil, "disk_usage", lambda root: SimpleNamespace(free=100 if root == temp else 2 * 1024**3)
    )
    with pytest.raises(ValueError, match="temporary"):
        build.storage_preflight(output)
    assert not output.exists()


def test_low_space_aborts_cli_without_staging_or_packaging(tmp_path, monkeypatch, capsys):
    output = tmp_path / "build"
    monkeypatch.setattr(build.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(build.sys, "argv", ["build", "--output", str(output)])
    monkeypatch.setattr(build.shutil, "disk_usage", lambda _: SimpleNamespace(free=100))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("packager invoked"))
    with pytest.raises(SystemExit) as result:
        build.main()
    assert result.value.code == 2 and not output.exists()
    assert "Insufficient free storage" in capsys.readouterr().err


def test_invalid_storage_target_is_explicit(tmp_path):
    file = tmp_path / "file"
    file.write_text("preserve")
    with pytest.raises(ValueError, match="not a directory"):
        build.storage_preflight(file)
    with pytest.raises(ValueError, match="positive"):
        build.storage_preflight(tmp_path, 0)
    assert file.read_text() == "preserve"


def test_packaging_hooks_isolate_operator_configuration_and_keep_dependency_path(tmp_path, monkeypatch):
    operator = tmp_path / "operator"
    operator.mkdir()
    config = operator / "config.ini"
    config.write_text("operator preferences")
    monkeypatch.setenv("KIVY_HOME", str(operator))
    monkeypatch.setenv("KIVY_NO_FILELOG", "0")
    monkeypatch.setenv("PYTHONPATH", "/isolated/build/dependencies")
    output = tmp_path / "artifact"
    environment = build.packaging_environment(output)
    assert environment["KIVY_HOME"] == str(output / "packaging-kivy")
    assert environment["KIVY_NO_FILELOG"] == "1"
    assert environment["KIVY_LOG_MODE"] == "MIXED"
    assert environment["PYTHONPATH"] == "/isolated/build/dependencies"
    assert build.os.environ["KIVY_HOME"] == str(operator)
    assert build.os.environ["KIVY_NO_FILELOG"] == "0"
    assert config.read_text() == "operator preferences"
    assert not output.exists()


@pytest.mark.parametrize("missing", ["PyInstaller", "kivy", "PIL"])
def test_missing_packaging_dependency_aborts_before_staging(tmp_path, monkeypatch, capsys, missing):
    output = tmp_path / "build"
    monkeypatch.setattr(build.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(build.sys, "argv", ["build", "--output", str(output)])
    monkeypatch.setattr(build.shutil, "disk_usage", lambda _: SimpleNamespace(free=2 * 1024**3))
    monkeypatch.setattr(build.importlib.util, "find_spec", lambda name: None if name == missing else object())
    monkeypatch.setattr(build.shutil, "copytree", lambda *a, **k: pytest.fail("source staged"))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("packager invoked"))
    with pytest.raises(SystemExit) as result:
        build.main()
    message = capsys.readouterr().err
    assert result.value.code == 2 and not output.exists()
    assert missing in message and build.sys.executable in message


@pytest.mark.parametrize("missing", ["msgfmt", "codesign"])
def test_missing_packaging_tool_aborts_before_output_or_source_staging(tmp_path, monkeypatch, capsys, missing):
    output = tmp_path / "build"
    monkeypatch.setattr(build.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(build.sys, "argv", ["build", "--output", str(output)])
    monkeypatch.setattr(build.shutil, "disk_usage", lambda _: SimpleNamespace(free=2 * 1024**3))
    monkeypatch.setattr(build.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(build.shutil, "which", lambda name: None if name == missing else "/prepared/" + name)
    monkeypatch.setattr(build.shutil, "copytree", lambda *a, **k: pytest.fail("source staged"))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("packager invoked"))
    with pytest.raises(SystemExit) as result:
        build.main()
    assert result.value.code == 2 and not output.exists()
    assert missing in capsys.readouterr().err


def test_scratch_mode_requires_fresh_separate_locations_and_preserves_evidence(tmp_path):
    output, scratch = tmp_path / "archive", tmp_path / "scratch"
    assert build.build_locations(output, scratch) == (output, scratch)
    assert build.build_locations(output, None) == (output, output)
    assert not output.exists() and not scratch.exists()
    for candidate in (output, output / "nested", tmp_path):
        with pytest.raises(ValueError, match="non-nested"):
            build.build_locations(output, candidate)
    output.mkdir()
    (output / "receipt").write_text("preserve")
    with pytest.raises(ValueError, match="fresh"):
        build.build_locations(output, scratch)
    assert (output / "receipt").read_text() == "preserve"


def candidate(tmp_path):
    root = tmp_path / "scratch"
    (root / "source").mkdir(parents=True)
    (root / "source/code.py").write_text("source bytes")
    resource = root / "dist/carveracontroller.app/Contents/Resources"
    resource.mkdir(parents=True)
    (resource / "binary").write_bytes(b"signed candidate bytes")
    (resource / "alias").symlink_to("binary")
    (root / "source-manifest.json").write_text('{"source": "candidate"}')
    (root / "source").chmod(0o750)
    return root


def test_archive_copies_exact_signed_deliverables_and_retains_scratch(tmp_path, monkeypatch):
    import json

    scratch = candidate(tmp_path)
    output = tmp_path / "archive"
    calls = []
    monkeypatch.setattr(build.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    expected = build.artifact_tree(scratch)
    bundle = build.archive_signed_build(scratch, output, "TEST")
    assert bundle == output / "dist/carveracontroller.app"
    assert build.artifact_tree(output) == expected == build.artifact_tree(scratch)
    assert (bundle / "Contents/Resources/alias").is_symlink()
    assert len(calls) == 2
    assert all(args[:4] == ["codesign", "--verify", "--deep", "--strict"] and kwargs["check"] for args, kwargs in calls)
    receipt = json.loads((output / "build-archive-receipt.json").read_text())
    assert receipt["strict_signature_verified"] and not receipt["installed"]
    assert receipt["source_to_package_verification"] == "OPEN independent gate"
    assert receipt["scratch_retained"] and receipt["identity_mismatches"] == []


def test_corrupt_archive_retains_failed_copy_and_source_without_success_receipt(tmp_path, monkeypatch):
    import json

    scratch = candidate(tmp_path)
    output = tmp_path / "archive"
    monkeypatch.setattr(build.subprocess, "run", lambda *args, **kwargs: None)
    copy = build.shutil.copytree

    def corrupt(source, destination, *args, **kwargs):
        from pathlib import Path

        result = copy(source, destination, *args, **kwargs)
        destination = Path(destination)
        if destination.name == "source":
            (destination / "code.py").write_text("corrupt")
        return result

    monkeypatch.setattr(build.shutil, "copytree", corrupt)
    with pytest.raises(ValueError, match="identity mismatch"):
        build.archive_signed_build(scratch, output, "TEST")
    assert (scratch / "source/code.py").read_text() == "source bytes"
    assert (output / "source/code.py").read_text() == "corrupt"
    assert not (output / "build-archive-receipt.json").exists()
    assert "identity mismatch" in json.loads((output / "build-archive-failure.json").read_text())["error"]


def test_unsigned_candidate_aborts_before_archive_creation(tmp_path, monkeypatch):
    import subprocess

    scratch = candidate(tmp_path)
    output = tmp_path / "archive"

    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(build.subprocess, "run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        build.archive_signed_build(scratch, output, "TEST")
    assert not output.exists() and scratch.exists()


def test_scratch_cli_routes_packaging_and_signing_before_archiving(tmp_path, monkeypatch):
    import plistlib
    from pathlib import Path

    repo, scratch, output = tmp_path / "repo", tmp_path / "scratch", tmp_path / "archive"
    (repo / "scripts").mkdir(parents=True)
    (repo / "carveracontroller/locales").mkdir(parents=True)
    (repo / "assets").mkdir()
    (repo / "carveracontroller/__main__.py").write_text("pass\n")
    (repo / "carveracontroller/machine").mkdir()
    (repo / "carveracontroller/machine/artifact_fs_worker.py").write_text("worker source\n")
    monkeypatch.setattr(build, "__file__", str(repo / "scripts/build_adaptive_macos.py"))
    monkeypatch.setattr(build.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(build, "dependency_preflight", lambda: None)
    monkeypatch.setattr(build.shutil, "disk_usage", lambda _: SimpleNamespace(free=2 * 1024**3))
    monkeypatch.setattr(
        build.sys, "argv", ["build", "--output", str(output), "--scratch-root", str(scratch), "--version", "2.1.0-TEST"]
    )
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if "PyInstaller" in args:
            if "carvera-artifact-worker" in args:
                assert Path(args[args.index("--distpath") + 1]) == scratch / "helper-dist"
                assert kwargs["cwd"] == scratch
                assert "--windowed" in args and "--console" not in args
                assert str(scratch / "source/carveracontroller/machine/artifact_fs_worker.py") in args
                assert Path(args[args.index("--icon") + 1]) == scratch / "source/assets/packaging/icon-src.icns"
                helper = scratch / "helper-dist/carvera-artifact-worker.app/Contents"
                (helper / "MacOS").mkdir(parents=True)
                (helper / "Resources").mkdir()
                (helper / "Info.plist").write_bytes(plistlib.dumps({}))
                (helper / "MacOS/carvera-artifact-worker").write_bytes(b"worker executable")
                (helper / "Resources/runtime.bin").write_bytes(b"runtime")
                (helper / "Resources/runtime-link").symlink_to("runtime.bin")
                return
            assert Path(args[args.index("--distpath") + 1]) == scratch / "dist"
            assert kwargs["cwd"] == scratch / "source"
            assert kwargs["env"]["KIVY_HOME"] == str(scratch / "packaging-kivy")
            assert kwargs["env"]["TMPDIR"] == str(scratch / "temporary")
            assert (scratch / "temporary").is_dir()
            assert not output.exists()
            bundle = scratch / "dist/carveracontroller.app"
            (bundle / "Contents").mkdir(parents=True)
            (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({}))
        elif "--sign" in args:
            helper = scratch / "dist/carveracontroller.app/Contents/Helpers/carvera-artifact-worker.app"
            assert (helper / "Contents/Resources/worker-source.py").read_bytes() == b"worker source\n"
            assert (helper / "Contents/Resources/runtime-link").is_symlink()
            assert args[-1] in (str(scratch / "dist/carveracontroller.app"), str(helper))
            assert "--deep" not in args
            assert not output.exists()
            assert kwargs["env"]["TMPDIR"] == str(scratch / "temporary")

    monkeypatch.setattr(build.subprocess, "run", run)
    build.main()
    assert (output / "build-archive-receipt.json").exists()
    assert (scratch / "source/carveracontroller/__version__.py").read_text() == "__version__ = '2.1.0-TEST'\n"
    info = plistlib.loads((output / "dist/carveracontroller.app/Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "2.1.0"
    assert calls[-1][0][-1] == str(output / "dist/carveracontroller.app")
    assert "--verify" in calls[-1][0] and "--sign" not in calls[-1][0]


@pytest.mark.skipif(build.platform.system() != "Darwin", reason="Actual macOS code-signature validation")
def test_archive_preserves_actual_adhoc_macos_signature(tmp_path):
    import json
    import plistlib

    scratch = candidate(tmp_path)
    app = scratch / "dist/carveracontroller.app"
    executable = app / "Contents/MacOS/demo"
    executable.parent.mkdir()
    build.shutil.copyfile("/usr/bin/true", executable)
    executable.chmod(0o755)
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "dev.carvera.archive-test",
                "CFBundleExecutable": "demo",
                "CFBundlePackageType": "APPL",
            }
        )
    )
    build.subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    output = tmp_path / "archive"
    build.archive_signed_build(scratch, output, "TEST")
    assert json.loads((output / "build-archive-receipt.json").read_text())["strict_signature_verified"]
    assert build.artifact_tree(scratch) == build.artifact_tree(output)


@pytest.mark.skipif(build.platform.system() != "Darwin", reason="Actual macOS nested signature validation")
def test_metadata_resign_preserves_nested_code_and_refuses_corruption(tmp_path):
    import hashlib
    import os
    import plistlib
    import subprocess

    app = tmp_path / "metadata.app"
    executable, helper = app / "Contents/MacOS/demo", app / "Contents/Helpers/helper"
    for path in (executable, helper):
        path.parent.mkdir(parents=True)
        build.shutil.copyfile("/usr/bin/true", path)
        path.chmod(0o755)
    plist = app / "Contents/Info.plist"
    info = {
        "CFBundleIdentifier": "dev.carvera.metadata-test",
        "CFBundleExecutable": "demo",
        "CFBundlePackageType": "APPL",
    }
    plist.write_bytes(plistlib.dumps(info))
    subprocess.run(["codesign", "--force", "--sign", "-", str(helper)], check=True)
    before = hashlib.sha256(helper.read_bytes()).hexdigest()
    build.sign_bundle_metadata(app, os.environ.copy())
    info["CFBundleShortVersionString"] = "2.1.0"
    plist.write_bytes(plistlib.dumps(info))
    assert subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)]).returncode != 0
    build.sign_bundle_metadata(app, os.environ.copy())
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == before
    content = bytearray(helper.read_bytes())
    content[4096] ^= 1
    helper.write_bytes(content)
    with pytest.raises(subprocess.CalledProcessError):
        build.sign_bundle_metadata(app, os.environ.copy())
    assert helper.read_bytes() == content
