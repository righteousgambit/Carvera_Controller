"""Consistent local artifact browser for profiles, CAD and machining recipes."""

import os
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior

from carveracontroller.desktop_components import MUTED, Action, Field, Surface, label
from carveracontroller.desktop_program_picker import ProgramEntry, human_size
from carveracontroller.machine.artifact_fs import filesystem_request


def artifact_entries(directory, suffixes, query=""):
    entries = []
    with os.scandir(Path(directory).expanduser()) as children:
        for index, child in enumerate(children):
            if index >= 20000:
                raise ValueError("Folder has more than 20,000 items; enter a narrower folder")
            if child.name.startswith("."):
                continue
            try:
                stat = child.stat()
                is_dir = child.is_dir()
            except OSError:
                continue
            if is_dir or any(child.name.casefold().endswith(suffix.casefold()) for suffix in suffixes):
                entries.append(ProgramEntry(child.name, child.path, is_dir, stat.st_size, stat.st_mtime))
    return sorted(
        (entry for entry in entries if query.casefold().strip() in entry.name.casefold()),
        key=lambda entry: (not entry.is_dir, entry.name.casefold()),
    )


class ArtifactList(RecycleView):
    def scroll_to(self, widget, padding=10, animate=False):
        """Reveal a focused recycled row without ordinary Layout internals.

        RecycleLayout's _trigger_layout is a method, not a ClockEvent. Kivy's
        ScrollView implementation assumes the latter and crashes on focus.
        Only attached, current rows can move this viewport.
        """
        viewport = self._viewport
        if not self.parent or viewport is None or widget.parent is not viewport:
            return
        overflow = viewport.height - self.height
        if overflow <= 0:
            return
        padding_y = padding if isinstance(padding, (int, float)) else padding[1]
        bottom = self.parent.to_widget(*widget.to_window(*widget.pos))[1]
        top = self.parent.to_widget(*widget.to_window(widget.right, widget.top))[1]
        distance = 0
        if bottom < self.y + padding_y:
            distance = self.y + padding_y - bottom
        elif top > self.top - padding_y:
            distance = self.top - padding_y - top
        self.scroll_y = max(0, min(1, self.scroll_y - distance / overflow))


class ArtifactRow(RecycleDataViewBehavior, Action):
    entry = ObjectProperty(None, allownone=True)
    browser = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__("", self.activate, **kwargs)
        self.halign = "left"
        self.valign = "middle"
        self.shorten = True
        self.shorten_from = "right"
        self.bind(size=lambda item, size: setattr(item, "text_size", (max(0, size[0] - dp(20)), size[1])))

    def activate(self):
        if self.browser is not None and self.entry is not None:
            self.browser.select(self.entry)


class ArtifactBrowser:
    def __init__(self, workspace, callback, suffixes, save=False, title="Choose file"):
        self.workspace, self.callback, self.suffixes, self.save = workspace, callback, tuple(suffixes), save
        # Session-local accepted locations avoid repeatedly entering unrelated storage.
        # Separate artifact types retain their own folder; save and load share it.
        self.location_key = tuple(sorted(suffix.casefold() for suffix in self.suffixes))
        self.path = Path(getattr(workspace, "artifact_locations", {}).get(self.location_key, Path.home() / "Downloads"))
        self.generation = 0
        self.entries = []
        self.closed = False
        self.ready = False
        self.choosing = False
        self._work_lock = threading.Lock()
        self._pending_work = None
        self._worker_running = False
        self.popup = ModalView(size_hint=(0.90, 0.85), auto_dismiss=False, background="", background_color=(0, 0, 0, 0))
        panel = Surface(orientation="vertical", padding=dp(16), spacing=dp(10))
        heading = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        heading.add_widget(label(title, 20, height=36))
        heading.add_widget(Action("Close", self.dismiss, size_hint_x=None, width=dp(72)))
        panel.add_widget(heading)
        quick = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        for name, target in (
            ("Home", Path.home()),
            ("Downloads", Path.home() / "Downloads"),
            ("Jobs", Path.home() / ".carvera/jobs"),
        ):
            callback = self.open_jobs if name == "Jobs" else lambda target=target: self.navigate(target)
            quick.add_widget(Action(name, callback, height=dp(34)))
        panel.add_widget(quick)
        nav = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        nav.add_widget(Action("Up", lambda: self.navigate(self.path.parent), size_hint_x=None, width=dp(48)))
        self.location = Field(text=str(self.path), hint_text="Folder or full file path")
        self.location.bind(on_text_validate=lambda *_: self.navigate(self.location.text))
        nav.add_widget(self.location)
        nav.add_widget(Action("Go", lambda: self.navigate(self.location.text), size_hint_x=None, width=dp(48)))
        panel.add_widget(nav)
        self.search = Field(hint_text="Filter files and folders by name")
        self.search.bind(text=lambda *_: self.render())
        panel.add_widget(self.search)
        self.files = ArtifactList(
            do_scroll_x=False, bar_width=dp(9), scroll_type=["content", "bars"], always_overscroll=False
        )
        self.rows = RecycleBoxLayout(
            default_size=(None, dp(36)),
            default_size_hint=(1, None),
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(4),
        )
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.files.add_widget(self.rows)
        self.files.viewclass = ArtifactRow
        panel.add_widget(self.files)
        panel.add_widget(label("Filename · " + ", ".join(self.suffixes), 11, MUTED, 24))
        self.filename = Field(hint_text="Select a file above" if not save else "New filename" + self.suffixes[0])
        self.filename.bind(on_text_validate=lambda *_: self.choose())
        panel.add_widget(self.filename)
        self.note = label("Local files · folders first · selection does not run or upload programs.", 11, MUTED, 44)
        panel.add_widget(self.note)
        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        actions.add_widget(Action("Cancel", self.dismiss))
        self.choose_action = Action("Save here" if save else "Choose file", self.choose, primary=True)
        self.choose_action.disabled = True
        actions.add_widget(self.choose_action)
        panel.add_widget(actions)
        self.popup.add_widget(panel)

    def open(self):
        self.popup.open()
        self.navigate(self.path, fallback=Path.home())

    def dismiss(self):
        self.closed = True
        self.generation += 1
        with self._work_lock:
            self._pending_work = None
        self.files.data = []
        self.popup.dismiss()

    def open_jobs(self):
        directory = Path.home() / ".carvera" / "jobs"
        self.navigate(directory, create=True)

    def _queue_work(self, work):
        """One active filesystem operation and at most one latest pending request."""
        with self._work_lock:
            self._pending_work = work
            if self._worker_running:
                return
            self._worker_running = True

        def run():
            while True:
                with self._work_lock:
                    current, self._pending_work = self._pending_work, None
                    if current is None:
                        self._worker_running = False
                        return
                current()

        threading.Thread(target=run, daemon=True).start()

    def navigate(self, directory, *, create=False, fallback=None):
        if self.closed:
            return
        self.generation += 1
        generation = self.generation
        self.ready = False
        self.choosing = False
        self.choose_action.disabled = True
        self.entries = []
        self.search.text = ""
        self.location.text = str(directory)
        self.note.text = "Reading folder in isolated helper… · choose another location to cancel"
        self.files.data = []

        def read():
            try:
                result = filesystem_request(
                    {
                        "operation": "list",
                        "path": str(directory),
                        "suffixes": self.suffixes,
                        "create": create,
                        "fallback": str(fallback) if fallback is not None else None,
                    },
                    cancelled=lambda: self.closed or generation != self.generation,
                )
                candidate = Path(result["path"])
                filename = result["filename"]
                entries = [ProgramEntry(**entry) for entry in result["entries"]]
                error = None
            except (OSError, ValueError, RuntimeError) as exc:
                candidate, filename, entries, error = None, None, [], str(exc)
            Clock.schedule_once(lambda _dt: finish(candidate, filename, entries, error), 0)

        def finish(candidate, filename, entries, error):
            if generation != self.generation or self.closed:
                return
            self.entries = entries
            if error:
                self.note.text = error
            else:
                self.path = candidate
                self.location.text = str(candidate)
                if filename is not None:
                    self.filename.text = filename
                self.ready = True
                self.choose_action.disabled = False
                self.render()

        self._queue_work(read)

    def render(self):
        if not self.ready or self.closed or self.choosing:
            return
        query = self.search.text.strip().casefold()
        entries = [entry for entry in self.entries if query in entry.name.casefold()]
        self.files.data = [
            {
                "text": ("Folder · " if entry.is_dir else "")
                + entry.name
                + ("" if entry.is_dir else " · " + human_size(entry.size)),
                "entry": entry,
                "browser": self,
            }
            for entry in entries
        ]
        self.files.scroll_y = 1
        self.note.text = (
            f"{len(entries)} matching items · all available by scrolling"
            if entries
            else "No matching files. Navigate to another folder or change the filter."
        )

    def select(self, entry):
        if not self.ready or self.closed or self.choosing or entry not in self.entries:
            return
        if entry.is_dir:
            self.filename.text = ""
            self.navigate(entry.path)
        else:
            self.filename.text = entry.name
            self.note.text = f"Selected {entry.name} · {human_size(entry.size)}"

    def choose(self):
        if self.closed or not self.ready or self.choosing:
            return
        if self.location.text != str(self.path):
            self.navigate(self.location.text)
            return
        name = self.filename.text.strip()
        if (
            not name
            or Path(name).name != name
            or not any(name.casefold().endswith(suffix.casefold()) for suffix in self.suffixes)
        ):
            self.note.text = "Enter a filename ending in " + ", ".join(self.suffixes)
            return
        target = self.path / name
        generation, location = self.generation, self.location.text
        self.choosing = True
        self.choose_action.disabled = True
        self.note.text = "Checking selected file…"

        def check():
            error = None
            try:
                filesystem_request(
                    {"operation": "check", "path": str(target), "save": self.save},
                    cancelled=lambda: self.closed or generation != self.generation,
                )
            except (OSError, ValueError) as exc:
                error = str(exc)
            Clock.schedule_once(lambda _dt: finish(error), 0)

        def finish(error):
            if self.closed or generation != self.generation:
                return
            self.choosing = False
            self.choose_action.disabled = False
            if self.filename.text.strip() != name or self.location.text != location:
                self.note.text = "Selection changed. Review it and choose again."
                return
            if error:
                self.note.text = error
                return
            try:
                self.callback(str(target))
            except (OSError, ValueError, TypeError) as exc:
                self.note.text = str(exc)
                return
            locations = getattr(self.workspace, "artifact_locations", None)
            if locations is None:
                locations = self.workspace.artifact_locations = {}
            locations[self.location_key] = str(target.parent)
            self.dismiss()

        self._queue_work(check)
