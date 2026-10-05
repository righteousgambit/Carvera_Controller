"""Configured G53 axis-reference markers; no occupancy or measured registration."""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp


def label_positions(items, viewport, gap, inset):
    """Pack captions into ordered columns without moving their projected targets.

    Each item is (marker index, projected XY, caption size). Small viewports use
    additional columns rather than hiding labels or reducing their font size.
    """
    ox, oy, width, height = viewport
    available = max(0, height - 2 * inset)
    columns = [[]]
    occupied = 0
    for item in sorted(items, key=lambda item: (item[1][1], item[0])):
        required = item[2][1] + (gap if columns[-1] else 0)
        if columns[-1] and occupied + required > available:
            columns.append([])
            occupied = 0
        columns[-1].append(item)
        occupied += item[2][1] + (gap if len(columns[-1]) > 1 else 0)
    columns = [column for column in columns if column]
    if not columns:
        return {}
    widths = [max(item[2][0] for item in column) for column in columns]
    total_width = sum(widths) + gap * (len(columns) - 1)
    right = max(item[1][0] for item in items) + inset * 3
    left = min(item[1][0] for item in items) - inset * 3 - total_width
    start = right if right + total_width <= ox + width - inset else left
    start = max(ox + inset, min(start, ox + width - inset - total_width))
    result = {}
    for column, column_width in zip(columns, widths):
        positions = []
        bottom = oy + inset
        for index, anchor, size in column:
            y = max(bottom, min(anchor[1] - size[1] / 2, oy + height - inset - size[1]))
            positions.append(y)
            bottom = y + size[1] + gap
        # A crowded cluster may have pushed the final caption beyond the top.
        top = oy + height - inset
        for row in range(len(column) - 1, -1, -1):
            index, _anchor, size = column[row]
            positions[row] = min(positions[row], top - size[1])
            top = positions[row] - gap
        # Center the packed stack around its targets to shorten callouts.
        desired = sum(item[1][1] for item in column) / len(column)
        actual = sum(y + item[2][1] / 2 for y, item in zip(positions, column)) / len(column)
        shift = max(
            oy + inset - positions[0],
            min(desired - actual, oy + height - inset - positions[-1] - column[-1][2][1]),
        )
        for item, y in zip(column, positions):
            result[item[0]] = (start, y + shift)
        start += column_width + gap
    return result


class SlotOverlay:
    def __init__(self, interaction):
        self.interaction = interaction
        self.markers = []
        with interaction.overlay:
            for _ in range(6):
                color = Color(0.98, 0.72, 0.32, 0)
                ring = Line(circle=(0, 0, dp(7)), width=1.5)
                leader = Line(points=(), width=1)
                text = Rectangle(pos=(0, 0), size=(0, 0))
                self.markers.append([color, ring, text, None, leader])

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
        items = []
        viewport = self.interaction.viewport()
        for index, marker in enumerate(self.markers):
            color, ring, text, number, _leader = marker
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
            ox, oy, width, height = viewport
            if not ox <= screen[0] <= ox + width or not oy <= screen[1] <= oy + height:
                continue
            if target_number != number:
                caption = CoreLabel(text=f"T{target_number}", font_size=dp(12))
                caption.refresh()
                text.texture = caption.texture
                text.size = caption.texture.size
                marker[3] = target_number
            ring.circle = (*screen[:2], dp(7))
            items.append((index, screen[:2], text.size))
        positions = label_positions(items, viewport, gap=dp(4), inset=dp(4))
        for index, anchor, size in items:
            color, _ring, text, _number, leader = self.markers[index]
            text.pos = positions[index]
            x, y = text.pos
            edge = x if anchor[0] < x else x + size[0]
            leader.points = (*anchor, edge, y + size[1] / 2)
            color.a = 1
