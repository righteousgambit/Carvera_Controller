"""Catch real Kivy property/shader errors that mesh-only tests cannot detect."""

from kivy.clock import Clock
from kivy.core.window import Window

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_tool_preview import ToolPreview


def test_preview_orbit_fit_and_dispose_are_hardware_independent():
    definition = ToolDefinition(
        1,
        tool_type=ToolType.FLAT_END_MILL,
        diameter=6.35,
        shank_diameter=6.35,
        length=76.2,
        stickout=35,
        flute_length=25.4,
    )
    preview = ToolPreview(definition, size_hint=(None, None), size=(600, 700))
    Window.add_widget(preview)
    try:
        Clock.tick()
        preview.view.redraw()
        assert preview.view.renderer.shader.success
        assert preview.view.mesh.vertices
        assert max(preview.view.indices) < len(preview.view.vertices) // 12
        old = list(preview.view.mesh.vertices)
        preview.view.yaw += 0.5
        preview.view.redraw()
        assert old != list(preview.view.mesh.vertices)
        preview.view.zoom_by(2)
        assert preview.view.zoom == 2
        preview.view.fit()
        assert preview.view.zoom == 1
        preview.mode.text = "Dimensioned drawing"
        Clock.tick()
        Clock.tick()
        preview.drawing.redraw()
        assert preview.viewport.children == [preview.drawing_scroll]
        assert preview.drawing.annotations[-1].text == "Inserted cutter: 41.2 mm"
        assert all(button.disabled for button in preview.view_actions)
        assert all(item.y >= preview.drawing.y for item in preview.drawing.annotations)
        preview.mode.text = "3D geometry"
        assert preview.viewport.children == [preview.view]
        assert all(not button.disabled for button in preview.view_actions)
        preview.dispose()
        assert not preview.view.trigger.is_triggered
        assert not preview.drawing.trigger.is_triggered
    finally:
        preview.dispose()
        Window.remove_widget(preview)
