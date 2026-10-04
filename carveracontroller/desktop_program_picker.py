"""Desktop program browser; existing controller owns all remote transfers.

Local previews never upload. Remote previews download through the existing
controller session. Upload is a separate explicit action with the controller's
existing overwrite confirmation.
"""

import datetime
import os
import posixpath
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PROGRAM_EXTENSIONS = frozenset({".cnc", ".nc", ".gcode", ".tap", ".ngc"})


@dataclass(frozen=True)
class ProgramEntry:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified: float = 0


def filter_entries(entries, query=""):
    """Keep navigable folders and supported programs, folders first."""
    query = query.strip().casefold()
    return sorted(
        (
            entry
            for entry in entries
            if not entry.name.startswith(".")
            and (entry.is_dir or Path(entry.name).suffix.casefold() in PROGRAM_EXTENSIONS)
            and query in entry.name.casefold()
        ),
        key=lambda entry: (not entry.is_dir, entry.name.casefold(), entry.name),
    )


def list_program_directory(directory, query=""):
    """One-level local listing. Permission/missing-path errors remain explicit."""
    entries = []
    with os.scandir(Path(directory).expanduser()) as children:
        for child in children:
            try:
                stat = child.stat()
                entries.append(ProgramEntry(child.name, child.path, child.is_dir(), stat.st_size, stat.st_mtime))
            except OSError:
                # An individual item may disappear while its folder is being read.
                continue
    return filter_entries(entries, query)


def remote_entries(records, query=""):
    return filter_entries(
        [
            ProgramEntry(
                str(item["name"]),
                str(item["path"]),
                bool(item["is_dir"]),
                int(item.get("size", 0)),
                float(item.get("date", 0)),
            )
            for item in records
        ],
        query,
    )


def read_program_excerpt(path, byte_limit=16384, line_limit=24):
    """Bounded text inspection; no parsing, execution, or controller access."""
    with open(path, "rb") as source:
        content = source.read(byte_limit + 1)
    lines = content[:byte_limit].decode("utf-8", errors="replace").splitlines()
    excerpt = "\n".join(lines[:line_limit])
    if len(content) > byte_limit or len(lines) > line_limit:
        excerpt += "\n…"
    return excerpt or "Empty program"


def human_size(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class ProgramBrowser:
    """Reusable popup owned by DesktopWorkspace; widgets load only on demand."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.root = workspace.machine
        self.location = "local"
        old_path = getattr(self.root.file_popup.local_rv, "curr_dir", "")
        self.local_path = str(Path(old_path).expanduser()) if old_path and Path(old_path).is_dir() else str(Path.home())
        self.remote_path = str(getattr(self.root.file_popup.remote_rv, "curr_dir", "/sd/gcodes"))
        self.entries = []
        self.selected = None
        self.popup = None
        self._poll = None
        self._loading_remote = False
        self._pending_upload = None
        self._started = 0
        self._inspection_generation = 0
        self.inspection = None

    def _build(self):
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.modalview import ModalView
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput

        from carveracontroller.desktop_components import (
            BG,
            MUTED,
            TEXT,
            Action,
            AdaptiveGrid,
            DesktopScrollView,
            Field,
            Surface,
            label,
        )

        self.popup = ModalView(
            size_hint=(0.94, 0.88),
            auto_dismiss=False,
            background="",
            background_color=(0, 0, 0, 0),
            overlay_color=(0, 0, 0, 0.65),
        )
        panel = Surface(orientation="vertical", padding=dp(18), spacing=dp(12))
        header = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(10))
        header.add_widget(label("Choose a program", size=21, height=36))
        header.add_widget(Action("Close", self.dismiss, size_hint_x=None, width=dp(72), height=dp(34)))
        panel.add_widget(header)
        panel.add_widget(
            label("Inspect toolpaths locally or select a program already on your machine.", color=MUTED, height=24)
        )
        places = AdaptiveGrid(max_cols=4, min_width=130, row_height=34, spacing=dp(6))
        self.places = places
        self.local_button = Action("This computer", lambda: self.set_location("local"), height=34)
        self.remote_button = Action("Machine files", lambda: self.set_location("remote"), height=34)
        places.add_widget(self.local_button)
        places.add_widget(self.remote_button)
        places.add_widget(Action("Home", lambda: self.navigate(str(Path.home()), local=True), height=34))
        places.add_widget(
            Action("Downloads", lambda: self.navigate(str(Path.home() / "Downloads"), local=True), height=34)
        )
        panel.add_widget(places)
        body = BoxLayout(spacing=dp(14))
        self.body = body
        center = BoxLayout(orientation="vertical", spacing=dp(8))
        navigation = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        navigation.add_widget(Action("Up", self.up, size_hint_x=None, width=dp(42), height=dp(34)))
        self.path_field = Field(
            height=dp(34),
            multiline=False,
            font_size=dp(12),
            background_normal="",
            background_active="",
            background_color=BG,
            foreground_color=TEXT,
            cursor_color=TEXT,
            padding=[dp(9), dp(8)],
        )
        self.path_field.bind(on_text_validate=lambda *_: self.navigate(self.path_field.text))
        navigation.add_widget(self.path_field)
        navigation.add_widget(Action("Refresh", self.refresh, size_hint_x=None, width=dp(74), height=dp(34)))
        center.add_widget(navigation)
        self.search = Field(
            hint_text="Search this folder",
            multiline=False,
            size_hint_y=None,
            height=dp(36),
            font_size=dp(13),
            background_normal="",
            background_active="",
            background_color=BG,
            foreground_color=TEXT,
            cursor_color=TEXT,
            padding=[dp(10), dp(9)],
        )
        self.search.bind(text=lambda *_: self._render_rows())
        center.add_widget(self.search)
        self.status = label("", size=12, color=MUTED, height=28)
        center.add_widget(self.status)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(5))
        self.rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll.add_widget(self.rows)
        center.add_widget(scroll)
        body.add_widget(center)
        details = Surface(color=BG, orientation="vertical", size_hint_x=0.45, padding=dp(12), spacing=dp(8))
        self.details = details
        detail_scroll = DesktopScrollView(do_scroll_x=False)
        self.detail_scroll = detail_scroll
        detail_content = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        detail_content.bind(minimum_height=detail_content.setter("height"))
        detail_scroll.add_widget(detail_content)
        details.add_widget(detail_scroll)
        self.detail_content = detail_content
        self.detail_title = label("Program details", size=16, height=42, shorten=True)
        self.metadata = label("Select a program to inspect it.", size=12, color=MUTED, height=56)
        detail_content.add_widget(self.detail_title)
        detail_content.add_widget(self.metadata)
        from carveracontroller.desktop_program_thumbnail import ProgramThumbnail

        self.thumbnail = ProgramThumbnail()
        detail_content.add_widget(self.thumbnail)
        self.inspection_note = label("XY preview · resolved motion only", size=10, color=MUTED, height=26, shorten=True)
        detail_content.add_widget(self.inspection_note)
        class InspectionText(TextInput):
            """Selectable source text with one surrounding scroll owner."""

            def on_touch_down(self, touch):
                if getattr(touch, "button", "") in ("scrollup", "scrolldown"):
                    return False
                return super().on_touch_down(touch)

        self.excerpt = InspectionText(
            readonly=True,
            size_hint_y=None,
            height=dp(120),
            font_size=dp(11),
            background_normal="",
            background_active="",
            background_color=BG,
            foreground_color=MUTED,
            padding=[0, dp(8)],
        )
        self.excerpt.bind(minimum_height=lambda widget, value: setattr(widget, "height", max(dp(120), value)))
        detail_content.add_widget(self.excerpt)
        body.add_widget(details)
        panel.add_widget(body)
        footer = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        self.destination = label("Local preview does not transfer a file.", size=12, color=MUTED, height=40)
        footer.add_widget(self.destination)
        self.upload_button = Action("Upload to machine", self.upload, size_hint_x=None, width=dp(158))
        self.preview_button = Action("Preview locally", self.preview, primary=True, size_hint_x=None, width=dp(148))
        footer.add_widget(self.upload_button)
        footer.add_widget(self.preview_button)
        panel.add_widget(footer)
        self.popup.add_widget(panel)
        self.popup.bind(on_dismiss=lambda *_: self._stop_polling())
        # Limit reading width on large desktop displays while remaining usable in smaller windows.
        from kivy.core.window import Window

        self.popup.size_hint_x = None
        self.popup.width = min(dp(1000), Window.width * 0.94)
        Window.bind(size=self._resize)
        self._resize(Window, Window.size)

    def _resize(self, _window, size):
        from kivy.metrics import dp

        if self.popup:
            self.popup.width = min(dp(1000), size[0] * 0.94)
            compact = self.popup.width < dp(660)
            self.places.max_cols = 2 if compact else 4
            self.places._reflow()
            self.body.orientation = "vertical" if compact else "horizontal"
            self.details.size_hint_x = 1 if compact else 0.45
            self.details.size_hint_y = 0.8 if compact else 1

    def open(self):
        if self.popup is None:
            self._build()
        self.popup.open()
        self.refresh()

    def dismiss(self):
        if self.popup:
            self.popup.dismiss()

    def _stop_polling(self):
        self._loading_remote = False
        self._inspection_generation += 1
        if self._poll:
            self._poll.cancel()
            self._poll = None
        self._pending_upload = None

    def _busy(self):
        controller = self.root.controller
        return bool(getattr(controller, "loadNUM", 0) or getattr(controller, "sendNUM", 0))

    def _remote_allowed(self):
        return bool(self.workspace.connected) and not self._busy()

    def set_location(self, location):
        self._stop_polling()
        self.location = location
        self.search.text = ""
        self.refresh()

    def navigate(self, path, local=False):
        if local:
            self.location = "local"
        self._stop_polling()
        if self.location == "local":
            self.local_path = str(Path(path).expanduser().absolute())
        else:
            normalized = posixpath.normpath(path.replace("\\", "/"))
            if normalized != "/sd" and not normalized.startswith("/sd/"):
                self.status.text = "Choose a folder under /sd."
                return
            self.remote_path = normalized
        self.search.text = ""
        self.refresh()

    def up(self):
        path = str(Path(self.local_path).parent) if self.location == "local" else posixpath.dirname(self.remote_path)
        if self.location == "remote" and self.remote_path == "/sd":
            return
        self.navigate(path)

    def refresh(self):
        self._stop_polling()
        self._loading_remote = False
        self.selected = None
        self.detail_title.text = "Program details"
        self.metadata.text = "Select a program to inspect it."
        self.excerpt.text = ""
        self.inspection = None
        self.thumbnail.set_segments(())
        self.inspection_note.text = "XY preview · resolved motion only"
        self.detail_scroll.scroll_y = 1
        self.entries = []
        self.path_field.text = self.local_path if self.location == "local" else self.remote_path
        self._render_rows()
        if self.location == "local":
            try:
                self.entries = list_program_directory(self.local_path)
                self.status.text = f"{len(self.entries)} folders and programs"
            except OSError as error:
                self.status.text = f"Cannot read folder: {error.strerror or str(error)}"
            self._render_rows()
            return
        if not self.workspace.connected:
            self.status.text = "Connect a machine to browse its programs."
            self._sync_actions()
            return
        if self._busy():
            self.status.text = "Controller is transferring data. Refresh when it finishes."
            return
        self.root.file_popup.firmware_mode = False
        self.status.text = "Reading machine folder…"
        self._loading_remote = True
        self._pending_upload = None
        self._started = time.monotonic()
        self.root.file_popup.remote_rv.list_dir(self.remote_path)
        from kivy.clock import Clock

        if self._poll:
            self._poll.cancel()
        self._poll = Clock.schedule_interval(self._poll_remote, 0.2)

    def directory_failed(self, message):
        """Called by root.loadError before it clears the legacy transfer flags."""
        if self._loading_remote or self._pending_upload is not None:
            self.status.text = f"Could not read machine folder: {message}"
            self._loading_remote = False
            self._stop_polling()
            self._sync_actions()

    def _poll_remote(self, _dt):
        if not self.workspace.connected:
            self.status.text = "Machine disconnected. Connect and refresh."
            self._stop_polling()
            return False
        if not self._busy() and time.monotonic() - self._started >= 0.5:
            self._loading_remote = False
            if getattr(self.root.controller, "loadERR", False):
                self.status.text = "Could not read machine folder. Refresh to retry."
            elif self._pending_upload is not None:
                path = self._pending_upload
                self._pending_upload = None
                self._stop_polling()
                if getattr(self.workspace.app, "state", "") != "Idle":
                    self.status.text = "Machine is no longer idle. Upload cancelled."
                    return False
                self.root.file_popup.local_rv.curr_selected_file = path
                self.root.check_and_upload()
                self.dismiss()
                return False
            else:
                self.entries = remote_entries(self.root.file_popup.remote_rv.curr_file_list_buff)
                self.status.text = f"{len(self.entries)} folders and programs on machine"
            self._render_rows()
            self._stop_polling()
            return False
        if time.monotonic() - self._started > 25:
            self.status.text = "Machine folder is taking longer than expected. Refresh after transfer ends."
            self._stop_polling()
            return False
        return True

    def _render_rows(self):
        from kivy.metrics import dp

        from carveracontroller.desktop_components import MUTED, Action, label

        self.rows.clear_widgets()
        entries = filter_entries(self.entries, self.search.text)
        for entry in entries[:250]:
            suffix = "Folder" if entry.is_dir else human_size(entry.size)
            row = Action(
                f"{entry.name}    ·    {suffix}",
                lambda value=entry: self.select(value),
                height=dp(40),
                primary=entry == self.selected,
                halign="left",
                valign="middle",
                padding=(dp(9), 0),
                shorten=True,
                shorten_from="right",
            )
            row.bind(size=lambda obj, value: setattr(obj, "text_size", (value[0] - dp(18), value[1])))
            self.rows.add_widget(row)
        if len(entries) > 250:
            self.rows.add_widget(label("First 250 shown · narrow the search for more.", color=MUTED, height=32))
        if not entries:
            self.rows.add_widget(label("No matching programs or folders.", color=MUTED, height=48))
        self._sync_actions()

    def _sync_actions(self):
        from carveracontroller.desktop_components import ACCENT, BG, RAISED, TEXT

        for button, selected in (
            (self.local_button, self.location == "local"),
            (self.remote_button, self.location == "remote"),
        ):
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()
        selected_file = self.selected is not None and not self.selected.is_dir
        local = self.location == "local"
        self.preview_button.text = "Preview locally" if local else "Load from machine"
        self.preview_button.disabled = not selected_file or (not local and not self._remote_allowed())
        self.upload_button.opacity = 1 if local else 0
        self.upload_button.disabled = (
            not local
            or not selected_file
            or not self._remote_allowed()
            or getattr(self.workspace.app, "state", "") != "Idle"
            or self._pending_upload is not None
        )
        self.destination.text = (
            f"Upload destination: {self.remote_path}"
            if local and self.workspace.connected
            else "Local preview does not transfer a file."
            if local
            else "Load downloads for preview; it does not start the program."
        )

    def select(self, entry):
        if entry.is_dir:
            self.navigate(entry.path)
            return
        self.selected = entry
        self.detail_title.text = entry.name
        modified = (
            datetime.datetime.fromtimestamp(entry.modified).strftime("%b %d, %Y · %H:%M")
            if entry.modified
            else "Unknown"
        )
        self.metadata.text = f"{'This computer' if self.location == 'local' else 'Machine'}\n{human_size(entry.size)}\nModified {modified}"
        self._inspection_generation += 1
        generation = self._inspection_generation
        self.inspection = None
        self.thumbnail.set_segments(())
        self.inspection_note.text = "XY preview · resolved motion only"
        self.detail_scroll.scroll_y = 1
        if self.location == "local":
            from kivy.clock import Clock

            from carveracontroller.machine.program_preview import inspect_program

            self.excerpt.text = "Inspecting captured program…"
            available = set(getattr(self.root.gcode_viewer, "library_tool_table_mm", {}))

            def read():
                try:
                    result, error = inspect_program(entry.path), None
                except (OSError, ValueError, UnicodeError) as exc:
                    result, error = None, str(exc)
                Clock.schedule_once(lambda _dt: self._finish_inspection(generation, entry, available, result, error), 0)

            threading.Thread(target=read, daemon=True).start()
        else:
            self.excerpt.text = "Load this program to inspect its toolpath.\n\nThe file stays on your machine."
        self._render_rows()

    def _finish_inspection(self, generation, entry, available, result, error):
        if generation != self._inspection_generation or self.selected != entry or self.location != "local":
            return
        if error:
            self.excerpt.text = f"Quick inspection unavailable: {error}"
            return
        self.inspection = result
        units = ", ".join({"G20": "inch (G20)", "G21": "mm (G21)"}[unit] for unit in result.units) or "Unknown units"
        tools = ", ".join(f"T{tool}" for tool in result.tool_ids[:16]) or "No declared tools"
        if len(result.tool_ids) > 16:
            tools += f" … ({len(result.tool_ids)} declared tools)"
        missing = [tool for tool in result.tool_ids if tool not in available]
        self.metadata.text = f"{units} · {result.line_count} lines · {len(result.operation_names)} operations\n{tools}"
        self.excerpt.text = (
            "Frames: "
            + (", ".join(result.frames) or "Unknown")
            + "\nMissing preview definitions: "
            + (", ".join(f"T{tool}" for tool in missing) or "None")
            + f"\nUnresolved motion: {len(result.unresolved_lines)} lines"
            + "\nCaptured SHA-256: "
            + result.digest
            + "\n\nOperations\n"
            + "\n".join(result.operation_names[:20])
            + ("\n…" if len(result.operation_names) > 20 else "")
            + "\n\nInterpreter notes\n"
            + ("\n".join(result.warnings[:8]) or "None")
            + "\n\nSource excerpt\n"
            + result.excerpt
        )
        # Different work frames cannot share one geometric projection without
        # their measured transforms; do not draw a misleading combined path.
        from kivy.clock import Clock

        def show_start(_dt):
            if generation == self._inspection_generation and self.selected == entry:
                self.excerpt.cursor = (0, 0)
                self.excerpt.scroll_y = 0
                self.excerpt.scroll_x = 0
                self.detail_scroll.scroll_y = 1

        Clock.schedule_once(show_start, 0)
        self.thumbnail.set_segments(result.segments if len(result.frames) <= 1 else ())
        self.inspection_note.text = (
            "Multiple work frames · load preview to review transforms"
            if len(result.frames) > 1
            else "XY · sampled resolved motion; geometry incomplete"
            if result.unresolved_lines
            else "XY · sampled resolved motion; setup and clearance unchecked"
        )

    def preview(self):
        if self.selected is None or self.selected.is_dir:
            return
        if self.location == "local":
            self.root.file_popup.local_rv.curr_selected_file = self.selected.path
            self.root.view_local_file()
        else:
            if not self._remote_allowed():
                self.status.text = "Connect the machine and finish the current transfer first."
                return
            remote = self.root.file_popup.remote_rv
            remote.curr_selected_file = self.selected.path
            remote.curr_selected_filesize = self.selected.size
            self.root.check_and_download()
        self.dismiss()

    def upload(self):
        if (
            self._pending_upload is not None
            or self.location != "local"
            or self.selected is None
            or self.selected.is_dir
            or not self._remote_allowed()
            or getattr(self.workspace.app, "state", "") != "Idle"
        ):
            return
        self.root.file_popup.firmware_mode = False
        self.root.file_popup.local_rv.curr_selected_file = self.selected.path
        # Refresh the destination before checking for collisions; an old listing
        # must not bypass the existing overwrite confirmation.
        self.status.text = "Checking upload destination…"
        self._loading_remote = True
        self._pending_upload = self.selected.path
        self._started = time.monotonic()
        self.root.file_popup.remote_rv.list_dir(self.remote_path)
        from kivy.clock import Clock

        if self._poll:
            self._poll.cancel()
        self._poll = Clock.schedule_interval(self._poll_remote, 0.2)
        self._sync_actions()
