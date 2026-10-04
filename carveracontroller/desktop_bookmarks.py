"""Save and revisit a local simulation point with revision checks."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import Action, DesktopScrollView, Field, Surface
from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.desktop_view_state import capture_view, restore_view
from carveracontroller.machine.simulation_bookmarks import BookmarkStore, revision_hash, validate_view


def capture_bookmark_context(workspace):
    profile = getattr(workspace, "selected_machine_profile", None)
    if not profile or not profile.get("id"):
        raise ValueError("Choose a saved machine profile first")
    viewer = workspace.machine.gcode_viewer
    scene = capture_scene_setup(workspace)
    profiles = dict(viewer.machine_component_profiles)
    if viewer.machine_profile:
        profiles["machine"] = viewer.machine_profile
    geometry = {
        key: {"components": value.components, "workholding": value.workholding, "atc": value.atc}
        for key, value in profiles.items()
    }
    store = getattr(workspace, "profile_store", None)
    context = {
        "scene": scene,
        "geometry": geometry,
        "tools": store.data["tools"] if store else [],
        "toolset": getattr(workspace, "loaded_toolset", None),
        "preview_tool_override": viewer.preview_tool_override,
        "program_tools": viewer.tool_table,
    }
    return profile["id"], revision_hash(context)


class BookmarkPanel(Surface):
    def __init__(self, operations, store=None, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(6), padding=dp(10), size_hint_y=None, **kwargs)
        from carveracontroller.desktop_operations import content_label

        self.bind(minimum_height=self.setter("height"))
        self.operations = operations
        self.store = store if store is not None else BookmarkStore()
        self.expanded = False
        self.toggle = Action("Bookmarks · show", self.toggle_expanded)
        self.add_widget(self.toggle)
        self.body = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.body.bind(minimum_height=self.body.setter("height"))
        row = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(38))
        self.name = Field(hint_text="Name this simulation point", size_hint_x=0.7)
        self.name.bind(on_text_validate=lambda *_: self.save())
        row.add_widget(self.name)
        row.add_widget(Action("Save point", self.save, size_hint_x=0.3))
        self.body.add_widget(row)
        self.note = content_label("Inspect a source line, frame the view, then save a named point.")
        self.body.add_widget(self.note)
        self.rows = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None, height=0)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.scroll = DesktopScrollView(size_hint_y=None, height=0, do_scroll_x=False)
        self.rows.bind(minimum_height=lambda obj, height: setattr(self.scroll, "height", min(dp(180), height)))
        self.scroll.add_widget(self.rows)
        self.body.add_widget(self.scroll)

    def toggle_expanded(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.add_widget(self.body)
            self.refresh()
            self.operations._reveal(self)
        else:
            self.remove_widget(self.body)
        self._title()

    def _title(self):
        profile = getattr(self.operations.workspace, "selected_machine_profile", None) or {}
        count = sum(item["profile_id"] == profile.get("id") for item in self.store.items)
        self.toggle.text = f"Bookmarks · {count} saved · {'hide' if self.expanded else 'show'}"

    def refresh(self):
        self.rows.clear_widgets()
        self._title()
        if self.store.load_error:
            self.note.text = "Bookmark library unavailable: " + self.store.load_error
            return
        panel = self.operations
        profile = getattr(panel.workspace, "selected_machine_profile", None) or {}
        for item in reversed(self.store.items):
            if item["profile_id"] != profile.get("id"):
                continue
            row = BoxLayout(spacing=dp(5), size_hint_y=None, height=dp(38))
            tool = f"T{item['tool']}" if item["tool"] is not None else "Unknown tool"
            button = Action(
                f"{item['name']} · line {item['line']} · {tool}",
                lambda entry=item: self.go(entry),
                halign="left",
                valign="middle",
                padding=(dp(8), 0),
            )
            button.shorten = True
            button.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0] - dp(16), size[1])))
            row.add_widget(button)
            row.add_widget(
                Action("Delete", lambda identity=item["id"]: self.delete(identity), size_hint_x=None, width=dp(68))
            )
            self.rows.add_widget(row)
        self.note.text = (
            "Inspect a source line, frame the view, then save a named point."
            if panel.program
            else "Load the matching program to revisit a saved point."
        )

    def save(self):
        panel = self.operations
        try:
            if not panel.inspector or panel.selected_line is None:
                raise ValueError("Inspect a source line before saving a point")
            if not self.name.text.strip():
                raise ValueError("Give this point a name")
            identity, setup_hash = capture_bookmark_context(panel.workspace)
            move = panel.inspector.explain(panel.selected_line)
            viewer = panel.workspace.machine.gcode_viewer
            view = capture_view(viewer)
            item = self.store.add(
                name=self.name.text,
                profile_id=identity,
                program_hash=panel.program.file_hash,
                setup_hash=setup_hash,
                line=panel.selected_line,
                source=move.source,
                tool=move.after.tool,
                view=view,
            )
            self.name.text = ""
            self.refresh()
            self.note.text = f"Saved {item['name']} · local preview point"
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.note.text = "Point not saved: " + str(exc)

    def go(self, item):
        panel = self.operations
        try:
            if not panel.program:
                raise ValueError("Load the saved program first")
            identity, setup_hash = capture_bookmark_context(panel.workspace)
            reason = self.store.mismatch(
                item, profile_id=identity, program_hash=panel.program.file_hash, setup_hash=setup_hash
            )
            if reason:
                raise ValueError(reason + "; return to the matching revision before revisiting this point")
            move = panel.inspector.explain(item["line"])
            if move.source != item["source"] or move.after.tool != item["tool"]:
                raise ValueError("Saved source or tool association does not match")
            view = validate_view(item["view"])
            panel.inspect_line(item["line"], seek=True)
            viewer = panel.workspace.machine.gcode_viewer
            restore_view(viewer, view)
            self.note.text = f"Revisited {item['name']} · local preview only"
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.note.text = "Point not restored: " + str(exc)

    def delete(self, identity):
        try:
            self.store.delete(identity)
            self.refresh()
            self.note.text = "Bookmark deleted"
        except (OSError, ValueError) as exc:
            self.note.text = "Bookmark not deleted: " + str(exc)
