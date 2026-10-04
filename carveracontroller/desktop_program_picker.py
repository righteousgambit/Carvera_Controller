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

from carveracontroller.machine.program_places import ProgramPlaces

PROGRAM_EXTENSIONS = frozenset({".cnc", ".nc", ".gcode", ".tap", ".ngc"})


@dataclass(frozen=True)
class ProgramEntry:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified: float = 0
    available: bool = True


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


def read_local_location(path, *, base, navigate=False, references=None):
    """Filesystem work only; callers publish results on the UI thread."""
    selected = None
    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(base) / candidate
        candidate = candidate.absolute()
        unsupported = False
        if navigate and candidate.is_file():
            unsupported = candidate.suffix.casefold() not in PROGRAM_EXTENSIONS
            if not unsupported:
                stat = candidate.stat()
                selected = ProgramEntry(candidate.name, str(candidate), False, stat.st_size, stat.st_mtime)
            candidate = candidate.parent
        if references is not None:
            entries = []
            for reference in references:
                item = Path(reference)
                try:
                    stat = item.stat()
                    entries.append(
                        ProgramEntry(item.name, reference, False, stat.st_size, stat.st_mtime, item.is_file())
                    )
                except OSError:
                    entries.append(ProgramEntry(item.name, reference, False, available=False))
            return str(candidate), entries, None, None
        try:
            entries = list_program_directory(candidate)
        except (OSError, ValueError) as error:
            return str(candidate), [], None, f"Cannot read folder: {error}"
        error = f"Unsupported program file: {Path(path).name}" if unsupported else None
        return str(candidate), entries, selected, error
    except (OSError, ValueError, RuntimeError) as error:
        return str(path), [], None, f"Cannot read path: {error}"


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


def initial_program_candidates(old_path, selected_path=None):
    """Choose startup hints without touching potentially unavailable storage."""
    candidates = [Path(selected_path).expanduser().parent] if selected_path else []
    if old_path:
        candidates.append(Path(old_path).expanduser())
    candidates.append(Path.home())
    return tuple(
        dict.fromkeys(
            str(path) for path in candidates if not any(part.casefold().endswith(".app") for part in path.parts)
        )
    )


def initial_program_directory(old_path, selected_path=None):
    """Initial display hint; existence validation belongs to the read worker."""
    return initial_program_candidates(old_path, selected_path)[0]


def read_initial_program_location(candidates):
    """Resolve saved hints in priority order, off the UI thread.

    A missing saved folder falls back; an existing but unreadable folder retains
    its error instead of silently presenting a different location.
    """
    for candidate in candidates:
        try:
            if Path(candidate).is_dir():
                return read_local_location(candidate, base=candidate)
        except OSError:
            return read_local_location(candidate, base=candidate)
    return read_local_location(candidates[-1], base=candidates[-1])


class ProgramBrowser:
    """Reusable popup owned by DesktopWorkspace; widgets load only on demand."""

    def __init__(self, workspace, places=None):
        self.workspace = workspace
        self.saved_places = places if places is not None else ProgramPlaces(load=False)
        self.collection = None
        self.root = workspace.machine
        self.location = "local"
        old_path = getattr(self.root.file_popup.local_rv, "curr_dir", "")
        self._initial_candidates = initial_program_candidates(
            old_path, getattr(workspace.app, "selected_local_filename", None)
        )
        self.local_path = self._initial_candidates[0]
        self.remote_path = str(getattr(self.root.file_popup.remote_rv, "curr_dir", "/sd/gcodes"))
        self.entries = []
        self.selected = None
        self.popup = None
        self._poll = None
        self._loading_remote = False
        self._pending_upload = None
        self._started = 0
        self._inspection_generation = 0
        self._local_generation = 0
        self._local_lock = threading.Lock()
        self._local_pending = None
        self._local_worker_running = False
        self._places_lock = threading.Lock()
        self._places_pending = []
        self._places_worker_running = False
        self._favorite_pending = False
        self._places_revision = 0
        self._reference_visible = False
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
            Choice,
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
        places = AdaptiveGrid(max_cols=6, min_width=130, row_height=34, spacing=dp(6))
        self.places = places
        self.local_button = Action("This computer", lambda: self.set_location("local"), height=34)
        self.remote_button = Action("Machine files", lambda: self.set_location("remote"), height=34)
        places.add_widget(self.local_button)
        places.add_widget(self.remote_button)
        self.recent_button = Action("Recent inspections", lambda: self.choose_collection("recent"), height=34)
        self.favorites_button = Action("Favorites", lambda: self.choose_collection("favorites"), height=34)
        places.add_widget(self.recent_button)
        places.add_widget(self.favorites_button)
        places.add_widget(Action("Home", lambda: self.navigate(str(Path.home()), local=True), height=34))
        places.add_widget(
            Action("Downloads", lambda: self.navigate(str(Path.home() / "Downloads"), local=True), height=34)
        )
        panel.add_widget(places)
        body = BoxLayout(spacing=dp(14))
        self.body = body
        center = BoxLayout(orientation="vertical", spacing=dp(8))
        navigation = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.up_button = Action("Up", self.up, size_hint_x=None, width=dp(42), height=dp(34))
        navigation.add_widget(self.up_button)
        self.path_field = Field(
            hint_text="Folder or program path",
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
        self.go_button = Action(
            "Go", lambda: self.navigate(self.path_field.text), size_hint_x=None, width=dp(42), height=dp(34)
        )
        navigation.add_widget(self.go_button)
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
        detail_content = BoxLayout(
            orientation="vertical", spacing=dp(8), padding=[0, 0, dp(14), dp(8)], size_hint_y=None
        )
        detail_content.bind(minimum_height=detail_content.setter("height"))
        detail_scroll.add_widget(detail_content)
        details.add_widget(detail_scroll)
        self.detail_content = detail_content
        self.detail_title = label("Program details", size=16, height=42, shorten=True)
        self.favorite_button = Action("Add favorite", self.toggle_favorite, height=dp(34))
        self.metadata = label("Select a program to inspect it.", size=12, color=MUTED, height=56)
        detail_content.add_widget(self.detail_title)
        detail_content.add_widget(self.favorite_button)
        detail_content.add_widget(self.metadata)
        from carveracontroller.desktop_readiness import wrapped

        self.dependencies = None
        self.dependency_note = wrapped("", size=11)
        detail_content.add_widget(self.dependency_note)
        dependency_actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.dependency_refresh = Action("Refresh setup check", self.refresh_dependencies, height=dp(34))
        self.dependency_review = Action("Review setup", self.review_dependencies, height=dp(34))
        dependency_actions.add_widget(self.dependency_refresh)
        dependency_actions.add_widget(self.dependency_review)
        detail_content.add_widget(dependency_actions)
        self.dependency_actions = dependency_actions
        self.clear_dependencies()
        from carveracontroller.desktop_program_thumbnail import ProgramThumbnail

        self.thumbnail = ProgramThumbnail()
        self.preview_frames = {}
        self.frame_extents = {}
        self.frame_selector = Choice(text="No resolved frame", values=(), height=dp(34), disabled=True)
        self.frame_selector.bind(text=lambda *_: self.show_frame())
        self.path_bounds = wrapped("Select a program to inspect its motion bounds.", size=11)
        self.comparison_baseline = None
        self.comparison_baseline_path = None
        self.comparison_note = wrapped(
            "Pin an inspected local program, then inspect another revision to compare.", size=11
        )
        self.comparison_actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.comparison_pin = Action("Pin revision", self.pin_revision, height=dp(34))
        self.comparison_clear = Action("Clear baseline", self.clear_revision, height=dp(34))
        self.comparison_actions.add_widget(self.comparison_pin)
        self.comparison_actions.add_widget(self.comparison_clear)
        self.refresh_comparison()
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
        self.detail_tabs = AdaptiveGrid(max_cols=4, min_width=100, row_height=34, spacing=dp(6))
        self.detail_tab_buttons = {}
        for name in ("Path", "Setup", "Source", "Compare"):
            button = Action(name, lambda selected=name: self.choose_detail(selected), height=dp(34))
            self.detail_tab_buttons[name] = button
            self.detail_tabs.add_widget(button)
        self.choose_detail("Path")
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
        self.popup.bind(on_dismiss=self._on_dismiss)
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
            self.places.max_cols = 2 if compact else 6
            self.places._reflow()
            self.body.orientation = "vertical" if compact else "horizontal"
            self.details.size_hint_x = 1 if compact else 0.45
            self.details.size_hint_y = 0.8 if compact else 1

    def open(self):
        if self.popup is None:
            self._build()
        self._reference_visible = True
        self.popup.open()
        self.refresh()

    def dismiss(self):
        self._reference_visible = False
        if self.popup:
            self.popup.dismiss()

    def _on_dismiss(self, *_):
        self._reference_visible = False
        self._stop_polling()

    def _stop_polling(self):
        self._loading_remote = False
        self._inspection_generation += 1
        self._local_generation += 1
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
        self.collection = None
        self.location = location
        self.search.text = ""
        self.refresh()

    def navigate(self, path, local=False):
        self.collection = None
        if local:
            self.location = "local"
        self._stop_polling()
        if self.location == "local":
            self.search.text = ""
            self._reset_listing()
            self._read_local(path, navigate=True)
            return
        normalized = posixpath.normpath(path.replace("\\", "/"))
        if normalized != "/sd" and not normalized.startswith("/sd/"):
            self.status.text = "Choose a folder under /sd."
            return
        self.remote_path = normalized
        self.search.text = ""
        self.refresh()

    def up(self):
        if self.collection:
            return
        path = str(Path(self.local_path).parent) if self.location == "local" else posixpath.dirname(self.remote_path)
        if self.location == "remote" and self.remote_path == "/sd":
            return
        self.navigate(path)

    def _reset_listing(self):
        self._loading_remote = False
        self.selected = None
        self.detail_title.text = "Program details"
        self.metadata.text = "Select a program to inspect it."
        self.excerpt.text = ""
        self.inspection = None
        self.clear_dependencies()
        self.clear_path_frames()
        self.refresh_comparison()
        self.thumbnail.set_segments(())
        self.inspection_note.text = "XY preview · resolved motion only"
        self.detail_scroll.scroll_y = 1
        self.entries = []
        self.path_field.text = (
            "Recent inspections"
            if self.collection == "recent"
            else "Favorites"
            if self.collection == "favorites"
            else self.local_path
            if self.location == "local"
            else self.remote_path
        )
        self._render_rows()

    def _read_local(self, path, navigate=False):
        from kivy.clock import Clock

        generation = self._local_generation
        base, collection = self.local_path, self.collection
        places_path = self.saved_places.path
        initial = self._initial_candidates
        self._initial_candidates = None
        if navigate or collection or not initial or path != initial[0]:
            initial = None
        self.status.text = "Reading local programs..."
        self._sync_actions()
        with self._local_lock:
            # One active filesystem read and one latest pending request. A slow
            # volume cannot spawn an unbounded set of threads or stale callbacks.
            self._local_pending = (
                generation,
                path,
                base,
                navigate,
                places_path,
                collection,
                self._places_revision,
                initial,
            )
            if self._local_worker_running:
                return
            self._local_worker_running = True

        def read():
            while True:
                with self._local_lock:
                    request = self._local_pending
                    self._local_pending = None
                    if request is None:
                        self._local_worker_running = False
                        return
                stamp, target, parent, nav, store_path, kind, revision, startup = request
                store = ProgramPlaces(store_path)
                if kind and store.error:
                    result = (str(target), [], None, f"Program shortcuts unavailable: {store.error}")
                else:
                    refs = tuple(getattr(store, kind)) if kind else None
                    result = (
                        read_initial_program_location(startup)
                        if startup
                        else read_local_location(target, base=parent, navigate=nav, references=refs)
                    )
                Clock.schedule_once(
                    lambda _dt, token=stamp, value=result, group=kind, saved=store, rev=revision: self._finish_local(
                        token, value, group, saved, rev
                    ),
                    0,
                )

        threading.Thread(target=read, daemon=True).start()

    def _finish_local(self, generation, result, collection, store=None, revision=None):
        if generation != self._local_generation or self.location != "local" or self.collection != collection:
            return
        path, self.entries, entry, error = result
        if store and not store.error and revision == self._places_revision:
            self.saved_places.recent = store.recent
            self.saved_places.favorites = store.favorites
        if not collection:
            self.local_path = path
            self.path_field.text = path
        self.status.text = error or (
            f"{len(self.entries)} " + ("recently inspected programs" if collection == "recent" else "favorite programs")
            if collection
            else f"{len(self.entries)} folders and programs"
        )
        self._render_rows()
        if entry is not None:
            self.select(entry)

    def refresh(self):
        self._stop_polling()
        self._reset_listing()
        if self.location == "local":
            self._read_local(self.local_path)
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

    def choose_collection(self, name):
        if name not in ("recent", "favorites"):
            raise ValueError("Unknown program collection")
        self.location, self.collection = "local", name
        self.search.text = ""
        self.refresh()

    def toggle_favorite(self):
        if self.location != "local" or self.selected is None or self.selected.is_dir or self._favorite_pending:
            return
        self._favorite_pending = True
        self._queue_place_save("favorite", self.selected.path)
        self._sync_actions()

    def _queue_place_save(self, kind, path):
        """Serialize accepted reference edits without doing filesystem I/O on Clock.

        Recent requests retain the newest 25 distinct references, matching the
        store's limit. A favorite button remains pending until its one accepted
        edit has a receipt. Dismissal never cancels an already accepted save.
        """
        from kivy.clock import Clock

        self._places_revision += 1
        request = (kind, path, self._inspection_generation)
        with self._places_lock:
            if kind == "recent":
                self._places_pending = [
                    item for item in self._places_pending if not (item[0] == "recent" and item[1] == path)
                ]
                recent = [item for item in self._places_pending if item[0] == "recent"]
                if len(recent) >= ProgramPlaces.RECENT_LIMIT:
                    self._places_pending.remove(recent[0])
            self._places_pending.append(request)
            if self._places_worker_running:
                return
            self._places_worker_running = True

        def save():
            while True:
                with self._places_lock:
                    if not self._places_pending:
                        self._places_worker_running = False
                        return
                    operation, reference, token = self._places_pending.pop(0)
                store = ProgramPlaces(self.saved_places.path)
                try:
                    if operation == "recent":
                        store.record_recent(reference)
                    else:
                        store.toggle_favorite(reference)
                    error = None
                except (OSError, ValueError) as exc:
                    error = str(exc)
                Clock.schedule_once(
                    lambda _dt, action=operation, target=reference, stamp=token, snapshot=store, failure=error: (
                        self._finish_place_save(action, target, stamp, snapshot, failure)
                    ),
                    0,
                )

        threading.Thread(target=save, daemon=True).start()

    def _finish_place_save(self, kind, path, generation, store, error):
        # Reject snapshots captured while this disk write was still pending.
        self._places_revision += 1
        if kind == "favorite":
            self._favorite_pending = False
        if not error:
            self.saved_places.recent, self.saved_places.favorites = store.recent, store.favorites
        if not self._reference_visible:
            return
        if error:
            if kind == "favorite" or generation == self._inspection_generation:
                self.status.text = f"Could not save {'favorite' if kind == 'favorite' else 'recent reference'}: {error}"
        elif kind == "favorite" and self.collection == "favorites":
            self.refresh()
        elif kind == "favorite" and self.selected and self.selected.path == path:
            self.status.text = "Favorite saved and read back."
        self._sync_actions()

    def _render_rows(self):
        from kivy.metrics import dp

        from carveracontroller.desktop_components import MUTED, Action, label

        self.rows.clear_widgets()
        query = self.search.text.strip().casefold()
        entries = (
            [entry for entry in self.entries if query in entry.path.casefold()]
            if self.collection
            else filter_entries(self.entries, query)
        )
        for entry in entries[:250]:
            suffix = "Folder" if entry.is_dir else human_size(entry.size)
            if self.collection:
                suffix = (
                    (human_size(entry.size) if entry.available else "Unavailable")
                    + " · "
                    + str(Path(entry.path).parent)
                )
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
            (self.local_button, self.location == "local" and self.collection is None),
            (self.remote_button, self.location == "remote"),
            (self.recent_button, self.collection == "recent"),
            (self.favorites_button, self.collection == "favorites"),
        ):
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()
        selected_file = self.selected is not None and not self.selected.is_dir and self.selected.available
        local = self.location == "local"
        self.search.hint_text = "Search saved program paths" if self.collection else "Search this folder"
        self.path_field.disabled = self.go_button.disabled = self.up_button.disabled = bool(self.collection)
        self.favorite_button.disabled = (
            not local or self.selected is None or self.selected.is_dir or self._favorite_pending
        )
        self.favorite_button.text = (
            "Saving favorite..."
            if self._favorite_pending
            else "Remove favorite"
            if self.selected and self.selected.path in self.saved_places.favorites
            else "Add favorite"
        )
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
        self._local_generation += 1
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
        self.clear_dependencies()
        self.clear_path_frames()
        self.refresh_comparison()
        self.thumbnail.set_segments(())
        self.inspection_note.text = "XY preview · resolved motion only"
        self.detail_scroll.scroll_y = 1
        if not entry.available:
            self.metadata.text = f"Unavailable local program\n{entry.path}"
            self.excerpt.text = "The saved reference remains available to remove from Favorites."
            self._render_rows()
            return
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
            self.status.text = self.excerpt.text
            self.inspection_note.text = "Quick inspection unavailable · see Source for details"
            return
        self.inspection = result
        self.refresh_comparison()
        self.refresh_dependencies()
        self._queue_place_save("recent", entry.path)
        units = ", ".join({"G20": "inch (G20)", "G21": "mm (G21)"}[unit] for unit in result.units) or "Unknown units"
        tools = ", ".join(f"T{tool}" for tool in result.tool_ids[:16]) or "No declared tools"
        if len(result.tool_ids) > 16:
            tools += f" … ({len(result.tool_ids)} declared tools)"
        missing = self.dependencies.missing_tools
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
        self.preview_frames = dict.fromkeys(result.frames, ())
        self.preview_frames.update({frame or "Unknown frame": segments for frame, segments in result.frame_previews})
        self.frame_extents = {extent.wcs or "Unknown frame": extent for extent in result.frame_bounds}
        self.frame_selector.values = tuple(self.preview_frames)
        self.frame_selector.disabled = not self.preview_frames
        self.frame_selector.text = next(iter(self.preview_frames), "No resolved frame")
        self.show_frame()

    def clear_path_frames(self):
        self.preview_frames = {}
        self.frame_extents = {}
        self.frame_selector.values = ()
        self.frame_selector.disabled = True
        self.frame_selector.text = "No resolved frame"
        self.path_bounds.text = "Select a program to inspect its motion bounds."

    def show_frame(self):
        frame = self.frame_selector.text
        self.thumbnail.set_segments(self.preview_frames.get(frame, ()))
        extent = self.frame_extents.get(frame)
        self.inspection_note.text = (
            "XY · sampled frame path; geometry incomplete"
            if self.inspection and self.inspection.unresolved_lines
            else "XY · sampled frame path; setup and clearance unchecked"
        )
        if extent is None:
            self.path_bounds.text = f"{frame} · motion bounds unavailable; no resolved moves."
            return
        self.path_bounds.text = (
            f"{frame} · resolved program bounds (mm)\n"
            + "\n".join(
                f"{axis}: {low:.3f} to {high:.3f}"
                for axis, low, high in zip("XYZ", extent.minimum_mm, extent.maximum_mm)
            )
            + f"\n{len(extent.resolved_lines)} resolved source moves · analytic arc extrema included"
            + "\nUnresolved moves excluded · machine travel and clearance unchecked."
        )

    def pin_revision(self):
        if self.inspection is None or self.selected is None or self.location != "local":
            return
        self.comparison_baseline = self.inspection
        self.comparison_baseline_path = self.selected.path
        self.refresh_comparison()

    def clear_revision(self):
        self.comparison_baseline = None
        self.comparison_baseline_path = None
        self.refresh_comparison()

    def refresh_comparison(self):
        captured = self.inspection is not None and self.selected is not None and self.location == "local"
        self.comparison_pin.disabled = not captured
        self.comparison_clear.disabled = self.comparison_baseline is None
        if self.comparison_baseline is None:
            self.comparison_note.text = "Pin an inspected local program, then inspect another revision to compare. The baseline retains its captured inspection even if that file changes."
        elif not captured:
            self.comparison_note.text = f"Baseline: {self.comparison_baseline_path}\nSHA-256: {self.comparison_baseline.digest}\nSelect a local program to compare."
        else:
            from carveracontroller.machine.program_comparison import compare_programs

            comparison = compare_programs(self.comparison_baseline, self.inspection)
            self.comparison_note.text = f"{comparison.text}\n\nBaseline file: {self.comparison_baseline_path}\nCandidate file: {self.selected.path}"

    def choose_detail(self, name):
        from carveracontroller.desktop_components import ACCENT, BG, RAISED, TEXT

        if name not in ("Path", "Setup", "Source", "Compare"):
            raise ValueError("Unknown program detail view")
        for control in self.detail_content.walk(restrict=True):
            if hasattr(control, "focus"):
                control.focus = False
        self.detail_view = name
        self.detail_content.clear_widgets()
        for widget in (self.detail_title, self.favorite_button, self.metadata, self.detail_tabs):
            self.detail_content.add_widget(widget)
        widgets = (
            (self.dependency_note, self.dependency_actions)
            if name == "Setup"
            else (self.comparison_actions, self.comparison_note)
            if name == "Compare"
            else (self.excerpt,)
            if name == "Source"
            else (self.frame_selector, self.thumbnail, self.inspection_note, self.path_bounds)
        )
        for widget in widgets:
            self.detail_content.add_widget(widget)
        for key, button in self.detail_tab_buttons.items():
            button.base_color = ACCENT if key == name else RAISED
            button.color = BG if key == name else TEXT
            button._paint()
        self.detail_scroll.scroll_y = 1

    def clear_dependencies(self):
        self.dependencies = None
        self.dependency_note.text = ""
        self.dependency_refresh.disabled = True
        self.dependency_review.disabled = True

    def refresh_dependencies(self):
        if self.inspection is None or self.location != "local" or self.selected is None:
            self.clear_dependencies()
            return
        from carveracontroller.machine.program_dependencies import describe_dependencies

        viewer = self.root.gcode_viewer
        setup = viewer.machine_setup
        workspace = self.workspace
        self.dependencies = describe_dependencies(
            self.inspection,
            available_tools=getattr(viewer, "library_tool_table_mm", {}),
            profile_name=(workspace.selected_machine_profile or {}).get("name", ""),
            toolset_name=(workspace.loaded_toolset or {}).get("name", ""),
            stock_size_mm=setup.stock_size_mm,
            alignment_confirmed=setup.alignment_confirmed,
        )
        self.dependency_note.text = self.dependencies.text
        self.dependency_refresh.disabled = False
        self.dependency_review.disabled = False

    def review_dependencies(self):
        if self.dependencies is None:
            return
        self.dismiss()
        self.workspace.select("Scene")

    def preview(self):
        if self.selected is None or self.selected.is_dir or not self.selected.available:
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
            or not self.selected.available
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
