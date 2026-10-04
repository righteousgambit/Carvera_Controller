"""Artifact selection, async navigation and overwrite semantics."""

from pathlib import Path
from unittest.mock import Mock

from carveracontroller.desktop_file_picker import ArtifactBrowser, artifact_entries
from tests.integration.conftest import pump_frames


def test_picker_filters_suffixes_and_keeps_folders(tmp_path):
    (tmp_path / "subfolder").mkdir()
    (tmp_path / "machine.json.gz").write_text("model")
    (tmp_path / "profile.JSON").write_text("{}")
    (tmp_path / ".hidden.json").write_text("{}")
    (tmp_path / "unrelated.cnc").write_text("M2")
    entries = artifact_entries(tmp_path, (".json", ".json.gz"))
    assert [e.name for e in entries] == ["subfolder", "machine.json.gz", "profile.JSON"]
    assert [e.name for e in artifact_entries(tmp_path, (".json",), "PROFILE")] == ["profile.JSON"]


def test_file_picker_stale_navigation_and_selection(kivy_app, tmp_path):
    workspace = kivy_app.root.desktop_workspace
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "first.cvmap").write_text("{}")
    (second / "second.cvmap").write_text("{}")
    chosen = Mock()
    browser = ArtifactBrowser(workspace, chosen, (".cvmap",))
    browser.navigate(first)
    browser.navigate(second)
    for _ in range(20):
        pump_frames(2)
        if browser.entries and browser.entries[0].name == "second.cvmap":
            break
    assert [e.name for e in browser.entries] == ["second.cvmap"]
    browser.select(browser.entries[0])
    browser.choose()
    chosen.assert_called_once_with(str(second / "second.cvmap"))
    assert browser.closed


def test_save_preserves_existing_and_rejects_path_escape(kivy_app, tmp_path):
    target = tmp_path / "existing.cvface"
    target.write_text("original")
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvface",), save=True)
    browser.path = tmp_path
    for name in ("existing.cvface", "../escape.cvface", "/tmp/escape.cvface", "wrong.json"):
        browser.filename.text = name
        browser.choose()
        chosen.assert_not_called()
    assert target.read_text() == "original"
    browser.filename.text = "new.cvface"
    browser.choose()
    chosen.assert_called_once_with(str(tmp_path / "new.cvface"))


def test_artifact_callback_failure_keeps_dialog_open(kivy_app, tmp_path):
    file = tmp_path / "model.json.gz"
    file.write_text("not a model")
    browser = ArtifactBrowser(
        kivy_app.root.desktop_workspace, Mock(side_effect=ValueError("Unsupported model")), (".json.gz",)
    )
    browser.path = tmp_path
    browser.filename.text = file.name
    try:
        browser.choose()
        assert not browser.closed
        assert browser.note.text == "Unsupported model"
    finally:
        # This test deliberately keeps the modal open after a rejected import;
        # it must not intercept pointer events in subsequent shared-app tests.
        browser.dismiss()


def test_jobs_shortcut_initializes_owned_folder_without_selecting_file(kivy_app, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvface",))
    browser.open_jobs()
    pump_frames(4)
    assert browser.path == tmp_path / ".carvera" / "jobs"
    assert browser.path.is_dir()
    chosen.assert_not_called()
    browser.dismiss()
