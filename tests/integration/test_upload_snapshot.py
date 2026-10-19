"""Production upload preparation uses disk snapshots; no live transport is used."""

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller import main
from carveracontroller.machine.program_bytes import preview_digest
from tests.integration.conftest import pump_frames


@pytest.fixture
def upload_case(monkeypatch, tmp_path):
    # The normal main() bootstrap sets these QuickLZ framing constants.
    monkeypatch.setattr(main, "BLOCK_SIZE", 4096, raising=False)
    monkeypatch.setattr(main, "BLOCK_HEADER_SIZE", 4, raising=False)
    path = tmp_path / "part.cnc"
    path.write_bytes(b"G21\r\n")
    workers = []

    def deferred_thread(*, target, **_kwargs):
        return SimpleNamespace(start=lambda: workers.append(target))

    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=deferred_thread, Event=threading.Event))
    app = SimpleNamespace(selected_local_filename=str(path), selected_remote_filename="")
    monkeypatch.setattr(main, "App", SimpleNamespace(get_running_app=lambda: app))
    controller = SimpleNamespace(_connection_generation=7, sendNUM=0, stream=SimpleNamespace(cancel_process=Mock()))
    root = SimpleNamespace(
        uploading=False,
        filetype="",
        program_preview_generation=3,
        _last_loaded_file_key=str(path),
        file_popup=SimpleNamespace(remote_rv=SimpleNamespace(curr_dir="/sd/jobs"), firmware_mode=False),
        gcode_viewer=SimpleNamespace(loaded_program_hash=preview_digest(b"G21\n")),
        controller=controller,
        show_message_popup=Mock(),
        progressStart=Mock(),
        progressFinish=Mock(),
        doUpload=Mock(),
        compress_file=Mock(),
    )
    root.cancelProcessingFile = lambda: main.Makera.cancelProcessingFile(root)
    yield SimpleNamespace(root=root, path=path, workers=workers, app=app)
    pump_frames(3)
    controller.stream.cancel_process.assert_not_called()


def test_snapshot_consumption_survives_original_mutation_and_pins_destination(upload_case):
    item = upload_case

    def consume(callback, **target):
        assert target == {"target_directory": "/sd/jobs", "firmware_mode": False}
        item.path.write_bytes(b"G20\r\n")
        assert Path(item.root.uploading_file).read_bytes() == b"G21\r\n"
        assert Path(item.root.uploading_file) != item.path
        item.root.file_popup.remote_rv.curr_dir = "/sd/elsewhere"
        callback("/sd/jobs/part.cnc", "cached.cnc")

    item.root.doUpload.side_effect = consume
    callback = Mock()
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    assert item.root._upload_preparing and not item.root.doUpload.called
    item.root.filetype = "lz"  # Changing settings cannot change the captured request.
    item.workers[0]()
    callback.assert_called_once_with("/sd/jobs/part.cnc", "cached.cnc")
    assert not Path(item.root.uploading_file).exists()
    assert not item.root._upload_preparing and item.root.controller.sendNUM == 0
    item.root.compress_file.assert_not_called()


@pytest.mark.parametrize("change", ["bytes", "connection", "preview", "cancel"])
def test_changed_context_or_cancel_rejects_before_transfer(upload_case, change):
    item = upload_case
    main.Makera.uploadLocalFile(item.root, str(item.path))
    if change == "bytes":
        item.path.write_bytes(b"G20\r\n")
    elif change == "connection":
        item.root.controller._connection_generation += 1
    elif change == "preview":
        item.root.program_preview_generation += 1
    else:
        item.root.cancelProcessingFile()
    item.workers[0]()
    pump_frames(3)
    item.root.doUpload.assert_not_called()
    assert item.root.controller.sendNUM == 0 and not item.root._upload_preparing
    assert "Upload not started" in item.root.show_message_popup.call_args.args[0]


def test_second_click_does_not_create_a_second_preparation(upload_case):
    item = upload_case
    main.Makera.uploadLocalFile(item.root, str(item.path))
    main.Makera.uploadLocalFile(item.root, str(item.path))
    assert len(item.workers) == 1
    item.workers[0]()
    item.root.doUpload.assert_called_once()


def test_reconnect_during_transfer_cannot_select_result_on_the_new_connection(upload_case):
    item = upload_case

    def reconnect(callback, **_kwargs):
        item.root.controller._connection_generation += 1
        callback("/sd/jobs/part.cnc", "cached.cnc")

    item.root.doUpload.side_effect = reconnect
    callback = Mock()
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    item.workers[0]()
    callback.assert_not_called()


@pytest.mark.parametrize("failure", [RuntimeError("no worker"), MemoryError()])
def test_worker_start_failure_releases_upload_admission(upload_case, monkeypatch, failure):
    def failed(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=failed, Event=threading.Event))
    item = upload_case
    main.Makera.uploadLocalFile(item.root, str(item.path))
    assert not item.root._upload_preparing
    item.root.doUpload.assert_not_called()
    assert "Could not start" in item.root.show_message_popup.call_args.args[0]


def test_existing_file_transfer_ownership_is_not_overwritten(upload_case):
    item = upload_case
    item.root.controller.sendNUM = 99
    main.Makera.uploadLocalFile(item.root, str(item.path))
    assert item.workers == []
    assert item.root.controller.sendNUM == 99
    item.root.doUpload.assert_not_called()


def test_transfer_started_during_preparation_keeps_its_ownership(upload_case):
    item = upload_case
    main.Makera.uploadLocalFile(item.root, str(item.path))
    item.root.controller.sendNUM = 99
    item.workers[0]()
    item.root.doUpload.assert_not_called()
    assert item.root.controller.sendNUM == 99


@pytest.mark.parametrize("compressed", [False, True])
def test_production_transfer_and_codec_use_snapshot_and_captured_target(upload_case, tmp_path, compressed):
    import hashlib
    import queue
    from functools import partial

    item = upload_case
    root = item.root
    cache = tmp_path / "cache"
    cache.mkdir()
    root.temp_dir = str(cache)
    root.filetype = "lz" if compressed else ""
    root.compress_file = partial(main.Makera.compress_file, root)
    root.doUpload = partial(main.Makera.doUpload, root)
    root.controller.pauseStream = Mock()
    root.controller.resumeStream = Mock()
    root.controller.uploadCommand = Mock()
    root.controller.log = queue.Queue()
    root.uploadCallback = Mock()
    root.confirm_reset = Mock()
    root.update_recent_local_dir_list = Mock()
    root.file_popup.remote_rv.current_dir = Mock()
    raw = b"G21\r\n"

    def transfer(path, digest, _callback):
        item.path.write_bytes(b"G20\r\n")
        root.file_popup.remote_rv.curr_dir = "/sd/changed"
        root.file_popup.firmware_mode = True
        if compressed:
            assert str(path).endswith(".lz")
            decoded = tmp_path / "decoded.cnc"
            assert main.Makera.decompress_file(root, path, str(decoded))
            assert decoded.read_bytes() == raw
            assert Path(path).parent.name.startswith("carvera-upload-")
        else:
            assert Path(path).read_bytes() == raw
        assert digest == hashlib.md5(raw).hexdigest()
        return True

    root.controller.stream.upload = Mock(side_effect=transfer)
    callback = Mock()
    main.Makera.uploadLocalFile(root, str(item.path), callback)
    item.workers[0]()
    expected_remote = "/sd/jobs/part.cnc" + (".lz" if compressed else "")
    root.controller.uploadCommand.assert_called_once_with(expected_remote)
    retained = cache / "jobs" / "part.cnc"
    assert retained.read_bytes() == raw
    if compressed:
        callback.assert_not_called()
        root.decompstatus = False
        root.pending_decompress_callback()
    callback.assert_called_once_with("/sd/jobs/part.cnc", str(retained))
    pump_frames(3)
    root.confirm_reset.assert_not_called()
    assert root._upload_prepare_cancel is None


def test_cancel_waiting_for_decompression_suppresses_deferred_selection(upload_case):
    item = upload_case

    def wait_decompression(callback, **_kwargs):
        item.root.decompstatus = True
        item.root.pending_decompress_callback = lambda: callback("/sd/jobs/part.cnc", "cached.cnc")

    item.root.doUpload.side_effect = wait_decompression
    callback = Mock()
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    item.workers[0]()
    assert item.root._upload_prepare_cancel is not None
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    assert len(item.workers) == 1
    item.root.cancelProcessingFile()
    item.root.decompstatus = False
    item.root.pending_decompress_callback()
    callback.assert_not_called()
    assert item.root._upload_prepare_cancel is None


def test_cancel_during_compression_never_starts_transfer(upload_case):
    item = upload_case
    item.root.filetype = "lz"

    def cancel_compression(*_args, cancelled, **_kwargs):
        item.root.cancelProcessingFile()
        assert cancelled()
        return

    item.root.compress_file.side_effect = cancel_compression
    main.Makera.uploadLocalFile(item.root, str(item.path))
    item.workers[0]()
    item.root.doUpload.assert_not_called()
    assert not item.root._upload_preparing


def test_preparation_popup_failure_releases_admission_without_starting_worker(upload_case):
    item = upload_case
    item.root.progressStart.side_effect = ValueError("popup unavailable")
    main.Makera.uploadLocalFile(item.root, str(item.path))
    assert item.workers == []
    assert not item.root._upload_preparing
    item.root.doUpload.assert_not_called()
    assert "popup unavailable" in item.root.show_message_popup.call_args.args[0]
