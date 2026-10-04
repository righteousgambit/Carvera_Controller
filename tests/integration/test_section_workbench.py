from unittest.mock import Mock

from tests.integration.conftest import pump_frames


def wait_for_section(panel):
    for _ in range(200):
        pump_frames(1, sleep=0.01)
        if not panel.running:
            return
    raise AssertionError("Section worker did not finish")


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
        assert panel.plot.result.bounds is not None
        assert "span 40.000 mm" in panel.dimensions.text
        assert "span 20.000 mm" in panel.dimensions.text
        assert panel.plot.height > 0
        pump_frames(4)
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
