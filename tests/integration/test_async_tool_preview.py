"""Actual cutter inspection preserves UI frames and rejects obsolete work."""

import threading
import time
from unittest.mock import Mock

from kivy.clock import Clock
from kivy.core.window import Window

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.desktop_tool_preview import ToolPreview
from tests.integration.conftest import pump_frames


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert predicate()


def test_mesh_preparation_leaves_ui_frames_and_close_available(kivy_app, monkeypatch):
    import carveracontroller.desktop_tool_preview as module

    entered, release = threading.Event(), threading.Event()
    owner = threading.get_ident()
    original = module.build_tool_mesh

    def prepare(definition, **kwargs):
        assert threading.get_ident() != owner
        entered.set()
        assert release.wait(5)
        return original(definition, **kwargs)

    monkeypatch.setattr(module, "build_tool_mesh", prepare)
    close = Mock()
    preview = ToolPreview(ToolDefinition(1, diameter=6.35), on_close=close)
    Window.add_widget(preview)
    try:
        wait_for(entered.is_set)
        ticks = []
        Clock.schedule_once(lambda _dt: ticks.append(True), 0)
        pump_frames(3)
        assert ticks and not preview.view.mesh.vertices
        button = next(w for w in preview.walk() if getattr(w, "text", "") == "Close")
        assert not button.disabled
        button.dispatch("on_release")
        close.assert_called_once()
        preview.dispose()
        release.set()
        pump_frames(10, sleep=0.01)
        assert not preview.view.mesh.vertices
    finally:
        release.set()
        preview.dispose()
        Window.remove_widget(preview)


def test_projection_coalesces_orbit_resize_and_rejects_old_delivery(kivy_app, monkeypatch):
    import carveracontroller.desktop_tool_preview as module

    preview = ToolPreview(ToolDefinition(1, diameter=6.35), size_hint=(None, None), size=(600, 700))
    Window.add_widget(preview)
    entered, release = threading.Event(), threading.Event()
    calls = []
    owner = threading.get_ident()
    try:
        wait_for(lambda: bool(preview.view.mesh.vertices) and not preview.view.projecting)
        old = list(preview.view.mesh.vertices)
        original = module.project_mesh

        def project(vertices, indices, center, pose, cancelled):
            assert threading.get_ident() != owner
            calls.append(pose)
            if len(calls) == 1:
                entered.set()
                assert release.wait(5)
                # A late success must be rejected even if the worker ignores Cancel.
                return [777.0] * 36, [0, 1, 2]
            return original(vertices, indices, center, pose, cancelled)

        monkeypatch.setattr(module, "project_mesh", project)
        preview.view.yaw = 0.8
        preview.view.redraw()
        wait_for(entered.is_set)
        for i in range(20):
            preview.view.yaw = 1 + i / 10
            preview.view.redraw()
        preview.size = (410, 510)
        pump_frames(3)
        assert len(calls) == 1 and list(preview.view.mesh.vertices) == old
        release.set()
        wait_for(lambda: len(calls) == 2 and not preview.view.projecting)
        assert calls[-1].yaw == 2.9
        assert (calls[-1].width, calls[-1].height) == tuple(preview.view.size)
        assert 777.0 not in preview.view.mesh.vertices
        assert old != list(preview.view.mesh.vertices)
        assert len(preview.view.mesh.indices) == len(preview.view.indices)
    finally:
        release.set()
        preview.dispose()
        Window.remove_widget(preview)


def test_dispose_during_projection_never_publishes(kivy_app, monkeypatch):
    import carveracontroller.desktop_tool_preview as module

    preview = ToolPreview(ToolDefinition(1, diameter=6.35))
    Window.add_widget(preview)
    entered, release, ended = threading.Event(), threading.Event(), threading.Event()
    try:
        wait_for(lambda: bool(preview.view.mesh.vertices) and not preview.view.projecting)
        old = list(preview.view.mesh.vertices)

        def project(*args):
            entered.set()
            assert release.wait(5)
            ended.set()
            return [999.0] * 36, [0, 1, 2]

        monkeypatch.setattr(module, "project_mesh", project)
        preview.view.redraw()
        wait_for(entered.is_set)
        preview.dispose()
        release.set()
        wait_for(ended.is_set)
        pump_frames(5)
        assert list(preview.view.mesh.vertices) == old
        assert preview.view.pending is None and not preview.view.trigger.is_triggered
    finally:
        release.set()
        preview.dispose()
        Window.remove_widget(preview)


import pytest


@pytest.mark.parametrize("phase", ["geometry", "projection"])
@pytest.mark.parametrize("stage", ["construct", "start"])
@pytest.mark.parametrize("failure", [RuntimeError, OSError])
def test_worker_launch_failure_recovers_without_retry(kivy_app, monkeypatch, phase, stage, failure):
    import carveracontroller.desktop_tool_preview as module

    preview = ToolPreview(ToolDefinition(1, diameter=6.35))
    Window.add_widget(preview)
    try:
        old = []
        if phase == "projection":
            wait_for(lambda: bool(preview.view.mesh.vertices) and not preview.view.projecting)
            old = list(preview.view.mesh.vertices)
        attempts = []

        class FailedThread:
            def __init__(self, **kwargs):
                attempts.append(kwargs["name"])
                if stage == "construct":
                    raise failure("private environment detail")

            def start(self):
                raise failure("private environment detail")

        monkeypatch.setattr(module.threading, "Thread", FailedThread)
        if phase == "projection":
            preview.view.redraw()
        else:
            pump_frames(3)
        assert len(attempts) == 1
        assert "worker could not start" in preview.hint.text
        assert "private environment" not in preview.hint.text
        assert not preview.view.preparing and not preview.view.projecting
        assert list(preview.view.mesh.vertices) == old
        pump_frames(4)
        assert len(attempts) == 1
    finally:
        preview.dispose()
        Window.remove_widget(preview)


def test_geometry_failure_is_visible_and_nominal_drawing_remains_usable(kivy_app, tmp_path):
    preview = ToolPreview(ToolDefinition(1, diameter=6.35, geometry_path=str(tmp_path / "missing.json")))
    Window.add_widget(preview)
    try:
        wait_for(lambda: not preview.view.preparing)
        assert "could not be prepared" in preview.hint.text
        assert not preview.view.mesh.vertices
        preview.mode.text = "Dimensioned drawing"
        pump_frames(3)
        assert preview.viewport.children == [preview.drawing_scroll]
        preview.mode.text = "3D geometry"
        assert "could not be prepared" in preview.hint.text
    finally:
        preview.dispose()
        Window.remove_widget(preview)


def test_large_cad_inspection_retains_every_triangle_and_prepares_off_ui(kivy_app, tmp_path, monkeypatch):
    import json

    import carveracontroller.desktop_tool_preview as module

    path = tmp_path / "SYNTHETIC-20000-triangles.json"
    path.write_text(
        json.dumps(
            {
                "schema": "carvera-tool-mesh-v1",
                "units": "mm",
                "axis": "+Z",
                "origin": "tip",
                "triangles": [-1, 0, 0, 1, 0, 0, 0, 1, 12] * 20000,
            }
        )
    )
    owner = threading.get_ident()
    original_build, original_project = module.build_tool_mesh, module.project_mesh
    stages = []

    def build(definition, **kwargs):
        assert threading.get_ident() != owner
        result = original_build(definition, **kwargs)
        stages.append("geometry")
        return result

    def project(*args):
        assert threading.get_ident() != owner
        result = original_project(*args)
        stages.append("projection")
        return result

    monkeypatch.setattr(module, "build_tool_mesh", build)
    monkeypatch.setattr(module, "project_mesh", project)
    preview = ToolPreview(
        ToolDefinition(1, diameter=6.35, geometry_path=str(path)), size_hint=(None, None), size=(900, 1000)
    )
    Window.add_widget(preview)
    send = Mock()
    monkeypatch.setattr(kivy_app.root.desktop_workspace.machine.controller, "executeCommand", send)
    try:
        wait_for(lambda: bool(preview.view.mesh.vertices) and not preview.view.projecting)
        assert "geometry" in stages and "projection" in stages
        assert len(preview.view.indices) == 60000
        assert len(preview.view.mesh.indices) == 60000
        assert len(preview.view.mesh.vertices) == 60000 * 12
        assert preview.view.renderer.shader.success
        send.assert_not_called()
    finally:
        preview.dispose()
        Window.remove_widget(preview)


def test_close_interrupts_actual_cad_mesh_packing(kivy_app, tmp_path, monkeypatch):
    import json

    from kivy.uix.popup import Popup

    from carveracontroller.addons.tool_visualization import cad_assets

    path = tmp_path / "synthetic.json"
    path.write_text(
        json.dumps(
            {
                "schema": "carvera-tool-mesh-v1",
                "units": "mm",
                "axis": "+Z",
                "origin": "tip",
                "triangles": [-1, 0, 0, 1, 0, 0, 0, 1, 12] * 1000,
            }
        )
    )
    validated, entered, release, ended = (threading.Event() for _ in range(4))
    original_load, original_check = cad_assets.load_tool_asset, cad_assets._check_cancelled
    interrupted = []
    owner = threading.get_ident()

    def load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        validated.set()
        return result

    def check(cancelled):
        if validated.is_set() and not entered.is_set():
            assert threading.get_ident() != owner
            entered.set()
            assert release.wait(5)
        try:
            original_check(cancelled)
        except InterruptedError:
            interrupted.append(True)
            ended.set()
            raise

    monkeypatch.setattr(cad_assets, "load_tool_asset", load)
    monkeypatch.setattr(cad_assets, "_check_cancelled", check)
    close, send = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.desktop_workspace.machine.controller, "executeCommand", send)
    preview = ToolPreview(ToolDefinition(1, geometry_path=str(path)), on_close=lambda: (close(), popup.dismiss()))
    popup = Popup(title="Synthetic cutter", content=preview)
    popup.bind(on_dismiss=lambda *_: preview.dispose())
    popup.open()
    try:
        wait_for(entered.is_set)
        ticks = []
        Clock.schedule_once(lambda _dt: ticks.append(True), 0)
        pump_frames(3)
        assert ticks
        button = next(w for w in preview.walk() if getattr(w, "text", "") == "Close")
        button.dispatch("on_release")
        close.assert_called_once()
        assert preview.view.closed.is_set()
        release.set()
        wait_for(ended.is_set)
        pump_frames(4)
        assert interrupted == [True]
        assert not preview.view.vertices and not preview.view.mesh.vertices
        assert not preview.view.projecting
        send.assert_not_called()
    finally:
        release.set()
        preview.dispose()
        popup.dismiss()
