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
    root.fail_decompression_wait = lambda message: main.Makera.fail_decompression_wait(root, message)
    yield SimpleNamespace(root=root, path=path, workers=workers, app=app)
    pump_frames(3)
    controller.stream.cancel_process.assert_not_called()


def test_snapshot_consumption_survives_original_mutation_and_pins_destination(upload_case):
    item = upload_case

    def consume(callback, **target):
        assert target["target_directory"] == "/sd/jobs" and target["firmware_mode"] is False
        assert target["transfer_generation"] == 7 and target["request_guard"]()
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
    pending = item.root.pending_decompress_callback
    item.root.cancelProcessingFile()
    assert item.root.pending_decompress_callback is None
    assert not item.root.decompstatus
    pending()
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


def test_unconfirmed_decompression_timeout_does_not_invoke_selection(upload_case):
    root = upload_case.root
    root.decompstatus = True
    root.fileCompressionBlocks = 4
    root.pending_decompress_callback = Mock()
    pending = root.pending_decompress_callback
    root._upload_prepare_cancel = threading.Event()
    main.Makera.fail_decompression_wait(root, "Machine decompression unconfirmed")
    pump_frames(3)
    pending.assert_not_called()
    assert root.pending_decompress_callback is None
    assert root._upload_prepare_cancel is None
    assert not root.decompstatus
    assert "unconfirmed" in root.show_message_popup.call_args.args[0]
    main.Makera.updateCompressProgress(root, 4)  # A late report cannot reopen the ended request.
    pending.assert_not_called()


@pytest.mark.parametrize("blocks,value", [(0, 0), (4, -1), (4, 5), (4, float("nan"))])
def test_invalid_decompression_progress_cannot_complete_request(upload_case, blocks, value):
    root = upload_case.root
    root.decompstatus = True
    root.fileCompressionBlocks = blocks
    root.pending_decompress_callback = Mock()
    main.Makera.updateCompressProgress(root, value)
    pump_frames(3)
    root.pending_decompress_callback.assert_not_called()
    assert root.decompstatus


def test_observed_decompression_count_finishes_and_publishes_once(upload_case):
    root = upload_case.root
    root.decompstatus = True
    root.fileCompressionBlocks = 4
    root.file_popup.remote_rv.current_dir = Mock()
    root.progressUpdate = Mock()
    callback = Mock()
    root.pending_decompress_callback = callback
    main.Makera.updateCompressProgress(root, 2)
    pump_frames(3)
    callback.assert_not_called()
    assert root.decompstatus
    main.Makera.updateCompressProgress(root, 4)
    pump_frames(6, sleep=0.03)
    callback.assert_called_once()
    assert not root.decompstatus
    main.Makera.updateCompressProgress(root, 4)
    pump_frames(3)
    callback.assert_called_once()


@pytest.fixture
def production_upload(upload_case, tmp_path):
    import queue
    from functools import partial

    item = upload_case
    root = item.root
    cache = tmp_path / "production-cache"
    cache.mkdir()
    root.temp_dir = str(cache)
    root.doUpload = partial(main.Makera.doUpload, root)
    root.controller.pauseStream = Mock()
    root.controller.resumeStream = Mock()
    root.controller.uploadCommand = Mock()
    root.controller.log = queue.Queue()
    root.uploadCallback = Mock()
    root.confirm_reset = partial(main.Makera.confirm_reset, root)
    root.confirm_popup = SimpleNamespace(
        lb_title=SimpleNamespace(text=""), lb_content=SimpleNamespace(text=""), open=Mock(), confirm=None
    )
    root.resetMachine = Mock()
    root.update_recent_local_dir_list = Mock()
    root.file_popup.remote_rv.current_dir = Mock()
    root.controller.stream.upload = Mock(return_value=True)
    return item


def test_transfer_finishing_after_new_selection_cannot_replace_it(production_upload):
    item = production_upload
    callback = Mock()

    def select_another(*_args):
        item.root.program_preview_generation += 1
        item.app.selected_local_filename = "later.cnc"
        return True

    item.root.controller.stream.upload.side_effect = select_another
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    item.workers[0]()
    callback.assert_not_called()
    assert item.app.selected_local_filename == "later.cnc"


def test_reconnected_transfer_preserves_new_owner_and_does_not_resume_it(production_upload):
    item = production_upload

    def reconnect(*_args):
        item.root.controller._connection_generation += 1
        item.root.controller.sendNUM = 99
        return True

    item.root.controller.stream.upload.side_effect = reconnect
    callback = Mock()
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    item.workers[0]()
    assert item.root.controller.sendNUM == 99
    item.root.controller.resumeStream.assert_not_called()
    callback.assert_not_called()
    assert not list(Path(item.root.temp_dir).rglob("*.cnc"))


@pytest.mark.parametrize("reconnect_at", ["during_transfer", "before_popup", "after_popup", "unchanged"])
def test_firmware_followups_remain_bound_to_the_upload_connection(production_upload, reconnect_at):
    item = production_upload
    root = item.root
    root.file_popup.firmware_mode = True
    if reconnect_at == "during_transfer":

        def reconnect(*_args):
            root.controller._connection_generation += 1
            root.controller.sendNUM = 99
            return True

        root.controller.stream.upload.side_effect = reconnect
    main.Makera.uploadLocalFile(root, str(item.path))
    item.workers[0]()
    if reconnect_at == "before_popup":
        root.controller._connection_generation += 1
    pump_frames(4)
    if reconnect_at == "unchanged":
        root.confirm_popup.open.assert_called_once()
        root.confirm_popup.confirm()
        root.resetMachine.assert_called_once()
        root.confirm_popup.confirm()
        root.resetMachine.assert_called_once()
        return
    if reconnect_at == "after_popup":
        root.confirm_popup.open.assert_called_once()
        root.controller._connection_generation += 1
        root.confirm_popup.confirm()
        assert "reset was not issued" in root.show_message_popup.call_args.args[0]
    else:
        root.confirm_popup.open.assert_not_called()
    root.resetMachine.assert_not_called()


@pytest.mark.parametrize("cancel_at", ["pause", "transfer"])
def test_cancelled_transfer_releases_its_own_receiver_and_local_admission(production_upload, cancel_at):
    item = production_upload

    def cancelled(*_args):
        item.root._upload_prepare_cancel.set()
        return

    if cancel_at == "pause":
        item.root.controller.pauseStream.side_effect = cancelled
    else:
        item.root.controller.stream.upload.side_effect = cancelled
    callback = Mock()
    main.Makera.uploadLocalFile(item.root, str(item.path), callback)
    item.workers[0]()
    item.root.controller.resumeStream.assert_called_once()
    assert item.root.controller.sendNUM == 0
    assert not item.root.uploading and not item.root._upload_preparing
    pump_frames(3)
    item.root.progressFinish.assert_called_once()
    callback.assert_not_called()


def test_repeated_or_regressing_reports_do_not_extend_completion_wait(upload_case):
    root = upload_case.root
    root.decompstatus = True
    root.fileCompressionBlocks = 7
    root.progressUpdate = Mock()
    root.pending_decompress_callback = Mock()
    assert main.Makera.updateCompressProgress(root, 2) is True
    assert main.Makera.updateCompressProgress(root, 2) is False
    assert main.Makera.updateCompressProgress(root, 1) is False
    assert main.Makera.updateCompressProgress(root, 999) is False
    assert root._decompression_valid_blocks == 2
    root.pending_decompress_callback.assert_not_called()


def test_decompression_ui_callbacks_cannot_touch_a_new_request(upload_case):
    root = upload_case.root
    root.decompstatus = True
    root.fileCompressionBlocks = 4
    root.progressUpdate = Mock()
    root.file_popup.remote_rv.current_dir = Mock()
    callback = Mock()
    root.pending_decompress_callback = callback
    root._upload_request_token = object()
    assert main.Makera.updateCompressProgress(root, 4)
    root._upload_request_token = object()
    pump_frames(6, sleep=0.03)
    callback.assert_not_called()
    root.progressFinish.assert_not_called()
    root.progressUpdate.assert_not_called()
    root.file_popup.remote_rv.current_dir.assert_not_called()


@pytest.mark.parametrize("report", [2, 1, 999])
def test_stale_or_invalid_reports_cannot_prevent_inactivity_timeout(upload_case, monkeypatch, report):
    root = upload_case.root
    root.decompstatus = True
    root.fileCompressionBlocks = 7
    root._decompression_valid_blocks = 2
    root.decompercent = report
    root.decompercentlast = -1
    root.decomptime = 100.0
    root.updateCompressProgress = lambda value: main.Makera.updateCompressProgress(root, value)
    root.pending_decompress_callback = Mock()
    callback = root.pending_decompress_callback
    monkeypatch.setattr(main, "time", SimpleNamespace(monotonic=lambda: 109.0))
    main.Makera.poll_decompression_wait(root)
    assert not root.decompstatus
    assert root.pending_decompress_callback is None
    callback.assert_not_called()


@pytest.mark.parametrize("change_at", ["pause", "hash", "transfer"])
def test_same_connection_owner_loss_is_rejected_without_releasing_other_owner(
    production_upload, monkeypatch, change_at
):
    item = production_upload
    root = item.root

    def lose_owner(*_args):
        root.controller.sendNUM = 99
        return True

    if change_at == "pause":
        root.controller.pauseStream.side_effect = lose_owner
    elif change_at == "hash":
        real_md5 = main.Utils.md5

        def hash_and_lose(path):
            digest = real_md5(path)
            root.controller.sendNUM = 99
            return digest

        monkeypatch.setattr(main.Utils, "md5", hash_and_lose)
    else:
        root.controller.stream.upload.side_effect = lose_owner
    callback = Mock()
    main.Makera.uploadLocalFile(root, str(item.path), callback)
    item.workers[0]()
    pump_frames(4)
    assert root.controller.sendNUM == 99
    root.controller.resumeStream.assert_not_called()
    callback.assert_not_called()
    assert not list(Path(root.temp_dir).rglob("*.cnc"))
    root.controller.sendNUM = 0
    pump_frames(3)
    root.progressStart.assert_called_once()
    if change_at != "transfer":
        root.controller.uploadCommand.assert_not_called()
        root.controller.stream.upload.assert_not_called()


@pytest.mark.parametrize("change_at", ["queued", "confirm"])
def test_firmware_followup_cannot_cross_same_connection_transfer_owner(production_upload, change_at):
    item = production_upload
    root = item.root
    root.file_popup.firmware_mode = True
    main.Makera.uploadLocalFile(root, str(item.path))
    item.workers[0]()
    if change_at == "queued":
        root.controller.sendNUM = 99
    pump_frames(4)
    if change_at == "confirm":
        root.confirm_popup.open.assert_called_once()
        root.controller.sendNUM = 99
        root.confirm_popup.confirm()
    else:
        root.confirm_popup.open.assert_not_called()
    root.resetMachine.assert_not_called()
    assert root.controller.sendNUM == 99
