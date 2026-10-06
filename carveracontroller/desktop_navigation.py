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
        self.restore_generation = 0
        self.restore_event = None
        self.closed = False

    def dispose(self):
        self.closed = True
        self.restore_generation += 1
        if self.restore_event is not None:
            self.restore_event.cancel()

    def task_changed(self, page, *, arriving):
        if self.closed or self.restoring or self.workspace.active_section != page:
            return
        if arriving:
            self.enter(page)
        else:
            self.depart()

    def task_context(self, page):
        ws = self.workspace
        decks = {"Job": "program_tasks", "Setup": "setup_tasks", "Settings": "machine_tasks"}
        if page in decks:
            deck = getattr(ws, decks[page], None)
            return (deck.active, deck.scroll) if deck is not None else (None, None)
        if page == "Monitor" and hasattr(ws, "monitor_sections"):
            return ws.monitor_sections.current, ws.monitor_sections.current_screen.children[0]
        return None, None

    def reset(self):
        self.restore_generation += 1
        if self.restore_event is not None:
            self.restore_event.cancel()
            self.restore_event = None
        self.history.clear()
        self.refresh_controls()

    def snapshot(self, kind, value):
        from carveracontroller.desktop_bookmarks import capture_navigation_context

        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        panel = getattr(ws, "operation_panel", None)
        program = getattr(panel, "program", None)
        task, scroll = self.task_context("Job" if kind == "program" else value if kind == "section" else None)
        point = {
            "kind": kind,
            "task": task,
            "scroll": min(1, max(0, float(scroll.scroll_y))) if scroll is not None else None,
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
        if (
            program
            and getattr(viewer, "lengths", ())
            and type(distance) in (int, float)
            and isfinite(distance)
            and distance >= 0
        ):
            point["distance"] = float(distance)
        return point

    def depart(self):
        pending_restore = self.restore_event is not None and self.restore_event.is_triggered
        if not self.restoring:
            self.restore_generation += 1
            if self.restore_event is not None:
                self.restore_event.cancel()
                self.restore_event = None
        if self.restoring or self.history.index < 0:
            return
        point = self.history.items[self.history.index]
        current = self.snapshot(point["kind"], point["value"])
        # Preserve the original identity. A setup edit must not silently rebind
        # an old selection to new geometry merely because the operator leaves it.
        if current["context"] == point["context"] and current["program"] == point["program"]:
            point = deepcopy(point)
            point.update(view=current["view"], distance=current["distance"])
            if not pending_restore and point.get("task") == current.get("task"):
                point["scroll"] = current["scroll"]
            self.history.update_current(point)

    def arrive(self, kind, value):
        if self.restoring:
            return
        point = self.snapshot(kind, value)
        if self.history.index >= 0:
            previous = self.history.items[self.history.index]
            identity = ("kind", "value", "program", "context", "task")
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
            return f"Program / line {point['value']}" + (" / " + point["task"] if point.get("task") else "")
        return point["value"] + (" / " + point["task"] if point.get("task") else "")

    def _validate_task(self, point):
        page = "Job" if point["kind"] == "program" else point["value"]
        if point["kind"] == "section" and page != "Job" and page not in self.workspace.section_names:
            raise ValueError("Workbench page unavailable")
        task = point.get("task")
        if task is None:
            return
        ws = self.workspace
        decks = {"Job": "program_tasks", "Setup": "setup_tasks", "Settings": "machine_tasks"}
        names = (
            getattr(ws, decks[page]).sections
            if page in decks
            else ws.monitor_section_buttons
            if page == "Monitor"
            else ()
        )
        if not isinstance(task, str) or task not in names:
            raise ValueError("Workbench task unavailable")
        position = point.get("scroll")
        if type(position) not in (int, float) or not isfinite(position) or not 0 <= position <= 1:
            raise ValueError("Workbench reading position invalid")

    def _restore_task(self, point):
        task = point.get("task")
        if task is None:
            return
        ws = self.workspace
        page = "Job" if point["kind"] == "program" else point["value"]
        decks = {"Job": "program_tasks", "Setup": "setup_tasks", "Settings": "machine_tasks"}
        if page in decks:
            deck = getattr(ws, decks[page])
            deck.show(task)
            if hasattr(deck, "cancel_restore"):
                deck.cancel_restore()
            else:
                # Invalidate an inspect-line reveal queued before restoring this task.
                deck.generation += 1
        else:
            ws.monitor_section_buttons[task].dispatch("on_release")
        self.restore_generation += 1
        generation = self.restore_generation
        index = self.history.index

        def restore(_dt):
            if self.closed or generation != self.restore_generation or self.history.index != index:
                return
            current_task, scroll = self.task_context(page)
            if ws.active_section != page or current_task != task:
                return
            pending = list(scroll._viewport.walk(restrict=True)) + [scroll]
            if any(
                getattr(item, trigger, None) is not None and getattr(item, trigger).is_triggered
                for item in pending
                for trigger in ("_trigger_layout", "_trigger_texture")
            ):
                self.restore_event = Clock.schedule_once(restore, 0)
                return
            from kivy.animation import Animation

            Animation.cancel_all(scroll, "scroll_x", "scroll_y")
            position = point["scroll"]
            if scroll.effect_y is not None:
                scroll.effect_y.velocity = 0
                scroll.effect_y.reset(-max(0, scroll._viewport.height - scroll.height) * position)
            scroll.scroll_y = position
            self.restore_event = None

        self.restore_event = Clock.schedule_once(restore, 0)

    def _message(self, text):
        ws = self.workspace
        if hasattr(ws, "navigation_label"):
            ws.navigation_label.text = text
        if hasattr(ws, "operation_panel"):
            ws.operation_panel.history_note.text = text
        if hasattr(ws, "object_inspector"):
            ws.object_inspector.status.text = text

    def navigate(self, direction):
        if self.closed:
            return False
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
            if point["kind"] in ("section", "program"):
                self._validate_task(point)
            if point["distance"] is not None:
                distance = point["distance"]
                if type(distance) not in (int, float) or not isfinite(distance):
                    raise ValueError("Preview position is invalid")
                if not getattr(viewer, "lengths", ()):
                    raise ValueError("Toolpath preview geometry is unavailable")
                if not 0 <= distance <= viewer.get_total_distance():
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
            if point["kind"] in ("section", "program"):
                self._restore_task(point)
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
