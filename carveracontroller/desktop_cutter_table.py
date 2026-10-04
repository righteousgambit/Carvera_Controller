"""Virtualized cutter comparison, keyboard selection and reviewed spreadsheet edits."""

import threading

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    MUTED,
    PANEL,
    RAISED,
    Action,
    AdaptiveGrid,
    DesktopFocus,
    DesktopScrollView,
    Field,
    label,
)
from carveracontroller.machine.cutter_table import (
    COLUMNS,
    DIMENSIONS,
    TableSelection,
    cell_text,
    export_tsv,
    review_tsv,
)
from carveracontroller.machine.desktop_profiles import ProfileError
from carveracontroller.machine.library_browser import browse_profiles


class ColumnGrip(Widget):
    """Dedicated drag target keeps header sort clicks separate from resizing."""

    def __init__(self, table, column, **kwargs):
        super().__init__(size_hint_x=None, width=dp(12), **kwargs)
        self.table, self.column = table, column
        with self.canvas:
            Color(*MUTED[:3], 0.5)
            self.line = Rectangle()
        self.bind(pos=self._paint, size=self._paint)

    def _paint(self, *_):
        self.line.pos = (self.center_x - dp(1), self.y + dp(8))
        self.line.size = (dp(2), max(0, self.height - dp(16)))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or getattr(touch, "is_mouse_scrolling", False):
            return False
        self.start = (touch.x, self.table.widths[self.column])
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.table.resize_column(self.column, self.start[1] + touch.x - self.start[0])
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return False


class CutterHeaderScroll(DesktopScrollView):
    """Capture divider presses before ScrollView negotiates a scroll gesture."""

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not self.disabled and not getattr(touch, "is_mouse_scrolling", False):
            touch.push()
            try:
                touch.apply_transform_2d(self.to_local)
                for cell in self._viewport.children:
                    for child in cell.children:
                        if isinstance(child, ColumnGrip) and child.on_touch_down(touch):
                            return True
            finally:
                touch.pop()
        return super().on_touch_down(touch)


class CutterTableRow(RecycleDataViewBehavior, BoxLayout):
    owner = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(spacing=0, **kwargs)
        self.cells = []
        with self.canvas.before:
            self.fill = Color(*PANEL)
            self.background = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._paint, size=self._paint)

    def _paint(self, *_):
        self.background.pos, self.background.size = self.pos, self.size

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        result = super().refresh_view_attrs(rv, index, data)
        self.identity = data["identity"]
        if not self.cells:
            for _key, _title, _width in COLUMNS:
                item = label("", 12, height=38, size_hint_x=None, shorten=True, shorten_from="right")
                item.padding = (dp(8), 0)
                self.cells.append(item)
                self.add_widget(item)
        for i, (item, text) in enumerate(zip(self.cells, data["texts"])):
            item.text = text or "—"
            item.width = self.owner.widths[i]
        self.fill.rgba = (0.14, 0.27, 0.29, 1) if data["selected"] else PANEL if index % 2 else RAISED
        return result

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not getattr(touch, "is_mouse_scrolling", False):
            # ScrollView first negotiates gestures; clicks are delivered only
            # after it decides this was not a scroll drag.
            mods = Window.modifiers
            self.owner.select(self.identity, toggle=bool({"ctrl", "meta", "super"} & set(mods)), extend="shift" in mods)
            self.owner.grid.focus = True
            return True
        return super().on_touch_down(touch)


class CutterGrid(DesktopFocus, FocusBehavior, RecycleView):
    def __init__(self, owner, **kwargs):
        self.owner = owner
        super().__init__(bar_width=dp(9), scroll_type=["content", "bars"], **kwargs)
        self.bind(focus=self._desktop_focus_changed)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        key, mods = keycode[1], set(modifiers)
        command = bool({"ctrl", "meta", "super"} & mods)
        if command and key == "a":
            self.owner.select_all()
            return True
        if command and key == "c":
            self.owner.copy_selected()
            return True
        if command and key == "v":
            self.owner.open_paste(Clipboard.paste())
            return True
        if key in ("up", "down", "home", "end", "pageup", "pagedown"):
            self.owner.move_selection(key, extend="shift" in mods)
            return True
        if key in ("enter", "numpadenter"):
            self.owner.edit_selected()
            return True
        if key == "escape":
            self.owner.clear_selection()
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class CutterTableDialog(Popup):
    """A retained table snapshot; selection/filtering never applies a physical tool."""

    def __init__(self, library, **kwargs):
        self.library = library
        self.reloading = False
        self.selection = TableSelection()
        self.widths = [dp(width) for _, _, width in COLUMNS]
        self.sort_key, self.descending = "name", False
        self.records = library.store.data["tools"]
        self.generation = library.store.generation
        body = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        super().__init__(title="Compare saved cutters", content=body, size_hint=(None, None), **kwargs)
        self._fit_window()
        self.bind(on_pre_open=lambda *_: Window.bind(size=self._fit_window))
        self.bind(on_dismiss=self._dispose)
        toolbar = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        self.search = Field(hint_text="Name, vendor, part number or notes", text=library.search.text)
        self.search_trigger = Clock.create_trigger(self._refresh, 0.12)
        self.search.bind(text=lambda *_: self.search_trigger())
        toolbar.add_widget(self.search)
        self.filter_action = Action("Filters…", self.open_filters, size_hint_x=None, width=dp(95))
        toolbar.add_widget(self.filter_action)
        self.reload_action = Action("Reload", self.reload_records, size_hint_x=None, width=dp(75))
        toolbar.add_widget(self.reload_action)
        toolbar.add_widget(Action("Select results", self.select_all, size_hint_x=None, width=dp(125)))
        toolbar.add_widget(Action("Clear", self.clear_selection, size_hint_x=None, width=dp(70)))
        body.add_widget(toolbar)
        self.hint = label(
            "Dimensions in mm · click a header to sort, drag its divider to resize · Shift ranges, Cmd/Ctrl toggles",
            12,
            color=MUTED,
            height=44,
        )
        body.add_widget(self.hint)
        self.header_scroll = CutterHeaderScroll(
            size_hint_y=None, height=dp(36), do_scroll_y=False, bar_width=0, scroll_type=["bars"]
        )
        self.header = BoxLayout(size_hint=(None, 1), spacing=0, width=sum(self.widths))
        self.header_buttons, self.header_cells = [], []
        for i, (_key, title, _width) in enumerate(COLUMNS):
            cell = BoxLayout(size_hint_x=None, width=self.widths[i])
            button = Action(title, lambda i=i: self.sort_column(i), height=dp(36))
            cell.add_widget(button)
            cell.add_widget(ColumnGrip(self, i))
            self.header_buttons.append(button)
            self.header_cells.append(cell)
            self.header.add_widget(cell)
        self.header_scroll.add_widget(self.header)
        body.add_widget(self.header_scroll)
        self.grid = CutterGrid(self)
        self.layout = RecycleBoxLayout(
            default_size=(None, dp(38)),
            default_size_hint=(1, None),
            size_hint=(None, None),
            orientation="vertical",
            width=sum(self.widths),
        )
        self.layout.bind(minimum_height=self.layout.setter("height"))
        self.grid.add_widget(self.layout)
        self.grid.viewclass = CutterTableRow
        self.grid.bind(scroll_x=lambda _, value: setattr(self.header_scroll, "scroll_x", value))
        self.header_scroll.bind(scroll_x=lambda _, value: setattr(self.grid, "scroll_x", value))
        body.add_widget(self.grid)
        self.status = label("", 12, height=54)
        body.add_widget(self.status)
        actions = AdaptiveGrid(max_cols=4, min_width=145, row_height=36, spacing=dp(8))
        self.copy_action = Action("Copy selected TSV", self.copy_selected)
        self.edit_action = Action("Edit selected cutter", self.edit_selected, primary=True)
        actions.add_widget(self.copy_action)
        actions.add_widget(Action("Paste & review…", lambda: self.open_paste(Clipboard.paste())))
        actions.add_widget(self.edit_action)
        actions.add_widget(Action("Close", self.dismiss))
        body.add_widget(actions)
        self._refresh()

    def _fit_window(self, *_):
        self.size = (min(dp(1500), Window.width * 0.94), min(dp(880), Window.height * 0.91))

    def _dispose(self, *_):
        Window.unbind(size=self._fit_window)
        self.search_trigger.cancel()
        self.grid.focus = False
        if getattr(self, "paste_popup", None):
            self.paste_popup.dismiss()

    def _refresh(self, *_):
        matches = browse_profiles(self.records, self.search.text, cutter_filter=self.library.cutter_filter)

        def sort_value(item):
            value = item.get(self.sort_key)
            return (value is None, value.casefold() if isinstance(value, str) else value or 0, item["id"])

        self.matches = sorted(matches, key=sort_value, reverse=self.descending)
        self.order = [item["id"] for item in self.matches]
        self.selection.reconcile({item["id"] for item in self.records})
        self.grid.data = [
            {
                "owner": self,
                "identity": item["id"],
                "texts": [cell_text(item, key) for key, _, _ in COLUMNS],
                "selected": item["id"] in self.selection.ids,
            }
            for item in self.matches
        ]
        for (key, title, _), button in zip(COLUMNS, self.header_buttons):
            button.text = title + (" v" if self.descending else " ^") if key == self.sort_key else title
        self._status()

    def _status(self, message=""):
        self.filter_action.text = "Filters*…" if self.library.cutter_filter.active else "Filters…"
        visible = len(self.selection.ids & set(self.order))
        hidden = len(self.selection.ids) - visible
        counts = f"{len(self.matches)}/{len(self.records)} results · {visible} selected here" + (
            f" · {hidden} selected outside filter" if hidden else ""
        )
        self.status.text = (
            message
            or counts
            + "\nSaved nominal geometry; physical assemblies, measured offsets and active previews remain separate."
        )
        self.copy_action.disabled = not self.selection.ids
        self.edit_action.disabled = self.reloading or len(self.selection.ids) != 1

    def resize_column(self, index, width):
        self.widths[index] = min(dp(500), max(dp(70), width))
        self.header_cells[index].width = self.widths[index]
        self.header.width = self.layout.width = sum(self.widths)
        self.grid.refresh_from_data()

    def sort_column(self, index):
        key = COLUMNS[index][0]
        self.descending = not self.descending if key == self.sort_key else False
        self.sort_key = key
        self._refresh()

    def select(self, identity, toggle=False, extend=False):
        self.selection.select(identity, self.order, toggle=toggle, extend=extend)
        for item in self.grid.data:
            item["selected"] = item["identity"] in self.selection.ids
        self.grid.refresh_from_data()
        self._status()

    def select_all(self):
        self.selection.ids.update(self.order)
        self._refresh()

    def clear_selection(self):
        self.selection = TableSelection()
        self._refresh()

    def move_selection(self, key, extend=False):
        if not self.order:
            return
        current = self.order.index(self.selection.current) if self.selection.current in self.order else -1
        step = max(1, int(self.grid.height / dp(38)) - 1)
        if key == "home":
            index = 0
        elif key == "end":
            index = len(self.order) - 1
        else:
            index = max(
                0, min(len(self.order) - 1, current + {"up": -1, "down": 1, "pageup": -step, "pagedown": step}[key])
            )
        self.select(self.order[index], extend=extend)
        overflow = max(0, self.layout.height - self.grid.height)
        if overflow:
            top = index * dp(38)
            offset = (1 - self.grid.scroll_y) * overflow
            if top < offset or top + dp(38) > offset + self.grid.height:
                self.grid.scroll_y = 1 - max(0, min(overflow, top - self.grid.height / 2)) / overflow

    def copy_selected(self):
        selected = [item for item in self.matches if item["id"] in self.selection.ids]
        selected += [item for item in self.records if item["id"] in self.selection.ids and item["id"] not in self.order]
        if selected:
            Clipboard.copy(export_tsv(selected))
            self._status(
                f"Copied {len(selected)} saved cutters as TSV, including stable IDs. Paste edited values to review local changes."
            )

    def edit_selected(self):
        if not self.reloading and len(self.selection.ids) == 1:
            identity = next(iter(self.selection.ids))
            self.library.select_record("tools", identity)
            self.dismiss()

    def open_paste(self, text=""):
        self.grid.focus = False
        self.paste_popup = CutterPasteDialog(self, text)
        self.paste_popup.open()

    def open_filters(self):
        self.grid.focus = False
        self.library.open_filters()
        self.library.filter_popup.bind(on_dismiss=lambda *_: self._refresh())

    def reload_records(self):
        if self.reloading:
            return
        self.reloading = True
        self.reload_action.disabled = self.edit_action.disabled = True
        self._status("Reloading saved library from disk… Unfinished editor drafts will be retained.")
        self.edit_action.disabled = True

        def finish(snapshot, error):
            self.reloading = False
            self.reload_action.disabled = False
            if not self._is_open:
                return
            if error:
                self._status(error + ". Existing table retained.")
                return
            self.generation, data = snapshot
            self.records = data["tools"]
            self.library.refresh()
            self._refresh()

        def run():
            snapshot, error = None, None
            try:
                snapshot = self.library.store.reload()
            except (ValueError, OSError) as exc:
                error = str(exc)
            Clock.schedule_once(lambda _dt: finish(snapshot, error), 0)

        threading.Thread(target=run, daemon=True).start()


class CutterPasteDialog(Popup):
    def __init__(self, table, text, **kwargs):
        self.table = table
        self.changes = ()
        self.review_token = 0
        self.saving = False
        self.review_page = 0
        body = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        super().__init__(title="Review spreadsheet changes", content=body, size_hint=(None, None), **kwargs)
        self._fit_window()
        self.bind(on_pre_open=lambda *_: Window.bind(size=self._fit_window))
        self.bind(on_dismiss=self._dispose)
        body.add_widget(
            label(
                "Paste tab-separated rows with ID and editable headers. Dimensions accept mm or 1/4 in. Blank optional dimensions clear them. Review the changes before saving local profiles.",
                12,
                color=MUTED,
                height=64,
            )
        )
        self.input = Field(text=text, multiline=True, size_hint_y=0.4, height=dp(120))
        body.add_widget(self.input)
        self.review_scroll = DesktopScrollView(do_scroll_x=False)
        self.review_text = label("", 12, height=100)
        self.review_text.valign = "top"
        self.review_text.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        self.review_text.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(100), size[1] + dp(12))))
        self.review_scroll.add_widget(self.review_text)
        body.add_widget(self.review_scroll)
        self.pages = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        self.previous_action = Action("Previous", lambda: self._page(-1), height=dp(32))
        self.page_label = label("", 12, height=32)
        self.next_action = Action("Next", lambda: self._page(1), height=dp(32))
        for item in (self.previous_action, self.page_label, self.next_action):
            self.pages.add_widget(item)
        body.add_widget(self.pages)
        self.message = label(
            "Nothing has been saved. Copy selected rows from the table to obtain IDs and headers.", 12, height=64
        )
        body.add_widget(self.message)
        actions = AdaptiveGrid(max_cols=3, min_width=125, row_height=36, spacing=dp(8))
        self.review_action = Action("Review changes", self.review)
        self.save_action = Action("Save reviewed locally", self.save, primary=True, disabled=True)
        self.cancel_action = Action("Cancel", self.dismiss)
        for item in (self.cancel_action, self.review_action, self.save_action):
            actions.add_widget(item)
        body.add_widget(actions)
        self.input.bind(text=self._invalidate)
        self._show_page()

    def _fit_window(self, *_):
        self.size = (min(dp(1000), Window.width * 0.90), min(dp(780), Window.height * 0.88))

    def _dispose(self, *_):
        Window.unbind(size=self._fit_window)
        self.review_token += 1

    def _invalidate(self, *_):
        self.review_token += 1
        self.changes = ()
        self.review_page = 0
        self.save_action.disabled = True
        self.review_action.disabled = False
        self.message.text = "Paste changed. Review it again before saving."
        self._show_page()

    def review(self):
        self.changes = ()
        self.save_action.disabled = True
        self.review_text.text = ""
        store = self.table.library.store
        self.review_token += 1
        token, text = self.review_token, self.input.text
        self.message.text = "Validating cutter rows… Nothing saved."
        self.review_action.disabled = True

        def finish(changes, generation, error):
            if token != self.review_token or not self._is_open:
                return
            self.review_action.disabled = False
            if error:
                self.message.text = error + ". Nothing saved."
                return
            self.changes, self.review_generation = changes, generation
            self.review_page = 0
            self._show_page()
            self.table.library._stash_draft()
            conflicts = [
                c.before["name"] for c in self.changes if ("tools", c.before["id"]) in self.table.library.drafts
            ]
            self.save_action.disabled = not self.changes or bool(conflicts)
            self.message.text = (
                "Unfinished editor drafts conflict: "
                + ", ".join(conflicts[:5])
                + ". Save or revert those drafts before reviewing again."
                if conflicts
                else f"{len(self.changes)} cutters will change locally. Active previews, physical tools and measured offsets will remain as they are."
            )

        def run():
            changes, generation, error = (), None, None
            try:
                generation, data = store.snapshot()
                changes = review_tsv(text, data["tools"])
            except (ValueError, OSError) as exc:
                error = str(exc)
            Clock.schedule_once(lambda _dt: finish(changes, generation, error), 0)

        threading.Thread(target=run, daemon=True).start()

    def _show_page(self):
        lines = []
        for change in self.changes[self.review_page * 30 : (self.review_page + 1) * 30]:
            lines.append(f"{change.before['name']} · {change.before['id']}")
            for key in change.fields:
                title = next(title for field, title, _ in COLUMNS if field == key)
                unit = " mm" if key in DIMENSIONS else ""
                lines.append(
                    f"  {title}: {cell_text(change.before, key) or 'unspecified'} -> {cell_text(change.after, key) or 'unspecified'}{unit}"
                )
            lines.append("")
        self.review_text.text = "\n".join(lines) or "No differences from the saved library."
        pages = max(1, (len(self.changes) + 29) // 30)
        self.page_label.text = f"Review {self.review_page + 1}/{pages} · {len(self.changes)} changed cutters"
        self.previous_action.disabled = self.review_page == 0
        self.next_action.disabled = self.review_page + 1 >= pages
        self.review_scroll.scroll_y = 1

    def _page(self, delta):
        pages = max(1, (len(self.changes) + 29) // 30)
        self.review_page = max(0, min(pages - 1, self.review_page + delta))
        self._show_page()

    def dismiss(self, *args, **kwargs):
        if not self.saving:
            return super().dismiss(*args, **kwargs)

    def save(self):
        if not self.changes or self.save_action.disabled:
            return
        library = self.table.library
        library._stash_draft()
        if any(("tools", c.before["id"]) in library.drafts for c in self.changes):
            self.message.text = "An editor draft changed after review. Resolve it and review again."
            self.save_action.disabled = True
            return
        updates, generation = [c.after for c in self.changes], self.review_generation
        self.saving = True
        self.input.disabled = self.cancel_action.disabled = self.review_action.disabled = self.save_action.disabled = (
            True
        )
        self.message.text = f"Saving {len(updates)} reviewed cutters atomically…"

        def finish(saved, error):
            self.saving = False
            self.input.disabled = self.cancel_action.disabled = self.review_action.disabled = False
            if error:
                self.message.text = error + ". Nothing saved by this review."
                return
            self.table.records = library.store.data["tools"]
            self.table.generation = library.store.generation
            self.table._refresh()
            library.refresh()
            self.table._status(
                f"Saved {len(saved)} reviewed cutters locally. Active previews, physical tools and measured offsets were not applied."
            )
            self.dismiss()

        def run():
            saved, error = [], None
            try:
                saved = library.store.update_tools(updates, generation)
            except (ValueError, OSError) as exc:
                error = str(exc)
            Clock.schedule_once(lambda _dt: finish(saved, error), 0)

        threading.Thread(target=run, daemon=True).start()
