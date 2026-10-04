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
