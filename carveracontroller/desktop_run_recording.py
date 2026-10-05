"""Local recording/replay workbench. Never drives live position or commands."""

import logging
import threading
from dataclasses import asdict
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.slider import Slider

from carveracontroller.desktop_components import Action, AdaptiveGrid, Surface
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.run_recording import MAX_ARCHIVE_BYTES, RecordingReplay, RunRecording, selected_context

logger = logging.getLogger(__name__)


class RunRecordingPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.replay = None
        self.busy = False
        self._last_sequence = None
        self._generation = 0
        self.previous_buffer = None
        self.summary = content_label("Local status record · awaiting received packets")
        self.add_widget(self.summary)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        self.start_action = Action("Start bound recording", self.start_recording, primary=True)
        self.previous_action = Action("Inspect previous buffer", self.inspect_previous, disabled=True)
        self.freeze_action = Action("Freeze for replay", self.freeze)
        self.live_action = Action("Return to live buffer", self.return_live)
        self.export_action = Action("Export recording…", self.export)
        self.import_action = Action("Open recording…", self.import_recording)
        for action in (
            self.start_action,
            self.freeze_action,
            self.live_action,
            self.previous_action,
            self.export_action,
            self.import_action,
        ):
            actions.add_widget(action)
        self.add_widget(actions)
        navigation = AdaptiveGrid(max_cols=4, min_width=75, row_height=32, spacing=dp(5))
        for text, offset in (("First", None), ("Previous", -1), ("Next", 1), ("Last", "last")):
            navigation.add_widget(Action(text, lambda offset=offset: self.step(offset)))
        self.add_widget(navigation)
        self.cursor = Slider(min=0, max=1, value=0, step=1, height=dp(32), size_hint_y=None, disabled=True)
        self.cursor.bind(value=lambda *_: self.show_event())
        self.add_widget(self.cursor)
        self.marker_enabled = False
        self.marker_action = Action("Show recorded position", self.toggle_marker, height=dp(36))
        self.add_widget(self.marker_action)
        self.marker_note = content_label(
            "Purple archive marker · uses current scene registration; program binding unverified"
        )
        self.add_widget(self.marker_note)
        self.binding_note = content_label("Buffer has no historical program/setup binding.")
        self.add_widget(self.binding_note)
        self.setup_action = Action("Use recorded stock & offset", self.restore_setup, disabled=True)
        self.add_widget(self.setup_action)
        self.program_action = Action("Open matching program…", self.choose_program, disabled=True)
        self.add_widget(self.program_action)
        self.details = content_label("Freeze the local buffer or open an archive to inspect recorded observations.")
        self.add_widget(self.details)
        self.notice = content_label(
            "Recorded status is separate from Live/Preview. No interpolation, execution inference or machine commands. "
            "Start a bound recording to retain local program/setup selection. Synchronized camera images are not yet recorded."
        )
        self.add_widget(self.notice)

    def _worker(self, work, done):
        if self.busy:
            return
        self.busy = True
        self._generation += 1
        generation = self._generation
        self.notice.text = "Processing the local record…"
        self._paint_actions()

        def run():
            try:
                result, error = work(), None
            except Exception as exc:
                logger.exception("Local run-recording artifact failed")
                result, error = None, str(exc)

            def finish(_dt):
                if generation != self._generation:
                    return
                self.busy = False
                if error is not None:
                    self.notice.text = "Recording unavailable: " + error
                else:
                    done(result)
                self._paint_actions()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=run, daemon=True, name="run-recording-artifact").start()

    def _paint_actions(self):
        for action in (
            self.start_action,
            self.freeze_action,
            self.export_action,
            self.import_action,
            self.live_action,
            self.previous_action,
        ):
            action.disabled = self.busy
        self.live_action.disabled = self.busy or self.replay is None
        self.previous_action.disabled = self.busy or self.previous_buffer is None
        self.setup_action.disabled = self.busy or self.replay is None or "context" not in self.replay.payload
        self.program_action.disabled = self.setup_action.disabled

    def choose_program(self):
        if self.replay is not None and "context" in self.replay.payload:
            self.workspace.choose_profile_file(
                self._open_program, extension=".nc", title="Choose exact recorded program"
            )

    def _open_program(self, filename):
        if self.replay is None:
            return
        replay = self.replay
        root = self.workspace.machine
        directory = Path(root.temp_dir) / "recorded-programs"

        def done(path):
            self.workspace.enter_preview()
            self.workspace.app.selected_remote_filename = ""
            self.workspace.app.selected_local_filename = str(path)
            self.busy = True

            def load_preview():
                error = None
                try:
                    root.load_gcode_file(str(path))
                except Exception as exc:
                    logger.exception("Recorded program preview failed")
                    error = str(exc)

                def finished(_dt):
                    self.busy = False
                    if error:
                        self.notice.text = "Program bytes matched; preview failed: " + error
                    elif self.workspace.app.selected_local_filename != str(path):
                        self.notice.text = "Program selection changed during loading · preview association unverified"
                    elif root.gcode_cannot_visualise:
                        self.notice.text = "Program bytes matched; viewer could not visualize this program"
                    else:
                        self.notice.text = "Matched program preview loaded · executed-line association unverified"
                    self._paint_actions()

                Clock.schedule_once(finished, 0)

            self.preview_loader = threading.Thread(target=load_preview, daemon=True, name="recorded-program-preview")
            self.preview_loader.start()
            self.notice.text = (
                "Exact recorded program bytes matched · local preview loading; executed-line association unverified"
            )

        self._worker(lambda: replay.stage_program(filename, directory), done)

    def restore_setup(self):
        if self.replay is None or "context" not in self.replay.payload:
            return
        setup = self.replay.payload["context"]["setup"]
        self.workspace.machine.gcode_viewer.configure_machine(**setup)
        self.show_event()
        self.notice.text = (
            "Recorded nominal stock/offset applied to local scene · physical setup and tools remain unverified"
        )

    def start_recording(self):
        filename = self.workspace.app.selected_local_filename
        if not filename:
            self.notice.text = "Choose a local program before starting a bound recording."
            return
        setup = asdict(self.workspace.machine.gcode_viewer.machine_setup)

        def done(record):
            controller = self.workspace.machine.controller
            self.previous_buffer = controller.run_recording
            controller.run_recording = record
            self.return_live()
            self.binding_note.text = self._context_text(record.snapshot().get("context"))
            self.notice.text = "New bound buffer active · previous buffer retained for inspection/export"

        self._worker(lambda: RunRecording(context=selected_context(filename, setup)), done)

    def inspect_previous(self):
        if self.previous_buffer is not None:
            self._worker(lambda: RecordingReplay(self.previous_buffer.export_bytes()), self.load)

    @staticmethod
    def _context_text(context):
        if context is None:
            return "No historical program/setup binding in this recording."
        program, setup = context["program"], context["setup"]
        return (
            f"Selected at recording start: {program['name']} · {program['size_bytes']} bytes\n"
            f"SHA-256: {program['sha256']}\n"
            f"Declared work offset mm: {tuple(setup['work_offset_mm'])}\n"
            f"Declared stock origin/size mm: {tuple(setup['stock_origin_mm'])} / {setup['stock_size_mm']}\n"
            "Local selection evidence · machine execution and physical registration unverified"
        )

    def freeze(self):
        self._worker(lambda: RecordingReplay(self.workspace.machine.controller.run_recording.export_bytes()), self.load)

    def load(self, replay):
        self.replay = replay
        self.binding_note.text = self._context_text(replay.payload.get("context"))
        events = replay.payload["events"]
        self.cursor.max = max(1, len(events) - 1)
        self.cursor.disabled = not events
        self.cursor.value = max(0, len(events) - 1)
        self.summary.text = (
            f"Replay · {len(events)} retained events · {replay.payload['dropped_events']} earlier events dropped"
        )
        self.notice.text = (
            "Archive observations only · synchronized images and executed-program attribution unavailable"
        )
        self.details.text = "No events retained in this archive."
        self.show_event()
        self._paint_actions()

    def return_live(self):
        self.replay = None
        self.workspace.machine.gcode_viewer.set_recorded_machine_point(None)
        self._last_sequence = None
        self.cursor.disabled = True
        self.refresh()

    def toggle_marker(self):
        self.marker_enabled = not self.marker_enabled
        self.marker_action.text = "Hide recorded position" if self.marker_enabled else "Show recorded position"
        self.show_event()

    def _update_marker(self, index=None):
        point = self.replay.machine_point(index) if self.marker_enabled and self.replay and index is not None else None
        self.workspace.machine.gcode_viewer.set_recorded_machine_point(point)
        self.marker_note.text = (
            "Purple archive XYZ marker · current scene registration; program binding unverified"
            if point is not None
            else "Recorded marker hidden"
            if not self.marker_enabled
            else "Recorded marker unavailable: needs same-packet XYZ/units and zero rotary angle"
        )

    def refresh(self):
        if self.replay is not None or self.busy:
            return
        # Do not copy the entire run on every heartbeat.
        payload = self.workspace.machine.controller.run_recording.summary()
        latest = payload["latest"]
        sequence = latest["sequence"] if latest else 0
        if sequence == self._last_sequence:
            return
        self._last_sequence = sequence
        self.summary.text = (
            f"Live buffer · {payload['retained_events']} events · {payload['dropped_events']} earlier events dropped"
        )
        self.binding_note.text = self._context_text(payload.get("context"))
        self.details.text = (
            "Latest received state: " + latest["data"]["state"] + f" · monotonic {latest['monotonic_at']:.3f} s"
            if latest and latest["kind"] == "status"
            else "No status packet retained yet"
        )
        self.notice.text = "Freeze for local replay; live machine/camera views continue independently."
        self._paint_actions()

    def step(self, offset):
        if self.replay is None:
            return
        self.cursor.value = 0 if offset is None else self.cursor.max if offset == "last" else self.cursor.value + offset

    def show_event(self):
        if self.replay is None or not self.replay.payload["events"]:
            self._update_marker()
            return
        events = self.replay.payload["events"]
        index = min(int(self.cursor.value), len(events) - 1)
        event = events[index]
        self._update_marker(index)
        heading = (
            f"Event {index + 1}/{len(events)} · sequence {event['sequence']} · connection {event['generation']}\n"
            f"Receive time: UTC epoch {event['utc_at']:.3f} · monotonic {event['monotonic_at']:.3f} s"
        )
        if event["kind"] != "status":
            self.details.text = heading + "\n" + event["kind"].replace("_", " ").title() + " · motion unknown"
            return
        body = event["data"]
        fields = body["fields"]
        units = fields.get("C", [])
        unit = (
            "in"
            if len(units) > 2 and units[2] == 1
            else "mm"
            if len(units) > 2 and units[2] == 0
            else "wire units unknown"
        )
        lines = [heading, "Reported state: " + body["state"]]
        for key, title in (
            ("MPos", "Machine position"),
            ("WPos", "Work position"),
            ("T", "Tool/TLO"),
            ("S", "Spindle report"),
            ("F", "Feed report"),
            ("P", "Program counter report (execution unverified)"),
        ):
            values = fields.get(key)
            lines.append(
                title + ": " + (", ".join(f"{value:g}" for value in values) if values else "not in this packet")
            )
        lines.append("Packet coordinate units: " + unit)
        self.details.text = "\n".join(lines)

    def export(self):
        self.workspace.choose_profile_file(self._export_to, save=True, extension=".cvrun", title="Export run recording")

    def _export_to(self, filename):
        def work():
            data = (
                self.workspace.machine.controller.run_recording.export_bytes()
                if self.replay is None
                else self.replay.export_bytes()
            )
            path = Path(filename)
            with path.open("xb") as stream:
                stream.write(data)
            # Readback validates the actual saved bytes before reporting success.
            RecordingReplay(path.read_bytes())
            return path

        self._worker(work, lambda path: setattr(self.notice, "text", "Saved local recording · " + str(path)))

    def import_recording(self):
        self.workspace.choose_profile_file(self._import_from, extension=".cvrun", title="Open run recording")

    def _import_from(self, filename):
        def work():
            with Path(filename).open("rb") as stream:
                return RecordingReplay(stream.read(MAX_ARCHIVE_BYTES + 1))

        self._worker(work, self.load)
