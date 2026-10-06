"""Named machine, cutter and six-slot toolset library for the desktop workspace."""

from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.desktop_components import DesktopScrollView as ScrollView
from carveracontroller.machine.desktop_profiles import ProfileError, ProfileStore
from carveracontroller.machine.library_browser import CutterFilter, browse_profiles


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
        self.tool_drawing = None
        self.tool_drawing_card = None
        self.tool_dimension = ""
        self.geometry_trigger = Clock.create_trigger(self._refresh_tool_drawing, 0)
        self.tool_reveal_trigger = Clock.create_trigger(self._reveal_tool_dimension, 0)
        self._tool_reveal = None
        self.chrome_trigger = Clock.create_trigger(self._position_editor_chrome, 0)
        self.store = store
        self.cutter_filter = CutterFilter()
        self.filter_values = {}
        self.page_index = 0
        self.page_size = 30
        self.browse_trigger = Clock.create_trigger(lambda _dt: self._refresh_list(), 0.12)
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
        self.search = self._input("", "Name, vendor, part number or notes")
        self.search.bind(text=lambda *_: self.browse_trigger())
        self.list_card.add_widget(self.search)
        self.browser_controls = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
        self.filter_button = components.Action("Filters", self.open_filters)
        self.sort_choice = components.Choice(text="Name", values=("Name",), size_hint_x=None, width=dp(90))
        self.sort_choice.bind(text=lambda *_: self._refresh_list())
        self.browser_controls.add_widget(self.filter_button)
        self.browser_controls.add_widget(self.sort_choice)
        self.table_button = components.Action("Table…", self.open_table, size_hint_x=None, width=dp(76))
        self.list_card.add_widget(self.browser_controls)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(9))
        self.list_scroll = scroll
        self.list_items = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.list_items.bind(minimum_height=self.list_items.setter("height"))
        scroll.add_widget(self.list_items)
        self.list_card.add_widget(scroll)
        self.new_button = components.Action("+ New profile", self.new)
        self.new_controls = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.new_controls.add_widget(self.new_button)
        self.new_controls.add_widget(self.table_button)
        self.list_card.add_widget(self.new_controls)
        self.compact_controls = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        self.compact_layout = None
        self.body.add_widget(self.list_card)
        self.editor_card = components.Surface(orientation="vertical", padding=dp(14), spacing=dp(8))
        self.editor_heading = components.label("Machine profile", 18, height=28)
        self.editor_card.add_widget(self.editor_heading)
        self.editor_description = self._wrapped_label("")
        self.editor_description.bind(height=self.chrome_trigger)
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
        self.editor_card.bind(size=self.chrome_trigger)
        self.actions.bind(height=self.chrome_trigger)
        self.draft_status.bind(height=self.chrome_trigger)
        self.body.add_widget(self.editor_card)
        self.add_widget(self.body)
        self.body.bind(size=self._reflow)
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
            self.new_controls.clear_widgets()
            if compact:
                self.compact_controls.add_widget(self.search)
                self.compact_controls.add_widget(self.new_button)
                self.compact_controls.add_widget(self.table_button)
                self.list_card.add_widget(self.compact_controls)
                self.list_card.add_widget(self.browser_controls)
                self.list_card.add_widget(self.list_scroll)
            else:
                self.new_controls.add_widget(self.new_button)
                self.new_controls.add_widget(self.table_button)
                for item in (
                    self.list_heading,
                    self.search,
                    self.browser_controls,
                    self.list_scroll,
                    self.new_controls,
                ):
                    self.list_card.add_widget(item)
        self.list_card.size_hint = (1, None) if compact else (None, 1)
        self.list_card.padding = dp(8 if compact else 12)
        if compact:
            self.list_card.height = dp(160)
        else:
            self.list_card.width = min(dp(280), max(dp(210), self.body.width * 0.24))
        self.editor_card.size_hint = (1, 1)
        self.chrome_trigger()

    def _position_editor_chrome(self, *_):
        if self._building or not hasattr(self, "editor_scroll"):
            return
        chrome = [self.editor_heading, self.editor_description]
        if self.tool_drawing_card:
            chrome.append(self.tool_drawing_card)
        # In a narrow library the saved-record list uses part of the body.
        # Budget the editor itself, including pinned actions/status, rather
        # than treating the body's full height as editable space.
        remaining = (
            self.editor_card.height
            - self.editor_card.padding[1]
            - self.editor_card.padding[3]
            - sum(item.height for item in chrome)
            - self.draft_status.height
            - self.actions.height
            - self.editor_card.spacing * (len(chrome) + 2)
        )
        parent = self.form if remaining < dp(180) else self.editor_card
        if all(item.parent is parent for item in chrome):
            return
        for item in chrome:
            if item.parent:
                item.parent.remove_widget(item)
        if parent is self.form:
            for item in reversed(chrome):
                parent.add_widget(item, index=len(parent.children))
        else:
            for item in chrome:
                parent.add_widget(item, index=parent.children.index(self.editor_scroll) + 1)

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

    def _refresh_list(self, reset_page=True):
        self.list_items.clear_widgets()
        if not self.store:
            return
        titles = {"machines": "Saved machines", "tools": "Saved cutters", "toolsets": "Saved ATC toolsets"}
        self.list_heading.text = titles[self.selected_kind]
        records = self.store.data[self.selected_kind]
        tools = self.selected_kind == "tools"
        self.sort_choice.values = ("Name", "Diameter", "Vendor") if tools else ("Name",)
        if not tools and self.sort_choice.text != "Name":
            self.sort_choice.text = "Name"
        self.filter_button.disabled = not tools
        self.table_button.disabled = not tools
        self.matches = browse_profiles(
            records, self.search.text, cutter_filter=self.cutter_filter if tools else None, sort=self.sort_choice.text
        )
        if reset_page:
            self.page_index = 0
            self.list_scroll.scroll_y = 1
        self.page_index = min(self.page_index, max(0, (len(self.matches) - 1) // self.page_size))
        start = self.page_index * self.page_size
        self.filter_button.text = f"{'Filters*' if tools and self.cutter_filter.active else 'Filters' if tools else 'Results'} · {len(self.matches)}/{len(records)}"
        for record in self.matches[start : start + self.page_size]:
            if self.selected_kind == "tools":
                detail = f"Ø {record['diameter']:g} · shank {record['shank_diameter']:g} mm · T{record['number']}"
                asset = (
                    "CAD reference"
                    if record.get("geometry_path")
                    else "Drawing reference"
                    if record.get("drawing_path")
                    else "Nominal dimensions"
                )
                detail += f"\n{record.get('vendor') or 'No vendor'} · {record.get('product_id') or asset}"
            elif self.selected_kind == "machines":
                detail = f"{record['model']} · {record['host'] or 'No address'}"
            else:
                detail = f"{len(record['slots'])} of 6 slots assigned"
            title = f"{record['name']}\n{detail}"
            button = self.components.Action(
                title, lambda r=record: (self._edit(r), self._refresh_list(False)), height=dp(72 if tools else 54)
            )
            if record["id"] == self.selected_id:
                button.base_color = (0.14, 0.27, 0.29, 1)
                button._paint()
            button.halign = "left"
            button.valign = "middle"
            button.bind(width=lambda obj, width: setattr(obj, "text_size", (width - dp(16), None)))
            button.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(54), size[1] + dp(16))))
            button.text_size = (button.width - dp(16), None)
            self.list_items.add_widget(button)
        if len(self.matches) > self.page_size:
            navigation = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
            navigation.add_widget(
                self.components.Action("Previous", lambda: self._browse_page(-1), disabled=self.page_index == 0)
            )
            navigation.add_widget(
                self.components.label(
                    f"{self.page_index + 1}/{(len(self.matches) - 1) // self.page_size + 1}", 12, height=34
                )
            )
            navigation.add_widget(
                self.components.Action(
                    "Next", lambda: self._browse_page(1), disabled=start + self.page_size >= len(self.matches)
                )
            )
            self.list_items.add_widget(navigation)
        if not self.list_items.children:
            self.list_items.add_widget(
                self.components.label(
                    "No profiles match." if records else "Create your first profile.",
                    12,
                    color=self.components.MUTED,
                    height=44,
                )
            )

    def _browse_page(self, delta):
        self.page_index += delta
        self._refresh_list(False)
        self.list_scroll.scroll_y = 1

    def open_filters(self):
        if self.selected_kind != "tools":
            return
        from carveracontroller.desktop_library_filters import CutterFilterDialog

        self.filter_popup = CutterFilterDialog(self)
        self.filter_popup.open()

    def open_table(self):
        if self.selected_kind != "tools" or not self.store:
            return
        from carveracontroller.desktop_cutter_table import CutterTableDialog

        self._stash_draft()
        self.table_popup = CutterTableDialog(self)
        self.table_popup.open()

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
        self.geometry_trigger()

    def revert(self):
        """Discard this editor's draft without changing stored or active metadata."""
        self.drafts.pop(self._editing_key, None)
        self._building = True
        for key, value in self._baseline.items():
            self.fields[key].text = value
        self._building = False
        self._position_editor_chrome()
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
            "thread_tip_offset",
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
            if key in {"number", "port", "thread_teeth"}
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
                optional=(key in dimension_keys or key == "thread_teeth")
                and key not in {"diameter", "shank_diameter", "vise_x", "vise_y", "vise_z", "vise_jaw_offset"},
                integer=key in {"number", "port", "thread_teeth"},
                minimum=-1000 if key.startswith("vise_") else 1 if key in {"number", "port", "thread_teeth"} else 0,
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

    def _focus_tool_dimension(self, key, focused):
        if focused:
            self.tool_dimension = key
            self.geometry_trigger()

    def _select_drawn_tool_dimension(self, drawing, key):
        if drawing is not self.tool_drawing or drawing.disposed or drawing.parent is None:
            return
        if self.selected_kind != "tools" or key not in self.fields:
            return
        for name, control in self.fields.items():
            if hasattr(control, "focus"):
                control.focus = name == key
        self.tool_dimension = key
        self._tool_reveal = (drawing, key, self.fields[key])
        self.geometry_trigger()

    def _reveal_tool_dimension(self, *_):
        pending, self._tool_reveal = self._tool_reveal, None
        if pending is None:
            return
        drawing, key, field = pending
        if (
            drawing is self.tool_drawing
            and not drawing.disposed
            and drawing.parent is not None
            and self.fields.get(key) is field
            and field.focus
            and self.tool_dimension == key
        ):
            self.editor_scroll.scroll_to(field.parent, animate=False)

    def _fit_tool_drawing_card(self, *_):
        if self.tool_drawing_card:
            self.tool_drawing_card.height = (
                dp(210)
                if self.tool_drawing and self.tool_drawing.parent
                else max(dp(48), self.tool_drawing_status.height + dp(12))
            )
            self.chrome_trigger()

    def _refresh_tool_drawing(self, *_):
        if self._building or self.selected_kind != "tools" or not self.tool_drawing_card:
            return
        from carveracontroller.desktop_tool_drawing import ToolDrawing
        from carveracontroller.machine.desktop_profiles import to_tool_definition

        try:
            record = self._record()
            record["name"] = record["name"] or "Draft cutter"
            definition = to_tool_definition(record)
            if self.tool_drawing is None:
                self.tool_drawing = ToolDrawing(definition, compact=True)
                self.tool_drawing.bind(on_dimension_selected=self._select_drawn_tool_dimension)
            else:
                self.tool_drawing.update_definition(definition)
            self.tool_drawing.selected_dimension = self.tool_dimension
            if not self.tool_drawing.parent:
                self.tool_drawing_card.add_widget(self.tool_drawing)
            key = self.tool_dimension
            value = getattr(definition, key, None) if key else None
            dimension = key.replace("_", " ").capitalize() if key else "Select a geometry field"
            state = "Unsaved" if self._raw_fields() != self._baseline else "Saved"
            self.tool_drawing_status.text = (
                f"{dimension}: {value:g} mm · {state.lower()} nominal schematic"
                if value is not None
                else f"{dimension} · nominal schematic; unspecified dimensions use display envelopes"
            )
            if key in ("corner_radius", "thread_pitch"):
                self.tool_drawing_status.text += " · cutting region highlighted"
            self.tool_drawing_status.color = self.components.MUTED
        except ValueError as exc:
            if self.tool_drawing and self.tool_drawing.parent:
                self.tool_drawing_card.remove_widget(self.tool_drawing)
            self.tool_drawing_status.text = f"Draft geometry unavailable: {exc}"
            self.tool_drawing_status.color = self.components.DANGER
        self._fit_tool_drawing_card()
        self._position_editor_chrome()
        if self._tool_reveal is not None:
            self.tool_reveal_trigger()

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
        if self.tool_drawing:
            self.tool_drawing.dispose()
        if self.tool_drawing_card and self.tool_drawing_card.parent:
            self.tool_drawing_card.parent.remove_widget(self.tool_drawing_card)
        self.tool_drawing = self.tool_drawing_card = None
        self.tool_dimension = ""
        for item in (self.editor_heading, self.editor_description):
            if item.parent is self.form:
                self.form.remove_widget(item)
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
                ("thread_teeth", "Complete teeth · multi-form only"),
                ("thread_tip_offset", "Tip to lowest tooth datum · mm"),
                ("stickout", "Tip to collet face · mm"),
            ):
                field = self._row(
                    title,
                    key,
                    record.get(key, ""),
                    hint="Optional" if key not in ("diameter", "shank_diameter") else "Required",
                )
                if key != "thread_teeth":
                    field.bind(focus=lambda _field, focused, key=key: self._focus_tool_dimension(key, focused))
            self.tool_drawing_card = self.components.Surface(
                orientation="vertical", size_hint_y=None, height=dp(210), padding=dp(6), spacing=dp(4)
            )
            self.tool_drawing_status = self._wrapped_label("Select a geometry field to inspect its dimension")
            self.tool_drawing_status.bind(height=self._fit_tool_drawing_card)
            self.tool_drawing_card.add_widget(self.tool_drawing_status)
            self.editor_card.add_widget(
                self.tool_drawing_card, index=self.editor_card.children.index(self.editor_scroll) + 1
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
        self._position_editor_chrome()
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

                def prepared(success, error):
                    if self.selected_kind == "machines" and self.selected_id == record["id"]:
                        self.status.text = (
                            f"Loaded {record['name']} into the workspace. No machine commands sent."
                            if success
                            else "Profile not loaded: " + str(error)
                        )

                if not self.workspace.request_machine_profile(record, prepared):
                    self.status.text = "Workspace closed; profile saved but not loaded."
                    return
                self.status.text = f"Preparing {record['name']}… Current workspace retained."
                return
            if self.selected_kind == "tools":
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
