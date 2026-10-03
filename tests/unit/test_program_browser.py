"""File browser boundaries without a Kivy window or controller connection."""

from types import SimpleNamespace

import pytest

from carveracontroller.desktop_program_picker import (
    ProgramBrowser,
    ProgramEntry,
    filter_entries,
    list_program_directory,
    read_program_excerpt,
    remote_entries,
)


def test_listing_keeps_folders_and_programs_in_stable_order(tmp_path):
    (tmp_path / "z folder").mkdir()
    (tmp_path / "Alpha").mkdir()
    for name in ("Z.NC", "b.cnc", "a.gcode", "x.tap", "c.ngc", "image.png", ".hidden.nc"):
        (tmp_path / name).write_text("G0 X0\n")
    entries = list_program_directory(tmp_path)
    assert [item.name for item in entries] == ["Alpha", "z folder", "a.gcode", "b.cnc", "c.ngc", "x.tap", "Z.NC"]
    assert entries[2].size == 6
    assert entries[2].path == str(tmp_path / "a.gcode")
    assert [item.name for item in list_program_directory(tmp_path, "  Z ")] == ["z folder", "Z.NC"]


def test_invalid_directory_does_not_silently_look_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        list_program_directory(tmp_path / "missing")


def test_remote_records_use_same_filter_without_local_stat():
    entries = remote_entries(
        [
            {"name": "nest", "path": "/sd/gcodes/nest", "is_dir": True},
            {"name": "part.nc", "path": "/sd/gcodes/part.nc", "is_dir": False, "size": 200},
            {"name": "config.txt", "path": "/sd/config.txt", "is_dir": False},
        ]
    )
    assert [entry.name for entry in entries] == ["nest", "part.nc"]
    assert entries[1].size == 200
    assert filter_entries(entries, "PART") == [entries[1]]


def test_excerpt_is_bounded_and_tolerates_unknown_encoding(tmp_path):
    path = tmp_path / "test.nc"
    path.write_bytes(b"G1 X0\xff\n" * 100)
    assert read_program_excerpt(path, byte_limit=20, line_limit=2) == "G1 X0�\nG1 X0�\n…"


def browser_fixture(tmp_path):
    calls = []
    local = SimpleNamespace(curr_dir=str(tmp_path), curr_selected_file="")
    remote = SimpleNamespace(curr_dir="/sd/gcodes", curr_selected_file="", curr_selected_filesize=0)
    root = SimpleNamespace(
        file_popup=SimpleNamespace(local_rv=local, remote_rv=remote),
        controller=SimpleNamespace(loadNUM=0, sendNUM=0),
        view_local_file=lambda: calls.append("preview-local"),
        check_and_download=lambda: calls.append("download"),
        check_and_upload=lambda: calls.append("upload"),
    )
    workspace = SimpleNamespace(machine=root, connected=True, app=SimpleNamespace(state="Idle"))
    browser = ProgramBrowser(workspace)
    browser.status = SimpleNamespace(text="")
    browser.dismiss = lambda: calls.append("dismiss")
    browser.selected = ProgramEntry("part.nc", str(tmp_path / "part.nc"), False, 140)
    return browser, calls


def test_local_preview_never_uploads_or_selects_remote_program(tmp_path):
    browser, calls = browser_fixture(tmp_path)
    browser.preview()
    assert calls == ["preview-local", "dismiss"]
    assert browser.root.file_popup.local_rv.curr_selected_file == str(tmp_path / "part.nc")
    assert browser.root.file_popup.remote_rv.curr_selected_file == ""


def test_remote_preview_reuses_download_path_and_file_size(tmp_path):
    browser, calls = browser_fixture(tmp_path)
    browser.location = "remote"
    browser.selected = ProgramEntry("part.nc", "/sd/gcodes/part.nc", False, 140)
    browser.preview()
    assert calls == ["download", "dismiss"]
    assert browser.root.file_popup.remote_rv.curr_selected_filesize == 140


@pytest.mark.parametrize("condition", ["offline", "transfer"])
def test_remote_preview_rejects_unavailable_existing_session(tmp_path, condition):
    browser, calls = browser_fixture(tmp_path)
    browser.location = "remote"
    if condition == "offline":
        browser.workspace.connected = False
    else:
        browser.root.controller.loadNUM = 1
    browser.preview()
    assert calls == []
    assert "current transfer" in browser.status.text


def test_parent_navigation_cannot_leave_machine_sd_root(tmp_path):
    browser, calls = browser_fixture(tmp_path)
    browser.location = "remote"
    browser.remote_path = "/sd"
    browser.up()
    browser.navigate("/etc")
    assert browser.remote_path == "/sd"
    assert "under /sd" in browser.status.text
    assert calls == []


def test_listing_failure_cancels_pending_upload_instead_of_assuming_empty_folder(tmp_path):
    browser, calls = browser_fixture(tmp_path)
    browser._pending_upload = browser.selected.path
    browser._loading_remote = True
    browser._sync_actions = lambda: None
    browser.directory_failed("Timeout loading dir")
    assert browser._pending_upload is None
    assert not browser._loading_remote
    assert "Timeout" in browser.status.text
    assert calls == []


def test_upload_waits_for_fresh_destination_before_existing_overwrite_guard(tmp_path):
    browser, calls = browser_fixture(tmp_path)
    browser._sync_actions = lambda: None
    browser.root.file_popup.remote_rv.list_dir = lambda path: calls.append(("list", path))
    browser.upload()
    assert calls == [("list", "/sd/gcodes")]
    assert browser._pending_upload == str(tmp_path / "part.nc")
    browser._started -= 1
    browser._poll_remote(0)
    assert calls == [("list", "/sd/gcodes"), "upload", "dismiss"]


def test_upload_cancels_if_machine_leaves_idle_during_listing(tmp_path):
    browser, calls = browser_fixture(tmp_path)
    browser._sync_actions = lambda: None
    browser.root.file_popup.remote_rv.list_dir = lambda path: calls.append(("list", path))
    browser.upload()
    browser.workspace.app.state = "Run"
    browser._started -= 1
    browser._poll_remote(0)
    assert calls == [("list", "/sd/gcodes")]
    assert "cancelled" in browser.status.text
