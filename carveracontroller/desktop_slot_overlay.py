"""Configured G53 axis-reference markers; no occupancy or measured registration."""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp


class SlotOverlay:
    def __init__(self, interaction):
        self.interaction = interaction
        self.markers = []
        with interaction.overlay:
            for _ in range(6):
                color = Color(0.98, 0.72, 0.32, 0)
                ring = Line(circle=(0, 0, dp(7)), width=1.5)
                text = Rectangle(pos=(0, 0), size=(0, 0))
                self.markers.append([color, ring, text, None])

    def refresh(self):
        ws = self.interaction.workspace
        viewer = self.interaction.viewer
        panel = getattr(ws, "slot_inventory_panel", None)
        profile = viewer.machine_profile
        visible = (
            profile is not None
            and viewer.machine_visible
            and viewer.machine_group_visibility.get("atc", True)
            and not viewer.disabled
            and getattr(viewer, "recorded_machine_point", None) is None
        )
        rows = panel.overlay_rows() if panel is not None and visible else ()
        for index, marker in enumerate(self.markers):
            color, ring, text, number = marker
            color.a = 0
            if index >= len(rows):
                continue
            target_number, position = rows[index]
            try:
                target = profile.configured_atc_target(position, viewer._machine_pose.get("table", (0, 0, 0)))
                screen = self.interaction.project(target)
            except (ValueError, ArithmeticError):
                # A configured target may be outside this renderer's numeric
                # range. Preserve the receipt; never publish a bogus marker.
                continue
            if screen is None:
                continue
            ox, oy, width, height = self.interaction.viewport()
            if not ox <= screen[0] <= ox + width or not oy <= screen[1] <= oy + height:
                continue
            if target_number != number:
                caption = CoreLabel(text=f"T{target_number}", font_size=dp(12))
                caption.refresh()
                text.texture = caption.texture
                text.size = caption.texture.size
                marker[3] = target_number
            # Keep the label inside the viewport even near its right/top border.
            text.pos = (
                min(screen[0] + dp(9), ox + width - text.size[0]),
                min(screen[1] + dp(7), oy + height - text.size[1]),
            )
            ring.circle = (*screen[:2], dp(7))
            color.a = 1
