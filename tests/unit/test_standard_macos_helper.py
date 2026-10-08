import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from scripts import build_adaptive_macos


@pytest.fixture
def builder(monkeypatch, tmp_path):
    # Import the real CLI while isolating its unrelated packaging dependencies.
    for name in (
        "PyInstaller",
        "PyInstaller.__main__",
        "pyinstaller_versionfile",
        "toml",
        "ruamel",
        "ruamel.yaml",
        "update_translations",
    ):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules["ruamel.yaml"].YAML = Mock()
    sys.modules["update_translations"].compile_mo = Mock()
    monkeypatch.setitem(sys.modules, "build_adaptive_macos", build_adaptive_macos)
    spec = importlib.util.spec_from_file_location("standard_build_test", Path(__file__).parents[2] / "scripts/build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT_PATH", tmp_path)
    monkeypatch.setattr(module, "BUILD_PATH", tmp_path / "scripts")
    module.BUILD_PATH.mkdir()
    monkeypatch.setattr(module, "PACKAGE_PATH", tmp_path / "carveracontroller")
    for name in (
        "backup_codegen_files",
        "codegen_version_string",
        "compile_mo",
        "rename_release_file",
        "restore_codegen_files",
    ):
        monkeypatch.setattr(module, name, Mock())
    monkeypatch.setattr(module, "build_pyinstaller_args", Mock(return_value=["desktop"]))
    monkeypatch.setattr(module, "run_pyinstaller", Mock())
    monkeypatch.setattr(module, "fix_macos_version_string", Mock())
    monkeypatch.setattr(module, "create_macos_dmg", Mock())
    monkeypatch.setattr(sys, "argv", ["build", "--os", "macos", "--version", "2.1.0-TEST"])
    return module


@pytest.mark.parametrize("failure", (None, "helper", "signature"))
def test_standard_release_includes_verified_helper_before_dmg_and_retains_failed_scratch(builder, monkeypatch, failure):
    stages = []

    def helper(package, working, bundle, environment):
        stages.append("helper")
        assert package == builder.PACKAGE_PATH
        assert working.is_dir() and working.parent == builder.BUILD_PATH
        assert bundle == builder.ROOT_PATH / "dist/carveracontroller.app"
        assert environment["KIVY_HOME"].startswith(str(working)) and environment["TMPDIR"] == str(working)
        (working / "analysis-evidence.txt").write_text("retained")
        if failure == "helper":
            raise ValueError("helper failure")

    def sign(bundle, environment):
        stages.append("signature")
        if failure == "signature":
            raise ValueError("signature failure")

    monkeypatch.setattr(build_adaptive_macos, "build_artifact_worker", helper)
    monkeypatch.setattr(build_adaptive_macos, "sign_bundle_metadata", sign)
    builder.fix_macos_version_string.side_effect = lambda version: stages.append("version")
    builder.create_macos_dmg.side_effect = lambda: stages.append("dmg")
    if failure:
        with pytest.raises(ValueError, match=failure):
            builder.main()
        builder.create_macos_dmg.assert_not_called()
        builder.rename_release_file.assert_not_called()
    else:
        builder.main()
        assert stages == ["helper", "version", "signature", "dmg"]
        builder.run_pyinstaller.assert_called_once_with(build_args=["desktop"])
        builder.restore_codegen_files.assert_called_once()
    folders = list(builder.BUILD_PATH.glob("artifact-worker-*"))
    assert len(folders) == 1 and (folders[0] / "analysis-evidence.txt").read_text() == "retained"
