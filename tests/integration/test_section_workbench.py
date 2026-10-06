from unittest.mock import Mock

from tests.integration.conftest import pump_frames


def wait_for_section(panel):
    for _ in range(200):
        pump_frames(1, sleep=0.01)
        if not panel.running:
            return
    raise AssertionError("Section worker did not finish")


def test_gpu_cutaway_discards_only_requested_half_space():
    from pathlib import Path

    from kivy.base import EventLoop
    from kivy.graphics import ClearBuffers, ClearColor, Fbo, Mesh
    from kivy.graphics.transformation import Matrix

    from carveracontroller.addons.machine_simulation.model import VERTEX_FORMAT
    from carveracontroller.machine.section_view import SectionClip

    EventLoop.ensure_window()
    pump_frames(2)
    fbo = Fbo(size=(64, 64))
    fbo.shader.source = str(Path(__file__).parents[2] / "carveracontroller/shaders/tool_pointer.glsl")
    assert fbo.shader.success
    for key in ("projection_mat", "modelview_mat", "rotation"):
        fbo[key] = Matrix()
    fbo["offset"] = (0.0, 0.0, 0.0)
    fbo["inspection_highlight"] = 0.0
    fbo["section_clip_enabled"] = 0.0
    fbo["section_clip_plane"] = (0.0, 0.0, 0.0, 0.0)
    vertices = [
        v for x, y in ((-0.8, -0.8), (0.8, -0.8), (0.8, 0.8), (-0.8, 0.8)) for v in (x, y, 0, 0, 0, 1, 1, 1, 1, 1)
    ]
    with fbo:
        ClearColor(0, 0, 0, 0)
        ClearBuffers()
        Mesh(vertices=vertices, indices=[0, 1, 2, 0, 2, 3], fmt=VERTEX_FORMAT, mode="triangles")

    def alpha(x):
        fbo.ask_update()
        fbo.draw()
        return fbo.pixels[(32 * 64 + x) * 4 + 3]

    assert alpha(16) > 0 and alpha(48) > 0
    fbo["section_clip_enabled"] = 1.0
    fbo["section_clip_plane"] = SectionClip(0, 0).shader_plane((0, 0, 0), 1)
    assert alpha(16) > 0 and alpha(48) == 0
    fbo["section_clip_plane"] = SectionClip(0, 0, True).shader_plane((0, 0, 0), 1)
    assert alpha(16) == 0 and alpha(48) > 0
    fbo["section_clip_enabled"] = 0.0
    assert alpha(16) > 0 and alpha(48) > 0


def test_component_cutaway_keeps_meshes_setup_and_other_components_intact(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.addons.machine_simulation.model import MachineSetup
    from carveracontroller.machine.section_view import SectionClip

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    original = viewer.machine_setup
    clips = dict(viewer.component_cutaways)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        viewer.machine_setup = MachineSetup(stock_size_mm=(40, 20, 10), work_offset_mm=(10, -20, 30))
        viewer.set_machine_visible(True)
        viewer._build_machine_scene()
        ws.object_inspector.select("stock")
        panel = ws.object_inspector.section_panel
        panel.axis.text = "Z"
        panel.coordinate.text = "35"
        geometry = viewer._inspection_geometry
        buffers = tuple(viewer._machine_contexts["stock"].children)
        panel.cutaway.text = "Keep below plane"
        assert viewer.component_cutaways["stock"] == SectionClip(2, 35)
        assert viewer._machine_contexts["stock"]["section_clip_enabled"] == 1
        assert viewer._machine_contexts["fixture"]["section_clip_enabled"] == 0
        assert viewer._machine_contexts["stock"].shader.success
        assert viewer.pointermesh["section_clip_enabled"] == 0
        assert viewer._inspection_geometry is geometry
        assert tuple(viewer._machine_contexts["stock"].children) == buffers
        assert viewer.machine_setup.work_offset_mm == (10, -20, 30)
        ws.object_inspector.select("fixture")
        assert panel.cutaway.text == "Full component"
        assert viewer.component_cutaways["stock"] == SectionClip(2, 35)
        ws.object_inspector.select("stock")
        assert panel.coordinate.text == "35" and panel.cutaway.text == "Keep below plane"
        panel.cutaway.text = "Keep above plane"
        assert viewer.component_cutaways["stock"] == SectionClip(2, 35, True)
        pump_frames(8)
        panel.export_to_png(str(tmp_path / "stock-cutaway-controls.png"))
        previous_width = panel.width
        previous_hint = panel.size_hint_x
        try:
            panel.size_hint_x = None
            panel.width = 360
            pump_frames(8)
            assert abs(panel.width - 360) <= 1
            assert panel.coordinate.width > 100
            assert panel.cutaway.right <= panel.right + 1
            assert panel.center_action.width > 100
            panel.export_to_png(str(tmp_path / "stock-cutaway-controls-360.png"))
        finally:
            panel.size_hint_x = previous_hint
            panel.width = previous_width
            pump_frames(2)
        panel.coordinate.text = "invalid"
        assert "stock" not in viewer.component_cutaways
        assert "withheld" in panel.cutaway_note.text
        assert viewer._machine_contexts["stock"]["section_clip_enabled"] == 0
        panel.coordinate.text = "35"
        assert viewer.component_cutaways["stock"] == SectionClip(2, 35, True)
        panel.cutaway.text = "Full component"
        assert "stock" not in viewer.component_cutaways
        assert viewer._inspection_geometry is geometry
        assert tuple(viewer._machine_contexts["stock"].children) == buffers
        send.assert_not_called()
    finally:
        viewer.component_cutaways = clips
        viewer.machine_setup = original
        viewer._build_machine_scene()
        ws.object_inspector.refresh()


def test_section_actions_dimension_stock_and_discard_changed_selection(kivy_app, tmp_path, monkeypatch):
    from carveracontroller.addons.machine_simulation.model import MachineSetup

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    original = viewer.machine_setup
    try:
        viewer.machine_setup = MachineSetup(stock_size_mm=(40, 20, 10), stock_origin_mm=(0, 0, 0))
        viewer.set_machine_visible(True)
        viewer._build_machine_scene()
        ws.object_inspector.select("stock")
        panel = ws.object_inspector.section_panel
        panel.center_action.dispatch("on_release")
        panel.calculate_action.dispatch("on_release")
        wait_for_section(panel)
        assert panel.plot.result is not None, panel.note.text
        assert panel.plot.result.bounds is not None
        assert "span 40.000 mm" in panel.dimensions.text
        assert "span 20.000 mm" in panel.dimensions.text
        assert panel.plot.height > 0
        pump_frames(4)
        viewport = ws.inspector_pages.get_screen("Scene").children[0]
        heading_y = panel.heading.to_window(panel.heading.x, panel.heading.top)[1]
        bottom = viewport.to_window(viewport.x, viewport.y)[1]
        top = viewport.to_window(viewport.x, viewport.top)[1]
        assert bottom < heading_y <= top
        assert not panel.export_action.disabled
        chooser = Mock()
        monkeypatch.setattr(ws, "choose_profile_file", chooser)
        panel.export_action.dispatch("on_release")
        save = chooser.call_args.args[0]
        target = tmp_path / "stock-section.svg"
        save(str(target))
        for _ in range(200):
            pump_frames(1, sleep=0.01)
            if not panel.export_running:
                break
        assert target.exists() and "section-contours" in target.read_text()
        assert "Saved Stock section" in panel.export_status.text
        assert "CAD triangles" in panel.note.text
        # A chooser left open across a plane change cannot export stale geometry.
        panel.export_action.dispatch("on_release")
        stale_save = chooser.call_args.args[0]
        panel.export_to_png(str(tmp_path / "stock-section.png"))
        from kivy.core.window import Window

        original_size = Window.size
        try:
            Window.size = (700, 900)
            pump_frames(8)
            assert panel.coordinate.width > 0
            assert panel.plot.width > 0
            vertices = panel.plot.mesh.vertices
            assert min(vertices[::4]) >= panel.plot.x
            assert max(vertices[::4]) <= panel.plot.right
            assert min(vertices[1::4]) >= panel.plot.y
            assert max(vertices[1::4]) <= panel.plot.top
            panel.export_to_png(str(tmp_path / "stock-section-narrow.png"))
        finally:
            Window.size = original_size
            pump_frames(5)
        panel.coordinate.text = str(float(panel.coordinate.text) + 1)
        assert panel.plot.result is None and not panel.dimensions.text
        assert panel.export_action.disabled
        stale_target = tmp_path / "stale-section.svg"
        stale_save(str(stale_target))
        assert not stale_target.exists()
        panel.calculate_action.dispatch("on_release")
        wait_for_section(panel)
        assert panel.plot.result is not None
        panel.axis.text = "X"
        assert panel.plot.result is None
        panel.calculate_action.dispatch("on_release")
        ws.object_inspector.select("fixture")
        assert panel.calculate_action.disabled
        wait_for_section(panel)
        assert panel.plot.result is None
        assert "span 40.000" not in panel.dimensions.text
        send.assert_not_called()
    finally:
        viewer.machine_setup = original
        viewer._build_machine_scene()
        ws.object_inspector.refresh()


def test_completed_section_does_not_reveal_after_leaving_scene(kivy_app, monkeypatch):
    import threading

    from carveracontroller import desktop_section_view
    from carveracontroller.addons.machine_simulation.model import MachineSetup

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    original = viewer.machine_setup
    real = desktop_section_view.section_geometry
    release, entered = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop_section_view, "section_geometry", delayed)
    try:
        viewer.machine_setup = MachineSetup(stock_size_mm=(40, 20, 10))
        viewer.set_machine_visible(True)
        viewer._build_machine_scene()
        ws.object_inspector.select("stock")
        pump_frames(8)
        scroll = ws.inspector_pages.get_screen("Scene").children[0]
        scroll.scroll_y = 0.2
        panel = ws.object_inspector.section_panel
        panel.calculate_action.dispatch("on_release")
        assert entered.wait(1)
        ws.select("Camera")
        release.set()
        wait_for_section(panel)
        pump_frames(12)
        assert panel.plot.result is not None
        assert ws.active_section == "Camera"
        assert scroll.scroll_y == 0.2
    finally:
        release.set()
        viewer.machine_setup = original
        viewer._build_machine_scene()
        ws.object_inspector.refresh()


def test_section_cancel_keeps_navigation_available_and_rejects_late_result(kivy_app, monkeypatch):
    import threading

    from carveracontroller import desktop_section_view
    from carveracontroller.addons.machine_simulation.model import MachineSetup

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    original = viewer.machine_setup
    real = desktop_section_view.section_geometry
    release = threading.Event()
    entered = threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        # Simulate a result already completed before cancellation was observed.
        return real(*args)

    monkeypatch.setattr(desktop_section_view, "section_geometry", delayed)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        viewer.machine_setup = MachineSetup(stock_size_mm=(40, 20, 10))
        viewer.set_machine_visible(True)
        viewer._build_machine_scene()
        ws.object_inspector.select("stock")
        panel = ws.object_inspector.section_panel
        panel.calculate_action.dispatch("on_release")
        assert entered.wait(1)
        assert panel.running and not panel.cancel_action.disabled
        ws.select("Camera")
        pump_frames(2)
        assert ws.active_section == "Camera"
        panel.cancel_action.dispatch("on_release")
        release.set()
        wait_for_section(panel)
        assert panel.plot.result is None
        assert "Cancelled" in panel.note.text
        assert ws.active_section == "Camera"
        send.assert_not_called()
    finally:
        release.set()
        viewer.machine_setup = original
        viewer._build_machine_scene()
        ws.object_inspector.refresh()


def test_dense_section_renders_every_segment_without_16bit_index_overflow(kivy_app):
    from carveracontroller.desktop_section_view import SectionPlot
    from carveracontroller.machine.section_view import SectionResult

    plot = SectionPlot()
    plot.size = (500, 250)
    # More than 65,535 vertices, resembling a dense fixture-hole midplane.
    segments = tuple(((i / 100, 0, 0), (i / 100, 1, 0)) for i in range(43520))
    plot.result = SectionResult(2, 0, segments, 99760, 1e-6)
    plot.redraw()
    assert sum(len(mesh.indices) for mesh in plot.meshes) == len(segments) * 2
    assert all(max(mesh.indices) < 65535 for mesh in plot.meshes)
    assert all(len(mesh.vertices) // 4 == len(mesh.indices) for mesh in plot.meshes)


def test_section_axes_and_scale_bar_match_projected_mm_at_multiple_widths(kivy_app, tmp_path):
    import pytest

    from carveracontroller.desktop_section_view import SectionPlot
    from carveracontroller.machine.section_view import SectionResult

    plot = SectionPlot()
    for axis, labels in ((0, ("Y right", "Z up")), (1, ("X right", "Z up")), (2, ("X right", "Y up"))):
        u, v = ((1, 2), (0, 2), (0, 1))[axis]
        start, end = [0.0] * 3, [0.0] * 3
        end[u], end[v] = 40.0, 20.0
        plot.result = SectionResult(axis, 0, ((tuple(start), tuple(end)),), 1, 1e-6)
        for width in (270, 1000):
            plot.size = (width, 250)
            plot.redraw()
            assert (plot.horizontal_axis.text, plot.vertical_axis.text) == labels
            x0, y0, _, _, x1, y1, _, _ = plot.mesh.vertices
            bar_x0, bar_y0, bar_x1, bar_y1 = plot.scale_bar.points
            assert (bar_x1 - bar_x0) / plot.scale_mm == pytest.approx((x1 - x0) / 40)
            assert (bar_x1 - bar_x0) / plot.scale_mm == pytest.approx((y1 - y0) / 20)
            assert bar_y0 == bar_y1 and plot.x <= bar_x0 < bar_x1 <= plot.right
            assert plot.scale_caption.text.endswith(" mm")
            assert plot.scale_caption.right < plot.horizontal_axis.x
            assert plot.scale_caption.text_size == plot.scale_caption.size
        if axis == 2:
            pump_frames(4)
            plot.export_to_png(str(tmp_path / "section-axes-scale-wide.png"))
            plot.width = 270
            plot.redraw()
            pump_frames(4)
            plot.export_to_png(str(tmp_path / "section-axes-scale-narrow.png"))
    plot.result = None
    plot.redraw()
    assert not plot.horizontal_axis.text and not plot.vertical_axis.text and not plot.scale_caption.text
    assert plot.scale_bar is None and plot.height == 0
