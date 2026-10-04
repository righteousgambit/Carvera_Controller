"""Workspace-local selection navigation. Never dispatches controller commands."""

from copy import deepcopy
from math import isfinite

from kivy.clock import Clock

from carveracontroller.desktop_view_state import capture_view, restore_view
from carveracontroller.machine.navigation_history import NavigationHistory
from carveracontroller.machine.scene_inspection import COMPONENT_TITLES
from carveracontroller.machine.simulation_bookmarks import validate_view


class SelectionNavigation:
    def __init__(self, workspace):
        self.workspace = workspace
        self.history = NavigationHistory()
        self.restoring = False

    def reset(self):
        self.history.clear()
        self.refresh_controls()

    def snapshot(self, kind, value):
        from carveracontroller.desktop_bookmarks import capture_navigation_context

        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        panel = getattr(ws, "operation_panel", None)
        program = getattr(panel, "program", None)
        point = {
            "kind": kind,
            "value": value,
            "line": value if kind == "program" else getattr(panel, "selected_line", None),
            "program": program.file_hash if program else None,
            "context": None,
            "view": None,
            "distance": None,
        }
        try:
            point["context"] = capture_navigation_context(ws)
            point["view"] = capture_view(viewer)
        except (ValueError, TypeError, AttributeError):
            point["context"] = point["view"] = None
        distance = getattr(viewer, "display_count", None)
        if program and type(distance) in (int, float) and isfinite(distance) and distance >= 0:
            point["distance"] = float(distance)
        return point

    def depart(self):
        if self.restoring or self.history.index < 0:
            return
        point = self.history.items[self.history.index]
        current = self.snapshot(point["kind"], point["value"])
        # Preserve the original identity. A setup edit must not silently rebind
        # an old selection to new geometry merely because the operator leaves it.
        if current["context"] == point["context"] and current["program"] == point["program"]:
            point = deepcopy(point)
            point.update(view=current["view"], distance=current["distance"])
            self.history.update_current(point)

    def arrive(self, kind, value):
        if self.restoring:
            return
        point = self.snapshot(kind, value)
        if self.history.index >= 0:
            previous = self.history.items[self.history.index]
            identity = ("kind", "value", "program", "context")
            if all(point[key] == previous[key] for key in identity):
                self.history.update_current(point)
                self.refresh_controls()
                return
        self.history.record(point)
        self.refresh_controls()

    def enter(self, page):
        ws = self.workspace
        panel = getattr(ws, "operation_panel", None)
        if page == "Scene":
            self.arrive("scene", ws.object_inspector.selected)
        elif page == "Job" and panel and panel.program and panel.selected_line is not None:
            self.arrive("program", panel.selected_line)
        else:
            self.arrive("section", page)

    def refresh_controls(self):
        ws = self.workspace
        if hasattr(ws, "workspace_back"):
            ws.workspace_back.disabled = not self.history.can_back
            ws.workspace_forward.disabled = not self.history.can_forward
            if self.history.index < 0:
                ws.navigation_label.text = "Selection history"
            else:
                point = self.history.items[self.history.index]
                ws.navigation_label.text = self.title(point) + " · local preview"
        for name, back, forward in (
            ("operation_panel", "back_action", "forward_action"),
            ("object_inspector", "back", "forward"),
        ):
            panel = getattr(ws, name, None)
            if panel:
                getattr(panel, back).disabled = not self.history.can_back
                getattr(panel, forward).disabled = not self.history.can_forward

    @staticmethod
    def title(point):
        if point["kind"] == "scene":
            return "Scene / " + COMPONENT_TITLES[point["value"]]
        if point["kind"] == "program":
            return f"Program / line {point['value']}"
        return point["value"]

    def _message(self, text):
        ws = self.workspace
        if hasattr(ws, "navigation_label"):
            ws.navigation_label.text = text
        if hasattr(ws, "operation_panel"):
            ws.operation_panel.history_note.text = text
        if hasattr(ws, "object_inspector"):
            ws.object_inspector.status.text = text

    def navigate(self, direction):
        self.depart()
        candidate = self.history.candidate(direction)
        if candidate is None:
            return False
        index, point = candidate
        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        try:
            current = self.snapshot(point["kind"], point["value"])
            if point["program"] != current["program"]:
                raise ValueError("Program revision changed")
            if point["context"] is not None and point["context"] != current["context"]:
                raise ValueError("Machine profile or setup changed; restore the matching setup to revisit this view")
            if point["view"] is not None:
                validate_view(point["view"])
            if point["distance"] is not None and not 0 <= point["distance"] <= viewer.get_total_distance():
                raise ValueError("Preview position no longer belongs to this program")
            if point["kind"] == "program":
                if ws.operation_panel.inspector is None:
                    raise ValueError("Program inspection unavailable")
                ws.operation_panel.inspector.explain(point["value"])
            elif point["kind"] == "scene" and point["value"] not in COMPONENT_TITLES:
                raise ValueError("Scene component unavailable")
            elif point["kind"] not in ("scene", "section"):
                raise ValueError("Selection kind unavailable")
            self.restoring = True
            if point["kind"] == "program":
                panel = ws.operation_panel
                panel._history_restoring = True
                panel.inspect_line(point["value"], seek=True)
                viewer.set_inspected_component(None)
                ws.select("Job", record_navigation=False)
                title = f"line {point['value']}"
                Clock.schedule_once(lambda _dt: panel._reveal(panel.inspection), 0)
            elif point["kind"] == "scene":
                ws.object_inspector.select(point["value"], record=False)
                title = COMPONENT_TITLES[point["value"]]
            else:
                ws.select(point["value"], record_navigation=False)
                title = point["value"]
            if point["distance"] is not None:
                viewer.set_pos_by_distance(point["distance"])
            if point["view"] is not None:
                restore_view(viewer, point["view"])
            self.history.commit(index)
            self.refresh_controls()
            self._message(f"Revisited {title} · local preview only")
            return True
        except (ValueError, AttributeError, TypeError) as exc:
            self._message("Navigation unavailable: " + str(exc))
            return False
        finally:
            self.restoring = False
            if hasattr(ws, "operation_panel"):
                ws.operation_panel._history_restoring = False
