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
        preview.drawing.dispatch("on_dimension_selected", "shank_diameter")
        preview.drawing.redraw()
        assert preview.drawing.selected_dimension == "shank_diameter"
        assert preview.drawing.definition is definition
        assert all(button.top <= preview.drawing.top for button in preview.drawing.dimension_buttons.values())
        assert all(button.disabled for button in preview.view_actions)
        assert all(item.y >= preview.drawing.y for item in preview.drawing.annotations)
        # A redraw must preserve StencilView's push/pop instructions. Actual
        # drawing is exercised through the initialized app integration fixture.
        clipping = tuple(preview.drawing.canvas.before.children)
        for _ in range(3):
            preview.drawing.redraw()
            assert tuple(preview.drawing.canvas.before.children) == clipping
        preview.mode.text = "3D geometry"
        assert preview.viewport.children == [preview.view]
        assert all(not button.disabled for button in preview.view_actions)
        preview.dispose()
        assert not preview.view.trigger.is_triggered
        assert not preview.drawing.trigger.is_triggered
    finally:
        preview.dispose()
        Window.remove_widget(preview)
