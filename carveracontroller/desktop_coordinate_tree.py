"""Selectable coordinate dependencies with explicit evidence and relationship kinds."""

from kivy.graphics import Color, Line
from kivy.metrics import dp

from carveracontroller.desktop_components import ACCENT, AMBER, BG, MUTED, RAISED, TEXT, Action, Surface
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.coordinate_review import coordinate_paths


def coordinates(row):
    if row.display_value is not None:
        return row.display_value
    return (
        "No resolved point · " + row.source
        if row.point_mm is None
        else "  ".join(f"{axis} {value:.4f}" for axis, value in zip("XYZ", row.point_mm)) + " mm"
    )


class FrameNode(Action):
    def __init__(self, path, depth, select, maximum_depth=1):
        self.path, self.depth = path, depth
        self.maximum_depth = max(1, maximum_depth)
        super().__init__(
            f"{path.review.name}\n{coordinates(path.review)}",
            select,
            height=dp(64),
            halign="left",
            valign="middle",
            padding=(dp(28 + 14 * depth), dp(8), dp(8), dp(8)),
        )
        with self.canvas.after:
            self.branch_color = Color(*MUTED)
            self.branch = Line(points=[], width=1)
        self.bind(size=self.layout_node, pos=self.layout_node, texture_size=self.layout_node)
        self.layout_node()

    def layout_node(self, *_):
        step = min(dp(14), max(0, (self.width * 0.3 - dp(28)) / self.maximum_depth))
        indent = dp(28) + self.depth * step
        self.padding = (indent, dp(8), dp(8), dp(8))
        self.text_size = (max(1, self.width), None)
        self.height = max(dp(64), self.texture_size[1] + dp(16))
        x, y = self.x + indent - dp(18), self.center_y
        self.branch.points = [x, self.top - dp(8), x, y, x + dp(8), y] if self.depth else [x, y, x + dp(8), y]

    def selected(self, active):
        self.base_color = ACCENT if active else RAISED
        self.color = BG if active else TEXT
        self.branch_color.rgba = BG if active else MUTED
        self._paint()


class CoordinateTree:
    def __init__(self, rows, detail, on_inspect=None):
        self.rows, self.detail = rows, detail
        self.on_inspect = on_inspect
        self.paths = ()
        self.nodes = {}
        self.selected_name = None
        self.captured = None

    def clear(self, reason):
        self.paths = ()
        self.nodes = {}
        self.selected_name = None
        self.captured = None
        self.rows.clear_widgets()
        self.detail.text = reason
        self.detail.color = MUTED

    def show(self, review, captured):
        self.show_paths(coordinate_paths(review), captured)

    def show_paths(self, paths, captured):
        previous = self.selected_name
        self.clear("Select a coordinate dependency to inspect its source and relation.")
        self.paths = tuple(paths)
        self.captured = captured
        for group in dict.fromkeys(path.group for path in self.paths):
            title = wrapped()
            title.text = group
            title.color = MUTED
            # Separate group headers from the public selectable-row collection.
            group_box = Surface(orientation="vertical", padding=dp(6), spacing=dp(4), size_hint_y=None)
            group_box.bind(minimum_height=group_box.setter("height"))
            group_box.add_widget(title)
            members = tuple(path for path in self.paths if path.group == group)
            ordered = []

            def append_children(parent, depth, members=members, ordered=ordered):
                for path in members:
                    if path.parent == parent:
                        ordered.append((path, depth))
                        append_children(path.review.name, depth + 1)

            append_children(None, 0)
            maximum_depth = max((depth for _, depth in ordered), default=1)
            for path, depth in ordered:
                node = FrameNode(
                    path, depth, lambda name=path.review.name: self.select(name, navigate=True), maximum_depth
                )
                self.nodes[path.review.name] = node
                group_box.add_widget(node)
            self.rows.add_widget(group_box)
        if self.paths:
            self.select(previous if previous in self.nodes else self.paths[0].review.name)

    def select(self, name, navigate=False):
        if name not in self.nodes:
            return False
        self.selected_name = name
        for key, node in self.nodes.items():
            node.selected(key == name)
        path = self.nodes[name].path
        row = path.review
        self.detail.color = AMBER if row.point_mm is None and row.display_value is None else TEXT
        self.detail.text = (
            f"{row.name} · {coordinates(row) if row.point_mm is not None or row.display_value is not None else 'No resolved point'}\n"
            f"{path.relationship}" + (f" · from {path.parent}" if path.parent else " · no parent asserted") + "\n"
            f"Source: {row.source}\n{row.relation}"
        )
        if navigate and self.on_inspect is not None:
            self.on_inspect()
        return True
