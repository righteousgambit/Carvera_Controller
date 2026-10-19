"""Complete job setup recovery uses real UI state and fake transport only."""

import copy
from pathlib import Path
from unittest.mock import Mock

import pytest
from kivy.config import Config

from carveracontroller import desktop_job_transaction as transactions
from carveracontroller.CNC import CNC
from carveracontroller.desktop_job_transaction import LocalJobTransaction
from carveracontroller.machine.desktop_profiles import validate_record
from tests.integration.conftest import pump_frames
from tests.integration.test_staged_program_preview import staged as _staged

staged = _staged


def state(s):
    ws, v = s.root.desktop_workspace, s.viewer
    camera = ws.camera_registration_panel
    return {
        "setup": v.machine_setup,
        "profile": ws.selected_machine_profile,
        "cad": v.machine_profile,
        "components": dict(v.machine_component_profiles),
        "workholding": (v.workholding_offset_mm, v.workholding_rotation_deg, v.jaw_offset_mm),
        "tools": dict(v.library_tool_table_mm),
        "toolset": ws.loaded_toolset,
        "bindings": getattr(ws, "loaded_tool_profiles", None),
        "restored": getattr(ws, "restored_job", None),
        "pending": getattr(ws, "pending_job_rest_stock", None),
        "repeat": (v.repeat_stock_plan, v.repeat_stock_index, v.repeat_rest_geometries),
        "override": (v.preview_tool_override, v.assembly_preview_binding),
        "hash": v.loaded_program_hash,
        "lines": tuple(s.root.lines),
        "selection": s.app.selected_local_filename,
        "file_selection": s.root.file_popup.local_rv.curr_selected_file,
        "camera": (
            camera.registration,
            camera.reference,
            camera.points.text,
            camera.focal.text,
            camera.note.text,
            camera.reference_view.capture_framing(),
        ),
        "url": (ws.camera_client.url, ws.camera_client.snapshot()[0], ws.camera_url_input.text),
        "choices": {k: (c.text, tuple(c.values)) for k, c in ws.component_choices.items()},
        "geometry": copy.deepcopy(ws.simulation_geometry),
        "labels": (ws.profile_status.text, ws.selected_machine_label.text, ws.tool_library_summary.text),
    }


@pytest.fixture
def job(staged, tmp_path, monkeypatch):
    s = staged
    ws = s.root.desktop_workspace
    original_options = {
        key: Config.get("carvera", key) if Config.has_option("carvera", key) else None
        for key in ("desktop_machine_profile_id", "webcam_snapshot_url")
    }
    monkeypatch.setattr(Config, "filename", str(tmp_path / "preferences.ini"))
    assert Config.write()
    profile = validate_record(
        "machines",
        {
            "id": "imported",
            "name": "Imported machine",
            "host": "127.0.0.2",
            "camera_url": "http://127.0.0.1:18092/snapshot.jpg",
        },
    )
    backup = LocalJobTransaction(ws, profile)
    s.workspace, s.profile = ws, profile
    ws.camera_registration_panel.points.text = "unfitted point draft"
    ws.camera_registration_panel.focal.text = "400 400 320 240"
    ws.camera_registration_panel.note.text = "retained camera draft"
    s.analysis_reload = Mock(wraps=ws.operation_panel.load)
    monkeypatch.setattr(ws.operation_panel, "load", s.analysis_reload)
    s.before = state(s)
    s.preferences_before = Path(Config.filename).read_bytes()
    s.inventory_before = copy.deepcopy(ws.profile_store.data)
    s.library_before = copy.deepcopy(ws.scene_library.data)
    yield s
    backup.rollback()
    for key, value in original_options.items():
        if value is None:
            Config.remove_option("carvera", key)
        else:
            Config.set("carvera", key, value)


def apply_changes(s, tx):
    ws, v = s.workspace, s.viewer
    ws.apply_prepared_machine_profile(s.profile, None, preview_only=True)
    v.configure_machine((-100, -80, -60), (30, 20, 10), (1, 2, 3))
    v.configure_workholding((10, 20, 30), 45, 2)
    v.publish_tool_profiles(s.prepared.tool_profiles)
    v.select_preview_tool(None)
    ws.loaded_toolset = {"id": "imported-bank", "name": "Imported bank"}
    ws.loaded_tool_profiles = {}
    ws.restored_job = object()
    ws.pending_job_rest_stock = (str(s.path), object())
    ws.camera_registration_panel.apply_calibration(None)
    ws.show_imported_scene_controls(v.machine_setup, [])
    s.root.file_popup.local_rv.curr_selected_file = str(s.path)
    s.root.view_local_file(
        program_lines=s.prepared.program.lines, prepared_program=s.prepared, evidence_sink=tx.stage_manifest
    )


@pytest.mark.parametrize("fault", ["profile", "stock", "tools", "camera", "program", "preferences"])
def test_failure_recovers_entire_local_setup(job, monkeypatch, fault):
    s = job
    before_generation = s.root.program_preview_generation
    camera_revision = s.workspace.camera_registration_panel.reference_revision
    if fault == "preferences":
        monkeypatch.setattr(transactions, "replace_preferences", Mock(side_effect=OSError("commit fault")))
    else:
        obj, name = {
            "profile": (s.workspace, "apply_prepared_machine_profile"),
            "stock": (s.viewer, "configure_machine"),
            "tools": (s.viewer, "publish_tool_profiles"),
            "camera": (s.workspace.camera_registration_panel, "apply_calibration"),
            "program": (s.root, "view_local_file"),
        }[fault]
        original = getattr(obj, name)

        def fail_after(*args, **kwargs):
            original(*args, **kwargs)
            CNC.vars["wx"] = 987.654
            raise RuntimeError("after real mutation")

        monkeypatch.setattr(obj, name, fail_after)
    monkeypatch.setitem(CNC.vars, "wx", CNC.vars.get("wx", 0))
    with pytest.raises((RuntimeError, OSError)), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    pump_frames(3)
    assert state(s) == s.before
    assert not tx.recovery_errors and not s.workspace._job_apply_active
    assert s.root.program_preview_generation > before_generation
    assert s.workspace.camera_registration_panel.reference_revision > camera_revision
    if fault != "preferences":
        assert CNC.vars["wx"] == 987.654
    assert Path(Config.filename).read_bytes() == s.preferences_before
    assert s.workspace.profile_store.data == s.inventory_before
    assert s.workspace.scene_library.data == s.library_before
    s.record.assert_not_called()
    s.analysis_reload.assert_not_called()
    s.send.assert_not_called()


def test_success_commits_profile_preferences_and_manifest_once(job):
    s = job
    with LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        assert Path(Config.filename).read_bytes() == s.preferences_before
        s.record.assert_not_called()
        tx.commit()
    assert tx.committed and not tx.active and not s.workspace._job_apply_active
    assert s.viewer.loaded_program_hash == s.prepared.program.source_hash
    assert s.workspace.selected_machine_profile == s.profile
    assert Config.get("carvera", "desktop_machine_profile_id") == "imported"
    assert "desktop_machine_profile_id = imported" in Path(Config.filename).read_text()
    assert s.workspace.camera_client.url == s.profile["camera_url"]
    s.record.assert_called_once_with(s.prepared.manifest)
    s.analysis_reload.assert_called_once_with(str(s.path))
    assert s.workspace.profile_store.data == s.inventory_before
    assert s.workspace.scene_library.data == s.library_before
    with pytest.raises(ValueError, match="committed"):
        tx.rollback()


@pytest.mark.parametrize("fault", [False, True])
def test_real_archive_review_apply_is_one_local_transaction(job, tmp_path, monkeypatch, fault):
    import time
    from types import SimpleNamespace

    from carveracontroller import desktop_job_import_review as reviews
    from carveracontroller import desktop_job_packages as jobs
    from carveracontroller.machine.job_packages import JobPackage, save_package

    s = job
    ws = s.workspace
    deadline = time.monotonic() + 10
    while reviews.import_blocker(ws) and time.monotonic() < deadline:
        pump_frames(1, sleep=0.02)
    assert reviews.import_blocker(ws) is None
    s.before = state(s)
    package = JobPackage(
        "Whole local setup",
        s.path.read_bytes(),
        machine=s.profile,
        stock={"size_mm": [35, 25, 15], "origin_mm": [1, 2, 3]},
        vise={"offset_mm": [10, 20, 30], "rotation_deg": 45, "jaw_offset_mm": 2},
        tools=[
            {
                "id": "new-cutter",
                "name": "Imported cutter",
                "shape": "flat_end_mill",
                "diameter": 3.175,
                "shank_diameter": 6.35,
                "number": 2,
            }
        ],
    )
    archive = save_package(package, tmp_path / "transaction.cvjob")
    workers = []

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    proxy = SimpleNamespace(Thread=DeferredThread)
    monkeypatch.setattr(jobs, "threading", proxy)
    monkeypatch.setattr(reviews, "threading", proxy)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ws, "choose_asset_file", lambda callback, **_kwargs: callback(archive))
    monkeypatch.setattr(ws.scene_library, "save", Mock(side_effect=AssertionError("No imported library writes")))
    if fault:
        original = s.root.view_local_file

        def fail_after(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("after imported program")

        monkeypatch.setattr(s.root, "view_local_file", fail_after)
    jobs.import_job(ws)
    assert len(workers) == 1
    workers.pop(0)()
    pump_frames(4)
    review = ws._job_import_review
    assert not review.closed
    review.apply()
    assert len(workers) == 1
    workers.pop(0)()
    pump_frames(4)
    if fault:
        assert not review.closed
        assert state(s) == s.before
        assert "previous local preview restored" in ws.package_note.text
        assert Path(Config.filename).read_bytes() == s.preferences_before
        s.record.assert_not_called()
        review.cancel()
        assert "previous local preview restored" in ws.package_note.text
    else:
        assert review.closed
        assert ws.selected_machine_profile == s.profile
        assert s.viewer.machine_setup.stock_size_mm == (35, 25, 15)
        assert s.viewer.workholding_offset_mm == (10, 20, 30)
        assert s.viewer.library_tool_table_mm[2].diameter == 3.175
        assert "Restored local preview" in ws.package_note.text
        assert ws.camera_client.url == s.profile["camera_url"]
        s.record.assert_called_once()
        assert s.viewer.loaded_program_hash == s.record.call_args.args[0].parsed_lines_sha256
    assert ws.profile_store.data == s.inventory_before
    assert ws.scene_library.data == s.library_before
    ws.scene_library.save.assert_not_called()
    s.send.assert_not_called()


@pytest.mark.parametrize("change", ["selection", "program_generation", "import_generation", "connection_generation"])
def test_commit_refuses_superseded_context(job, monkeypatch, change):
    s = job
    if change == "connection_generation":
        monkeypatch.setattr(s.root.controller, "_connection_generation", s.root.controller._connection_generation)
    with pytest.raises(ValueError, match="context"), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        if change == "selection":
            s.app.selected_local_filename = "superseded.nc"
        elif change == "program_generation":
            s.root.program_preview_generation += 1
        elif change == "import_generation":
            monkeypatch.setattr(
                s.workspace,
                "_job_import_generation",
                getattr(s.workspace, "_job_import_generation", 0) + 1,
                raising=False,
            )
        else:
            s.root.controller._connection_generation += 1
        tx.commit()
    assert s.viewer.loaded_program_hash == s.before["hash"]
    assert Path(Config.filename).read_bytes() == s.preferences_before
    s.record.assert_not_called()


def test_failed_entry_releases_ownership_and_recovers_previous_view(job, monkeypatch):
    s = job
    original = s.viewer.set_machine_visible
    calls = 0

    def fail_once(*args):
        nonlocal calls
        calls += 1
        result = original(*args)
        if calls == 1:
            raise RuntimeError("entry render fault")
        return result

    monkeypatch.setattr(s.viewer, "set_machine_visible", fail_once)
    with pytest.raises(RuntimeError, match="entry render fault"), LocalJobTransaction(s.workspace, s.profile):
        pytest.fail("Failed entry cannot enter the body")
    assert not s.workspace._job_apply_active
    assert state(s) == s.before


def test_persistent_render_failure_retains_prior_model_but_withholds_identity(job, monkeypatch):
    s = job
    monkeypatch.setattr(s.viewer, "_publish_program_mesh", Mock(side_effect=RuntimeError("persistent renderer fault")))
    with (
        pytest.raises(RuntimeError, match="persistent renderer fault"),
        LocalJobTransaction(s.workspace, s.profile) as tx,
    ):
        apply_changes(s, tx)
        tx.commit()
    assert tx.recovery_errors
    assert s.viewer.meshmanager is s.old_manager and s.viewer.loaded_program_hash is None
    assert s.viewer.machine_setup == s.before["setup"]
    assert Path(Config.filename).read_bytes() == s.preferences_before
    s.record.assert_not_called()


def test_same_camera_url_restores_disabled_state_after_failed_commit(job, monkeypatch):
    s = job
    s.profile["camera_url"] = s.workspace.camera_client.url
    s.workspace.camera_client.set_enabled(False)
    before = s.workspace.camera_client.generation
    monkeypatch.setattr(transactions, "replace_preferences", Mock(side_effect=OSError("commit fault")))
    with pytest.raises(OSError), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert not s.workspace.camera_client.snapshot()[0]
    assert s.workspace.camera_client.generation > before
    assert not tx.recovery_errors


def test_manifest_observer_failure_does_not_undo_committed_preferences(job):
    s = job
    s.record.side_effect = RuntimeError("evidence unavailable")
    with LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert tx.committed and tx.warning
    assert s.root.controller.run_evidence.program is None
    assert s.viewer.loaded_program_hash == s.prepared.program.source_hash
    assert "desktop_machine_profile_id = imported" in Path(Config.filename).read_text()


def test_camera_draft_undo_and_framing_survive_failed_import(job, monkeypatch):
    s = job
    panel = s.workspace.camera_registration_panel
    panel.points.text = "previous points\nlast pick"
    panel._pick_undo = (panel.reference_revision, panel.points.text, "previous points")
    panel.reference_view.restore_framing({"zoom": 2, "center_x": 0.3, "center_y": 0.7})
    revision = panel.reference_revision
    monkeypatch.setattr(transactions, "replace_preferences", Mock(side_effect=OSError("commit fault")))
    with pytest.raises(OSError), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert panel.reference_revision > revision
    assert panel.reference_view.capture_framing() == {"zoom": 2, "center_x": 0.3, "center_y": 0.7}
    panel.undo_point_pick()
    assert panel.points.text == "previous points"
    s.record.assert_not_called()


def test_repeated_part_playback_and_previous_buffers_survive_failed_import(job):
    from carveracontroller.machine.program_operations import ProgramOperations
    from carveracontroller.machine.repeat_parts import RepeatPartPlan
    from carveracontroller.machine.repeat_playback import prepare_repeat_playback
    from tests.integration.conftest import load_gcode_file

    s = job
    original = s.old.read_bytes()
    try:
        # Repeat playback requires declared frames; qualify a real loaded G54
        # program instead of substituting an offset for the old implicit frame.
        s.old.write_bytes(b"G21 G90 G94 G17 G54\n" + original)
        load_gcode_file(s.app, str(s.old))
        s.analysis_reload.reset_mock()
        plan = RepeatPartPlan.grid(1, 2, (10, 0, 0), (0, 0, 0), (0, 0, -2), (4, 4, 2))
        part = plan.parts[0]
        s.viewer.configure_machine(
            part.work_offset_mm, part.stock_size_mm, part.stock_origin_mm, repeat_plan=plan, repeat_index=0
        )
        playback = prepare_repeat_playback(ProgramOperations.from_text("".join(s.root.lines)), plan)
        s.viewer.set_declared_playback(playback)
        before = state(s)
        manager, positions = s.viewer.meshmanager, tuple(s.viewer.raw_positions)
        with (
            pytest.raises(RuntimeError, match="after array replacement"),
            LocalJobTransaction(s.workspace, s.profile) as tx,
        ):
            apply_changes(s, tx)
            raise RuntimeError("after array replacement")
        assert state(s) == before
        assert s.viewer.meshmanager is manager
        assert tuple(s.viewer.raw_positions) == positions
        assert s.viewer.declared_playback is playback
        assert s.viewer.repeat_stock_plan is plan
        assert not tx.recovery_errors
        s.record.assert_not_called()
        s.analysis_reload.assert_not_called()
    finally:
        s.old.write_bytes(original)


def test_loaded_reference_calibration_recovers_with_current_fit_identity(job, monkeypatch):
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    s = job
    panel = s.workspace.camera_registration_panel
    calibration = decode_calibration(data())
    panel.apply_calibration(calibration)
    panel.reference_view.restore_framing({"zoom": 2, "center_x": 0.3, "center_y": 0.7})
    previous = state(s)
    revision = panel.reference_revision
    assert panel.fit_identity == panel._input_identity()
    monkeypatch.setattr(transactions, "replace_preferences", Mock(side_effect=OSError("commit fault")))
    with pytest.raises(OSError), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert state(s) == previous
    assert panel.reference is calibration[2]
    assert panel.registration is calibration[0]
    assert panel.fit_identity == panel._input_identity()
    assert panel.reference_revision > revision
    assert not tx.recovery_errors
    s.analysis_reload.assert_not_called()
    s.record.assert_not_called()


def test_imported_stock_dropdown_retains_usable_prepared_choice(job):
    s = job
    with LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    choice = s.workspace.component_choices["stock"]
    imported = choice.text
    assert imported.startswith("Imported job stock")
    choice.dispatch("on_press")
    assert imported in choice.values
    choice.text = "No stock configured"
    assert s.viewer.machine_setup.stock_size_mm is None
    choice.text = imported
    assert s.viewer.machine_setup.stock_size_mm == (30, 20, 10)
    assert s.viewer.machine_setup.stock_origin_mm == (1, 2, 3)
    assert s.workspace.scene_library.data == s.library_before
    s.send.assert_not_called()


def test_failed_import_recovers_previous_ephemeral_stock_choice(job):
    s = job
    s.viewer.configure_machine(s.viewer.machine_setup.work_offset_mm, (41, 21, 11), (4, 5, 6))
    s.workspace.show_imported_scene_controls(s.viewer.machine_setup, [])
    choice = s.workspace.component_choices["stock"]
    previous = choice.text
    previous_setup = s.viewer.machine_setup
    with pytest.raises(RuntimeError), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        raise RuntimeError("after temporary imported choices")
    assert not tx.recovery_errors
    choice.dispatch("on_press")
    assert choice.text == previous and previous in choice.values
    choice.text = "No stock configured"
    choice.text = previous
    assert s.viewer.machine_setup.stock_size_mm == previous_setup.stock_size_mm
    assert s.viewer.machine_setup.stock_origin_mm == previous_setup.stock_origin_mm


@pytest.mark.parametrize("group", ["fixture", "workholding"])
def test_imported_component_dropdown_uses_retained_registered_geometry(job, group):
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    s = job
    data = profile_data()
    data["components"].append({"group": group, "vertices": list(data["components"][0]["vertices"])})
    cad = MachineProfile(data)
    with LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        s.viewer.select_machine_component(group, cad)
        s.workspace.show_imported_scene_controls(s.viewer.machine_setup, [(group, cad)])
        tx.commit()
    choice = s.workspace.component_choices[group]
    imported = choice.text
    choice.dispatch("on_press")
    assert imported in choice.values
    choice.text = "Current model"
    assert group not in s.viewer.machine_component_profiles
    choice.text = imported
    assert s.viewer.machine_component_profiles[group] is cad
    assert s.workspace.scene_library.data == s.library_before
    s.send.assert_not_called()


def test_failed_commit_preserves_hidden_program_view_cache(job, monkeypatch):
    s = job
    s.viewer.set_machine_visible(False)
    s.viewer.m_zoom, s.viewer.m_xPan, s.viewer.m_yPan = 1.7, 0.3, -0.2
    s.viewer.set_machine_visible(True)
    saved = s.viewer._machine_camera_saved
    monkeypatch.setattr(transactions, "replace_preferences", Mock(side_effect=OSError("commit fault")))
    with pytest.raises(OSError), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert not tx.recovery_errors and s.viewer.machine_visible
    assert s.viewer._machine_camera_saved == saved
    s.viewer.set_machine_visible(False)
    assert s.viewer.m_zoom == pytest.approx(1.7)
    assert s.viewer.m_xPan == pytest.approx(0.3)
    assert s.viewer.m_yPan == pytest.approx(-0.2)
    s.record.assert_not_called()


def test_success_preserves_unrelated_preexisting_file_edit(job):
    from configparser import ConfigParser

    s = job
    path = Path(Config.filename)
    with path.open("ab") as stream:
        stream.write(b"\n[external_review]\nretained=preserve-me\npercent=50%\n")
    with LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert tx.committed
    parsed = ConfigParser(interpolation=None)
    parsed.read(path)
    assert parsed.get("external_review", "retained") == "preserve-me"
    assert parsed.get("external_review", "percent") == "50%"
    assert parsed.get("carvera", "desktop_machine_profile_id") == "imported"
    s.record.assert_called_once()


def test_failed_commit_preserves_inherited_preference_without_new_override(job, monkeypatch):
    s = job
    key = "desktop_machine_profile_id"
    monkeypatch.setitem(Config._defaults, key, "inherited-profile")
    Config.remove_option("carvera", key)
    monkeypatch.setattr(transactions, "replace_preferences", Mock(side_effect=OSError("commit fault")))
    with pytest.raises(OSError), LocalJobTransaction(s.workspace, s.profile) as tx:
        apply_changes(s, tx)
        tx.commit()
    assert not tx.recovery_errors
    assert key not in Config._sections["carvera"]
    assert Config.get("carvera", key) == "inherited-profile"
    s.record.assert_not_called()


@pytest.mark.parametrize("kind", ["stock", "fixture", "workholding"])
def test_new_saved_name_does_not_shadow_retained_imported_choice(job, tmp_path, monkeypatch, kind):
    import gzip
    import json
    import time

    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    s = job
    data = profile_data()
    group = "fixture" if kind == "stock" else kind
    data["components"].append({"group": group, "vertices": list(data["components"][0]["vertices"])})
    cad = MachineProfile(data)
    library = s.workspace.scene_library
    before_data = copy.deepcopy(library.data)
    monkeypatch.setattr(library, "path", tmp_path / "collision-library.json")
    try:
        with LocalJobTransaction(s.workspace, s.profile) as tx:
            apply_changes(s, tx)
            components = [] if kind == "stock" else [(kind, cad)]
            if components:
                s.viewer.select_machine_component(kind, cad)
            s.workspace.show_imported_scene_controls(s.viewer.machine_setup, components)
            tx.commit()
        choice = s.workspace.component_choices[kind]
        old_label = choice.text
        if kind == "stock":
            library.save("stocks", {"name": old_label, "size": [99, 98, 97], "origin": [0, 0, 0]})
        else:
            changed = copy.deepcopy(data)
            changed["components"][-1]["vertices"][0] = 99
            path = tmp_path / "saved-component.json.gz"
            path.write_bytes(gzip.compress(json.dumps(changed).encode()))
            library.save("fixtures" if kind == "fixture" else "vises", {"name": old_label, "path": str(path)})
        previous_setup = s.viewer.machine_setup
        choice.dispatch("on_press")
        retained_label = choice.text
        assert retained_label != old_label
        assert len(choice.values) == len(set(choice.values))
        assert retained_label in choice.values and old_label in choice.values
        # Merely refreshing the dropdown must preserve the current geometry.
        assert s.viewer.machine_setup is previous_setup
        if kind != "stock":
            assert s.viewer.machine_component_profiles[kind] is cad
        choice.text = old_label
        if kind == "stock":
            assert s.viewer.machine_setup.stock_size_mm == (99, 98, 97)
        else:
            deadline = time.monotonic() + 10
            while s.workspace.scene_component_loads.lanes[kind]["active"] and time.monotonic() < deadline:
                pump_frames(1, sleep=0.01)
            assert s.viewer.machine_component_profiles[kind].geometry_sha256 != cad.geometry_sha256
        choice.text = retained_label
        if kind == "stock":
            assert s.viewer.machine_setup.stock_size_mm == (30, 20, 10)
        else:
            assert s.viewer.machine_component_profiles[kind] is cad
        s.send.assert_not_called()
    finally:
        library.data = before_data
