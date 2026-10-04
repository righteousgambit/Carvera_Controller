"""Named machine, cutter and six-slot toolset library for the desktop workspace."""

from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.desktop_components import DesktopScrollView as ScrollView
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
        self.drafts = {}
        self._kind_selection = {}
        self._editing_key = None
        self._baseline = {}
        self._building = False
        self.store = store
        error = None
        if self.store is None:
            try:
                self.store = ProfileStore()
            except ProfileError as exc:
                error = str(exc)

        class LibraryToolbar(components.AdaptiveGrid):
            def _reflow(self, *_):
                super()._reflow()
                # Keep related actions in balanced rows rather than orphaning Close.
                if len(self.children) == 6 and self.cols in (4, 5):
                    self.cols = 3
                    self.height = 2 * self.row_height + self.spacing[1]

        self.toolbar = LibraryToolbar(max_cols=6, min_width=115, row_height=34, spacing=dp(6))
        self.kind_buttons = {}
        for kind, title in (("machines", "Machines"), ("tools", "Cutters"), ("toolsets", "ATC toolsets")):
            item = components.Action(title, lambda k=kind: self.select_kind(k), height=dp(34))
            self.kind_buttons[kind] = item
            self.toolbar.add_widget(item)
        self.toolbar.add_widget(components.Action("Import JSON", lambda: self._file_action(False)))
        self.toolbar.add_widget(components.Action("Export JSON", lambda: self._file_action(True)))
        close = getattr(workspace, "close_profile_library", None)
        if close:
            self.toolbar.add_widget(components.Action("Close", close))
        self.add_widget(self.toolbar)
        self.body = BoxLayout(spacing=dp(12))
        self.list_card = components.Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
        self.list_heading = components.label("Saved machines", 14, height=24)
        self.list_card.add_widget(self.list_heading)
        self.search = self._input("", "Find by name")
        self.search.bind(text=lambda *_: self._refresh_list())
        self.list_card.add_widget(self.search)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(9))
        self.list_scroll = scroll
        self.list_items = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.list_items.bind(minimum_height=self.list_items.setter("height"))
        scroll.add_widget(self.list_items)
        self.list_card.add_widget(scroll)
        self.new_button = components.Action("+ New profile", self.new)
        self.list_card.add_widget(self.new_button)
        self.compact_controls = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        self.compact_layout = None
        self.body.add_widget(self.list_card)
        self.editor_card = components.Surface(orientation="vertical", padding=dp(14), spacing=dp(8))
        self.editor_heading = components.label("Machine profile", 18, height=28)
        self.editor_card.add_widget(self.editor_heading)
        self.editor_description = self._wrapped_label("")
        self.editor_card.add_widget(self.editor_description)
        self.editor_scroll = ScrollView(do_scroll_x=False, bar_width=dp(9))
        self.form = GridLayout(cols=1, spacing=dp(12), padding=(0, 0, dp(8), dp(8)), size_hint_y=None)
        self.form.bind(minimum_height=self.form.setter("height"))
        self.editor_scroll.add_widget(self.form)
        self.editor_card.add_widget(self.editor_scroll)
        self.draft_status = self._wrapped_label("Saved locally · no pending changes")
        self.editor_card.add_widget(self.draft_status)
        self.actions = components.AdaptiveGrid(max_cols=4, min_width=130, row_height=36, spacing=dp(8))
        self.save_button = components.Action("Save profile", self.save, primary=True)
        self.apply_button = components.Action("Use machine profile", self.apply)
        self.delete_button = components.Action("Delete", self.delete)
        self.revert_button = components.Action("Revert draft", self.revert)
        for item in (self.save_button, self.apply_button, self.revert_button, self.delete_button):
            self.actions.add_widget(item)
        self.editor_card.add_widget(self.actions)
        self.body.add_widget(self.editor_card)
        self.add_widget(self.body)
        self.body.bind(width=self._reflow)
        self._reflow()
        self.status = self._wrapped_label(
            "Profiles store local geometry and preferences. They do not calibrate or move the machine."
        )
        self.add_widget(self.status)
        if error:
            self.status.text = error + ". Existing file preserved; restore or repair it before editing."
            for item in (self.save_button, self.apply_button, self.delete_button):
                item.disabled = True
        else:
            self.refresh()

    def _wrapped_label(self, text):
        item = Label(
            text=text,
            font_name="Roboto",
            font_size=sp(12),
            color=self.components.MUTED,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        item.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        item.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(28), size[1])))
        return item

    def _reflow(self, *_):
        compact = self.body.width < dp(760)
        self.body.orientation = "vertical" if compact else "horizontal"
        if compact != self.compact_layout:
            self.compact_layout = compact
            self.list_card.clear_widgets()
            self.compact_controls.clear_widgets()
            if compact:
                self.compact_controls.add_widget(self.search)
                self.compact_controls.add_widget(self.new_button)
                self.list_card.add_widget(self.compact_controls)
                self.list_card.add_widget(self.list_scroll)
            else:
                for item in (self.list_heading, self.search, self.list_scroll, self.new_button):
                    self.list_card.add_widget(item)
        self.list_card.size_hint = (1, None) if compact else (None, 1)
        self.list_card.padding = dp(8 if compact else 12)
        if compact:
            self.list_card.height = dp(120)
        else:
            self.list_card.width = min(dp(280), max(dp(210), self.body.width * 0.24))
        self.editor_card.size_hint = (1, 1)

    def _section(self, title, columns=2):
        card = self.components.Surface(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None)
        card.add_widget(self.components.label(title, 13, height=22))
        grid = self.components.AdaptiveGrid(max_cols=columns, min_width=225, row_height=78, spacing=dp(10))
        card.add_widget(grid)
        grid.bind(height=lambda _, height: setattr(card, "height", height + dp(54)))
        card.height = grid.height + dp(54)
        self.form.add_widget(card)
        self.field_group = grid
        return grid

    def _input(self, value="", hint=""):
        return self.components.Field(text=str(value) if value is not None else "", hint_text=hint, height=dp(36))

    def select_kind(self, kind):
        self._stash_draft()
        self._kind_selection[self.selected_kind] = self.selected_id
        self.selected_kind, self.selected_id = kind, self._kind_selection.get(kind)
        self._editing_key = None
        self.search.text = ""
        self.refresh()

    def select_record(self, kind, identity):
        """Navigate to a saved entity while preserving the departing editor draft."""
        if not self.store or kind not in self.store.data:
            raise ProfileError("Unknown profile kind")
        record = next((r for r in self.store.data[kind] if r["id"] == identity), None)
        if record is None:
            raise ProfileError("Linked profile is missing")
        self.select_kind(kind)
        self._edit(record)
        self._refresh_list()

    def refresh(self):
        if not self.store:
            return
        for kind, button in self.kind_buttons.items():
            active = kind == self.selected_kind
            button.base_color = self.components.ACCENT if active else self.components.RAISED
            button.color = self.components.BG if active else self.components.TEXT
            button._paint()
        items = self.store.data[self.selected_kind]
        selected = next((r for r in items if r["id"] == self.selected_id), items[0] if items else None)
        if self.selected_id is None and (self.selected_kind, None) in self.drafts:
            selected = None
        self._edit(selected)
        self._refresh_list()

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
            button = self.components.Action(title, lambda r=record: self._edit(r), height=dp(54))
            if record["id"] == self.selected_id:
                button.base_color = (0.14, 0.27, 0.29, 1)
                button._paint()
            button.halign = "left"
            button.valign = "middle"
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

    def _raw_fields(self):
        return {key: control.text for key, control in self.fields.items()}

    def _stash_draft(self):
        if self._editing_key is not None and self._raw_fields() != self._baseline:
            self.drafts[self._editing_key] = self._raw_fields()
        elif self._editing_key is not None:
            self.drafts.pop(self._editing_key, None)

    def _draft_changed(self, *_):
        if self._building:
            return
        changed = sum(value != self._baseline.get(key) for key, value in self._raw_fields().items())
        self.draft_status.text = (
            f"Unsaved draft · {changed} changed fields · switching profiles preserves it"
            if changed
            else "Saved locally · no pending changes"
        )
        self.revert_button.disabled = not changed

    def revert(self):
        """Discard this editor's draft without changing stored or active metadata."""
        self.drafts.pop(self._editing_key, None)
        self._building = True
        for key, value in self._baseline.items():
            self.fields[key].text = value
        self._building = False
        self._draft_changed()
        self.status.text = "Draft reverted."

    def _row(self, title, key, value="", choices=None, hint=""):
        dimension_keys = {
            "diameter",
            "shank_diameter",
            "length",
            "flute_length",
            "corner_radius",
            "thread_pitch",
            "stickout",
            "vise_x",
            "vise_y",
            "vise_z",
            "vise_jaw_offset",
        }
        quantity = (
            "length"
            if key in dimension_keys
            else "angle"
            if key == "vise_rotation"
            else "scalar"
            if key in {"number", "port"}
            else None
        )
        row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(78 if quantity else 58), spacing=dp(2))
        row.add_widget(self.components.label(title, 11, color=self.components.MUTED, height=20))
        if choices:
            control = self.components.Choice(text=str(value), values=choices, height=dp(36))
        elif quantity:
            control = self.components.QuantityField(
                text=str(value) if value is not None else "",
                hint_text=hint,
                kind=quantity,
                optional=key in dimension_keys
                and key not in {"diameter", "shank_diameter", "vise_x", "vise_y", "vise_z", "vise_jaw_offset"},
                integer=key in {"number", "port"},
                minimum=-1000 if key.startswith("vise_") else 1 if key in {"number", "port"} else 0,
                maximum=1000 if key in dimension_keys or key == "vise_rotation" else 65535 if key == "port" else 9999,
            )
        else:
            control = self._input(value, hint)
        self.fields[key] = control
        row.add_widget(control)
        self.field_group.add_widget(row)
        return control

    def _asset_row(self, title, key, value="", suffixes=(".json", ".json.gz")):
        control = self._row(title, key, value, hint="Choose a local file")
        row = control.parent
        row.remove_widget(control)
        picker = BoxLayout(spacing=dp(6))
        picker.add_widget(control)

        def selected(path):
            if key in ("geometry_path", "holder_geometry_path") and Path(path).suffix.lower() in (
                ".step",
                ".stp",
                ".stl",
                ".obj",
            ):
                from carveracontroller.desktop_cad_import import open_cad_import

                open_cad_import(
                    path, lambda converted: setattr(control, "text", converted), holder=key == "holder_geometry_path"
                )
            else:
                control.text = path

        browse = self.components.Action(
            "Browse…",
            lambda: self.workspace.choose_asset_file(selected, suffixes=suffixes),
            size_hint_x=None,
            width=dp(90),
        )
        picker.add_widget(browse)
        row.add_widget(picker)
        return control

    def _preview_tool(self):
        try:
            from carveracontroller.desktop_tool_preview import ToolPreview
            from carveracontroller.machine.desktop_profiles import to_tool_definition

            definition = to_tool_definition(self._record())
            preview = ToolPreview(definition, on_close=lambda: popup.dismiss())
            popup = Popup(title=f"Cutter preview · {definition.description}", content=preview, size_hint=(0.85, 0.85))
            popup.bind(on_dismiss=lambda *_: preview.dispose())
            popup.open()
        except (ValueError, OSError) as exc:
            self.status.text = str(exc)

    def _edit(self, record):
        self._stash_draft()
        self._building = True
        self.selected_id = record["id"] if record else None
        self.form.clear_widgets()
        self.fields, self.slot_fields = {}, {}
        record = record or {}
        kind = self.selected_kind
        heading = {"machines": "Machine", "tools": "Cutter", "toolsets": "ATC toolset"}[kind]
        self.editor_heading.text = ("Edit " if self.selected_id else "New ") + heading.lower()
        self._section("Identity")
        self._row("Name", "name", record.get("name", ""), hint="A name you will recognize")
        self.delete_button.disabled = not bool(self.selected_id)
        if kind == "machines":
            self.editor_description.text = "Save connection, camera and model preferences for each machine. Using a profile does not connect or move it."
            self.apply_button.text = "Use machine profile"
            self._row("Machine model", "model", record.get("model", "C1"), ("C1", "CA1"))
            self._section("Connection")
            self._row("Network address", "host", record.get("host", ""), hint="192.168.0.79")
            self._row("Port", "port", record.get("port", 2222))
            self._section("Camera & machine preview", columns=1)
            self._row(
                "Camera snapshot URL", "camera_url", record.get("camera_url", ""), hint="http://host/snapshot.jpg"
            )
            self._asset_row(
                "Machine CAD file · .json.gz",
                "cad_path",
                record.get("cad_path", ""),
            )
            self._section("Default Mod Vise placement · new scene setups")
            for key, title in (
                ("vise_x", "X offset · mm"),
                ("vise_y", "Y offset · mm"),
                ("vise_z", "Z offset · mm"),
                ("vise_rotation", "Rotation about Z · degrees"),
                ("vise_jaw_offset", "Movable jaw shift · CAD Y mm"),
            ):
                self._row(title, key, record.get(key, 0))
        elif kind == "tools":
            self.editor_description.text = "Enter mm, fractions such as 1/4 in, or arithmetic. The interpretation appears beneath each value. Stored geometry uses mm; measured tool length and physical ATC position remain separate."
            self.apply_button.text = "Load cutter preview"
            self._row("Program tool number", "number", record.get("number", 1))
            self.shape_choices = {t.value.replace("_", " ").title(): t.value for t in ToolType}
            current_shape = record.get("shape", "flat_end_mill").replace("_", " ").title()
            self._row("Cutter shape", "shape", current_shape, tuple(self.shape_choices))
            self._section("Geometry · millimeters")
            for key, title in (
                ("diameter", "Cutting diameter · mm"),
                ("shank_diameter", "Shank diameter · mm"),
                ("length", "Overall length · mm"),
                ("flute_length", "Flute length · mm"),
                ("corner_radius", "Corner radius · mm"),
                ("thread_pitch", "Thread pitch · mm"),
                ("stickout", "Tip to collet face · mm"),
            ):
                self._row(
                    title,
                    key,
                    record.get(key, ""),
                    hint="Optional" if key not in ("diameter", "shank_diameter") else "Required",
                )
            self._section("CAD assets & drawings", columns=1)
            self._asset_row(
                "Cutter mesh · converted from STEP / STL / OBJ",
                "geometry_path",
                record.get("geometry_path", ""),
                suffixes=(".json", ".json.gz", ".step", ".stp", ".stl", ".obj"),
            )
            self._asset_row(
                "Holder mesh · origin at collet face",
                "holder_geometry_path",
                record.get("holder_geometry_path", ""),
                suffixes=(".json", ".json.gz", ".step", ".stp", ".stl", ".obj"),
            )
            self._asset_row(
                "Drawing / specification file",
                "drawing_path",
                record.get("drawing_path", ""),
                suffixes=(".pdf", ".png", ".jpg", ".jpeg", ".svg", ".dxf"),
            )
            self._row("Manufacturer CAD / catalog URL", "source_url", record.get("source_url", ""), hint="https://…")
            preview = self.components.Action("Inspect cutter & holder", self._preview_tool)
            self.form.add_widget(preview)
            self._section("Catalog details")
            self._row("Manufacturer", "vendor", record.get("vendor", ""), hint="Optional")
            self._row("Product / part number", "product_id", record.get("product_id", ""), hint="Optional")
            self._section("Notes", columns=1)
            self._row("Notes", "notes", record.get("notes", ""), hint="Optional")
        else:
            self.editor_description.text = "Assign six library cutters to the ATC preview. This does not change physical tools or measured offsets."
            self.apply_button.text = "Load toolset preview"
            tools = sorted(self.store.data["tools"], key=lambda t: t["name"].casefold())
            self.tool_choices = {f"{t['name']} · {t['id'][:8]}": t["id"] for t in tools}
            self.tool_choices["Empty slot"] = None
            reverse = {v: k for k, v in self.tool_choices.items()}
            self._section("ATC assignments")
            for slot in range(1, 7):
                current = reverse.get(record.get("slots", {}).get(str(slot)), "Empty slot")
                self.slot_fields[str(slot)] = self._row(
                    f"ATC slot {slot}", f"slot{slot}", current, tuple(self.tool_choices)
                )

        self.editor_scroll.scroll_y = 1
        self._editing_key = (self.selected_kind, self.selected_id)
        self._baseline = self._raw_fields()
        for key, value in self.drafts.get(self._editing_key, {}).items():
            if key in self.fields:
                self.fields[key].text = value
        for control in self.fields.values():
            control.bind(text=self._draft_changed)
        self._building = False
        self._draft_changed()
        self._refresh_list()

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
                elif isinstance(control, self.components.QuantityField):
                    try:
                        value = control.value()
                    except ValueError as exc:
                        raise ValueError(f"{key.replace('_', ' ').title()}: {exc}") from exc
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
            self.drafts.pop(self._editing_key, None)
            self._editing_key = None
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
                self.drafts.pop(self._editing_key, None)
                self._editing_key = None
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
