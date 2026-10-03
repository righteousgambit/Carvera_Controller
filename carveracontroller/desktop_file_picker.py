"""Consistent local artifact browser for profiles, CAD and machining recipes."""

import os
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import MUTED, Action, Field, Surface, label
from carveracontroller.desktop_program_picker import ProgramEntry, human_size


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


class ArtifactBrowser:
    def __init__(self, workspace, callback, suffixes, save=False, title="Choose file"):
        self.workspace, self.callback, self.suffixes, self.save = workspace, callback, tuple(suffixes), save
        self.path = Path.home() / "Downloads"
        if not self.path.is_dir():
            self.path = Path.home()
        self.generation = 0
        self.entries = []
        self.closed = False
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
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.rows = BoxLayout(orientation="vertical", size_hint_y=None, height=0, spacing=dp(4))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll.add_widget(self.rows)
        panel.add_widget(scroll)
        panel.add_widget(label("Filename · " + ", ".join(self.suffixes), 11, MUTED, 24))
        self.filename = Field(hint_text="Select a file above" if not save else "New filename" + self.suffixes[0])
        self.filename.bind(on_text_validate=lambda *_: self.choose())
        panel.add_widget(self.filename)
        self.note = label("Local files · folders first · selection does not run or upload programs.", 11, MUTED, 44)
        panel.add_widget(self.note)
        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        actions.add_widget(Action("Cancel", self.dismiss))
        actions.add_widget(Action("Save here" if save else "Choose file", self.choose, primary=True))
        panel.add_widget(actions)
        self.popup.add_widget(panel)

    def open(self):
        self.popup.open()
        self.navigate(self.path)

    def dismiss(self):
        self.closed = True
        self.generation += 1
        self.popup.dismiss()

    def open_jobs(self):
        directory = Path.home() / ".carvera" / "jobs"
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.note.text = f"Unable to open the local Jobs folder: {exc}"
            return
        self.navigate(directory)

    def navigate(self, directory):
        candidate = Path(directory).expanduser()
        if candidate.is_file():
            self.filename.text = candidate.name
            candidate = candidate.parent
        if not candidate.is_dir():
            self.note.text = "That folder is unavailable. Enter an existing folder or file path."
            return
        self.path = candidate.resolve()
        self.location.text = str(self.path)
        self.search.text = ""
        self.generation += 1
        generation = self.generation
        directory = self.path
        self.note.text = "Reading local folder…"
        self.rows.clear_widgets()

        def read():
            try:
                entries, error = artifact_entries(directory, self.suffixes), None
            except (OSError, ValueError) as exc:
                entries, error = [], str(exc)
            Clock.schedule_once(lambda _dt: finish(entries, error), 0)

        def finish(entries, error):
            if generation != self.generation or self.closed:
                return
            self.entries = entries
            if error:
                self.note.text = error
            else:
                self.render()

        threading.Thread(target=read, daemon=True).start()

    def render(self):
        query = self.search.text.strip().casefold()
        entries = [entry for entry in self.entries if query in entry.name.casefold()]
        self.rows.clear_widgets()
        for entry in entries[:250]:
            name = ("Folder · " if entry.is_dir else "") + entry.name
            if not entry.is_dir:
                name += " · " + human_size(entry.size)
            self.rows.add_widget(Action(name, lambda entry=entry: self.select(entry), height=dp(36)))
        self.note.text = (
            f"{len(entries)} matching items"
            if entries
            else "No matching files. Navigate to another folder or change the filter."
        )
        if len(entries) > 250:
            self.note.text += " · first 250 shown; narrow the filter to find another item"

    def select(self, entry):
        if entry.is_dir:
            self.filename.text = ""
            self.navigate(entry.path)
        else:
            self.filename.text = entry.name
            self.note.text = f"Selected {entry.name} · {human_size(entry.size)}"

    def choose(self):
        name = self.filename.text.strip()
        if (
            not name
            or Path(name).name != name
            or not any(name.casefold().endswith(suffix.casefold()) for suffix in self.suffixes)
        ):
            self.note.text = "Enter a filename ending in " + ", ".join(self.suffixes)
            return
        target = self.path / name
        if self.save and target.exists():
            self.note.text = "That file already exists. Choose a new name to preserve it."
            return
        if not self.save and not target.is_file():
            self.note.text = "Choose an existing file."
            return
        try:
            self.callback(str(target))
        except (OSError, ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        self.dismiss()
