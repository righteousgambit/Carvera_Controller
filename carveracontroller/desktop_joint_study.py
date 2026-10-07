"""Operator import of a declared, revision-bound joint-motion study."""

import json
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp

from carveracontroller.desktop_components import DANGER, MUTED, Action, AdaptiveGrid, Surface, label
from carveracontroller.desktop_file_picker import ArtifactBrowser
from carveracontroller.machine.inverse_time import analyze_inverse_time
from carveracontroller.machine.joint_motion_study import read_joint_study


class JointStudyImport(Surface):
    def __init__(self, owner):
        super().__init__(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.owner = owner
        self.generation = 0
        self.cancel_event = None
        self.identity = None
        self.running = False
        self.closed = False
        self.browser = None
        self.action = Action("Import joint study…", self.choose, height=dp(30), disabled=True)
        self.identity_action = Action("Copy block identity", self.copy_identity, height=dp(30), disabled=True)
        self.cancel_action = Action("Cancel joint study", self.cancel, height=dp(30))
        self.note = label("", 10, MUTED, 0)
        self.note.bind(width=lambda item, width: setattr(item, "text_size", (max(1, width), None)))
        self.note.bind(
            texture_size=lambda item, size: setattr(item, "height", max(dp(24), size[1]) if item.text else 0)
        )
        actions = AdaptiveGrid(max_cols=2, min_width=140, row_height=30, spacing=dp(4))
        actions.add_widget(self.action)
        actions.add_widget(self.identity_action)
        self.add_widget(actions)
        self.add_widget(self.note)

    def current(self):
        owner = self.owner
        if self.closed or owner.program is None or owner.inspector is None or owner.selected_line is None:
            return None
        block = analyze_inverse_time(owner.inspector.explain(owner.selected_line))
        return (owner.program.file_hash, owner.selected_line, block.seconds) if block.seconds is not None else None

    def refresh(self):
        current = self.current()
        if self.identity is not None and current != self.identity:
            self.cancel(clear=True)
        self.action.disabled = self.running or current is None
        self.identity_action.disabled = current is None

    def copy_identity(self):
        current = self.current()
        if current is None:
            return
        Clipboard.copy(json.dumps({"program_sha256": current[0], "line": current[1], "seconds": current[2]}, indent=2))
        self.note.color = MUTED
        self.note.text = (
            "Copied selected block identity · add the declared machine, joint samples and limits to your study"
        )

    def choose(self):
        identity = self.current()
        if identity is None or self.running:
            return
        self.browser = ArtifactBrowser(
            self.owner.workspace,
            lambda path: self.import_path(path, identity),
            (".json",),
            title="Import declared joint study · schema 1",
        )
        self.browser.open()

    def import_path(self, path, identity=None):
        current = self.current()
        if current is None or (identity is not None and identity != current):
            return
        self.cancel(clear=True)
        self.identity = current
        self.running = True
        generation = self.generation
        cancel = self.cancel_event = threading.Event()
        self.action.disabled = True
        self.add_widget(self.cancel_action, index=1)
        self.note.color = MUTED
        self.note.text = "Reviewing declared joints and tool-tip demand…"

        def work():
            report, error = None, None
            try:
                report = read_joint_study(
                    Path(path),
                    program_sha256=current[0],
                    line=current[1],
                    seconds=current[2],
                    cancelled=cancel.is_set,
                )
            except InterruptedError:
                return
            except (OSError, ValueError) as exc:
                error = str(exc)

            def complete(_dt):
                if self.closed or cancel.is_set() or generation != self.generation or self.current() != current:
                    return
                self.running = False
                if self.cancel_action.parent:
                    self.remove_widget(self.cancel_action)
                self.action.disabled = False
                if error is not None:
                    self.note.color = DANGER
                    self.note.text = error
                    return
                try:
                    self.owner.review_joint_motion(current[0], current[1], report)
                except ValueError as exc:
                    self.note.color = DANGER
                    self.note.text = str(exc)
                    return
                self.note.color = MUTED
                self.note.text = (
                    "Imported declared joint study · sources and content hashes retained · no controller motion"
                )
                self.owner.queue_reveal(self)

            Clock.schedule_once(complete, 0)

        threading.Thread(target=work, daemon=True, name="carvera-joint-study").start()

    def cancel(self, *, clear=False):
        self.generation += 1
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.running = False
        self.identity = None
        if self.cancel_action.parent:
            self.remove_widget(self.cancel_action)
        self.action.disabled = self.current() is None
        self.identity_action.disabled = self.action.disabled
        self.note.color = MUTED
        self.note.text = "" if clear else "Joint-study review cancelled · existing accepted study retained"

    def dispose(self):
        self.closed = True
        self.cancel(clear=True)
        if self.browser is not None:
            self.browser.dismiss()
