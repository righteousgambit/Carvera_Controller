"""Named machine, cutter and six-slot toolset library for the desktop workspace."""

from pathlib import Path

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.machine.desktop_profiles import ProfileError, ProfileStore


class ProfileLibrary(BoxLayout):
    """Edits local metadata. Applying profiles delegates to read-only workspace hooks."""

    def __init__(self, workspace, store=None, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), **kwargs)
        # Delayed import avoids a cycle while the workspace is constructing itself.
        try:
            from carveracontroller import desktop_components as components
        except ImportError:
            from carveracontroller import desktop_workspace as components
        self.components = components
        self.workspace = workspace
        self.selected_kind = "machines"
        self.selected_id = None
        self.fields = {}
        self.slot_fields = {}
        self.store = store
        error = None
        if self.store is None:
            try:
                self.store = ProfileStore()
            except ProfileError as exc:
                error = str(exc)
        toolbar = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        for kind, title in (("machines", "Machines"), ("tools", "Cutters"), ("toolsets", "ATC toolsets")):
            toolbar.add_widget(components.Action(title, lambda k=kind: self.select_kind(k), height=dp(36)))
        toolbar.add_widget(Widget())
        toolbar.add_widget(components.Action("Import JSON", lambda: self._file_action(False), height=dp(36)))
        toolbar.add_widget(components.Action("Export JSON", lambda: self._file_action(True), height=dp(36)))
        close = getattr(workspace, "close_profile_library", None)
        if close:
            toolbar.add_widget(components.Action("Close", close, height=dp(36), size_hint_x=None, width=dp(72)))
        self.add_widget(toolbar)
        body = BoxLayout(spacing=dp(12))
        list_card = components.Surface(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_x=0.30)
        self.list_heading = components.label("Saved machines", 15, height=30)
        list_card.add_widget(self.list_heading)
        self.search = self._input("", "Find by name")
        self.search.bind(text=lambda *_: self._refresh_list())
        list_card.add_widget(self.search)
        scroll = ScrollView(do_scroll_x=False)
        self.list_items = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.list_items.bind(minimum_height=self.list_items.setter("height"))
        scroll.add_widget(self.list_items)
        list_card.add_widget(scroll)
        list_card.add_widget(components.Action("+ New profile", self.new, primary=True))
        body.add_widget(list_card)
        self.editor_card = components.Surface(orientation="vertical", padding=dp(16), spacing=dp(8), size_hint_x=0.70)
        self.editor_heading = components.label("Machine profile", 19, height=32)
        self.editor_card.add_widget(self.editor_heading)
        self.editor_description = components.label("", 12, color=components.MUTED, height=42)
        self.editor_card.add_widget(self.editor_description)
        editor_scroll = ScrollView(do_scroll_x=False)
        self.form = GridLayout(cols=1, spacing=dp(10), size_hint_y=None)
        self.form.bind(minimum_height=self.form.setter("height"))
        editor_scroll.add_widget(self.form)
        self.editor_card.add_widget(editor_scroll)
        actions = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self.save_button = components.Action("Save profile", self.save, primary=True, height=dp(38))
        self.apply_button = components.Action("Use machine profile", self.apply, height=dp(38))
        self.delete_button = components.Action("Delete", self.delete, height=dp(38), size_hint_x=0.4)
        for item in (self.save_button, self.apply_button, self.delete_button):
            actions.add_widget(item)
        self.editor_card.add_widget(actions)
        body.add_widget(self.editor_card)
        self.add_widget(body)
        self.status = components.label(
            "Profiles store local geometry and preferences. They do not calibrate or move the machine.",
            12,
            color=components.MUTED,
            height=38,
        )
        self.add_widget(self.status)
        if error:
            self.status.text = error + ". Existing file preserved; restore or repair it before editing."
            for item in (self.save_button, self.apply_button, self.delete_button):
                item.disabled = True
        else:
            self.refresh()

    def _input(self, value="", hint=""):
        return self.components.Field(text=str(value) if value is not None else "", hint_text=hint, height=dp(36))

    def select_kind(self, kind):
        self.selected_kind, self.selected_id = kind, None
        self.search.text = ""
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        self._refresh_list()
        items = self.store.data[self.selected_kind]
        selected = next((r for r in items if r["id"] == self.selected_id), items[0] if items else None)
        self._edit(selected)

    def _refresh_list(self):
        self.list_items.clear_widgets()
        if not self.store:
            return
        titles = {"machines": "Saved machines", "tools": "Saved cutters", "toolsets": "Saved ATC toolsets"}
        self.list_heading.text = titles[self.selected_kind]
        records = self.store.data[self.selected_kind]
        needle = self.search.text.casefold().strip()
        for record in sorted(records, key=lambda r: r["name"].casefold()):
            if needle and needle not in (record["name"] + " " + record.get("product_id", "")).casefold():
                continue
            if self.selected_kind == "tools":
                detail = f"Ø {record['diameter']:g} mm · T{record['number']}"
            elif self.selected_kind == "machines":
                detail = f"{record['model']} · {record['host'] or 'No address'}"
            else:
                detail = f"{len(record['slots'])} of 6 slots assigned"
            title = f"{record['name']}\n{detail}"
            button = self.components.Action(title, lambda r=record: self._edit(r), height=dp(64))
            button.halign = "left"
            button.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0] - dp(16), size[1])))
            self.list_items.add_widget(button)
        if not self.list_items.children:
            self.list_items.add_widget(
                self.components.label(
                    "No profiles match." if records else "Create your first profile.",
                    12,
                    color=self.components.MUTED,
                    height=44,
                )
            )

    def new(self):
        if self.store:
            self._edit(None)

    def _row(self, title, key, value="", choices=None, hint=""):
        row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(64), spacing=dp(3))
        row.add_widget(self.components.label(title, 11, color=self.components.MUTED, height=22))
        control = (
            self.components.Choice(text=str(value), values=choices, height=dp(36))
            if choices
            else self._input(value, hint)
        )
        self.fields[key] = control
        row.add_widget(control)
        self.form.add_widget(row)
        return control

    def _edit(self, record):
        self.selected_id = record["id"] if record else None
        self.form.clear_widgets()
        self.fields, self.slot_fields = {}, {}
        record = record or {}
        kind = self.selected_kind
        heading = {"machines": "Machine", "tools": "Cutter", "toolsets": "ATC toolset"}[kind]
        self.editor_heading.text = ("Edit " if self.selected_id else "New ") + heading.lower()
        self._row("Name", "name", record.get("name", ""), hint="A name you will recognize")
        self.delete_button.disabled = not bool(self.selected_id)
        if kind == "machines":
            self.editor_description.text = "Save connection, camera and model preferences for each machine. Using a profile does not connect or move it."
            self.apply_button.text = "Use machine profile"
            self._row("Machine model", "model", record.get("model", "C1"), ("C1", "CA1"))
            self._row("Network address", "host", record.get("host", ""), hint="192.168.0.79")
            self._row("Port", "port", record.get("port", 2222))
            self._row(
                "Camera snapshot URL", "camera_url", record.get("camera_url", ""), hint="http://host/snapshot.jpg"
            )
            self._row(
                "Converted machine CAD profile path",
                "cad_path",
                record.get("cad_path", ""),
                hint="Optional .json.gz model path",
            )
        elif kind == "tools":
            self.editor_description.text = "Dimensions are millimeters. Overall length describes the cutter; measured tool length and actual ATC position remain separate."
            self.apply_button.text = "Load cutter preview"
            self._row("Program tool number", "number", record.get("number", 1))
            self.shape_choices = {t.value.replace("_", " ").title(): t.value for t in ToolType}
            current_shape = record.get("shape", "flat_end_mill").replace("_", " ").title()
            self._row("Cutter shape", "shape", current_shape, tuple(self.shape_choices))
            for key, title in (
                ("diameter", "Cutting diameter · mm"),
                ("shank_diameter", "Shank diameter · mm"),
                ("length", "Overall length · mm"),
                ("flute_length", "Flute length · mm"),
                ("corner_radius", "Corner radius · mm"),
                ("thread_pitch", "Thread pitch · mm"),
                ("vendor", "Manufacturer"),
                ("product_id", "Product / part number"),
                ("notes", "Notes"),
            ):
                self._row(
                    title,
                    key,
                    record.get(key, ""),
                    hint="Optional" if key not in ("diameter", "shank_diameter") else "Required",
                )
        else:
            self.editor_description.text = "Assign six library cutters to the ATC preview. This does not change physical tools or measured offsets."
            self.apply_button.text = "Load toolset preview"
            tools = sorted(self.store.data["tools"], key=lambda t: t["name"].casefold())
            self.tool_choices = {f"{t['name']} · {t['id'][:8]}": t["id"] for t in tools}
            self.tool_choices["Empty slot"] = None
            reverse = {v: k for k, v in self.tool_choices.items()}
            for slot in range(1, 7):
                current = reverse.get(record.get("slots", {}).get(str(slot)), "Empty slot")
                self.slot_fields[str(slot)] = self._row(
                    f"ATC slot {slot}", f"slot{slot}", current, tuple(self.tool_choices)
                )

    def _record(self):
        result = {"name": self.fields["name"].text.strip()}
        if self.selected_id:
            result["id"] = self.selected_id
        if self.selected_kind == "toolsets":
            result["slots"] = {
                slot: self.tool_choices[control.text]
                for slot, control in self.slot_fields.items()
                if self.tool_choices[control.text] is not None
            }
        else:
            for key, control in self.fields.items():
                value = control.text.strip()
                if key == "shape":
                    value = self.shape_choices[value]
                elif key in ("port", "number"):
                    value = int(value)
                elif key in ("diameter", "shank_diameter", "length", "flute_length", "corner_radius", "thread_pitch"):
                    value = float(value) if value else None
                result[key] = value
        return result

    def save(self):
        if not self.store:
            return None
        try:
            method = {
                "machines": self.store.save_machine,
                "tools": self.store.save_tool,
                "toolsets": self.store.save_toolset,
            }[self.selected_kind]
            result = method(self._record())
            self.selected_id = result["id"]
            self.refresh()
            self.status.text = f"Saved {result['name']} locally. Physical setup and offsets are unchanged."
            return result
        except (ValueError, OSError) as exc:
            self.status.text = str(exc)
            return None

    def apply(self):
        record = self.save()
        if record is None:
            return
        try:
            if self.selected_kind == "machines":
                self.workspace.apply_machine_profile(record)
            elif self.selected_kind == "tools":
                self.workspace.apply_tool_profile(record)
            else:
                self.workspace.apply_toolset_profile(record, self.store.toolset_definitions(record))
            self.status.text = f"Loaded {record['name']} into the workspace. No machine commands sent."
        except (ValueError, OSError) as exc:
            self.status.text = str(exc)

    def delete(self):
        if not self.store or not self.selected_id:
            return
        content = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))
        content.add_widget(
            self.components.label(
                "Delete this local profile? Tools assigned to a toolset must be removed from that set first.",
                13,
                height=70,
            )
        )
        popup = Popup(title="Delete profile", content=content, size_hint=(None, None), size=(dp(480), dp(220)))
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        row.add_widget(self.components.Action("Cancel", popup.dismiss))

        def perform():
            try:
                self.store.delete(self.selected_kind, self.selected_id)
                self.selected_id = None
                self.refresh()
                self.status.text = "Deleted the local profile."
            except (ProfileError, OSError) as exc:
                self.status.text = str(exc)
            popup.dismiss()

        row.add_widget(self.components.Action("Delete profile", perform, danger=True))
        content.add_widget(row)
        popup.open()

    def _file_action(self, exporting):
        if not self.store:
            return

        def chosen(path):
            try:
                if exporting:
                    saved = self.store.export_file(path)
                    self.status.text = f"Exported local profiles to {saved}"
                else:
                    counts = self.store.import_file(path)
                    self.refresh()
                    self.status.text = f"Merged {counts['machines']} machines, {counts['tools']} cutters and {counts['toolsets']} toolsets."
            except (ProfileError, OSError) as exc:
                self.status.text = str(exc)

        chooser = getattr(self.workspace, "choose_profile_file", None)
        if chooser:
            chooser(chosen, save=exporting)
            return
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
        path = self._input(str(Path.home() / "Downloads/carvera-profiles.json"))
        content.add_widget(self.components.label("JSON file path", 13, height=28))
        content.add_widget(path)
        popup = Popup(
            title="Export profiles" if exporting else "Import profiles",
            content=content,
            size_hint=(None, None),
            size=(dp(620), dp(220)),
        )
        content.add_widget(
            self.components.Action(
                "Export" if exporting else "Import", lambda: (chosen(path.text), popup.dismiss()), primary=True
            )
        )
        popup.open()
