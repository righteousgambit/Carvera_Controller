"""Local recording/replay workbench. Never drives live position or commands."""

import io
import logging
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.slider import Slider
from PIL import Image

from carveracontroller.desktop_components import (
    ACCENT,
    Action,
    AdaptiveGrid,
    Choice,
    DesktopFocus,
    Fold,
    Surface,
    displayed_control,
    release_screen_focus,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.camera_run import (
    CameraRunReplay,
    CameraRunWriter,
    export_camera_bundle,
    import_camera_bundle,
)
from carveracontroller.machine.receipt_playback import ReceiptPlayback
from carveracontroller.machine.recorded_jobs import export_recorded_job, import_recorded_job
from carveracontroller.machine.run_recording import MAX_ARCHIVE_BYTES, RecordingReplay, RunRecording, selected_context
from carveracontroller.machine.webcam import CameraFrame

logger = logging.getLogger(__name__)


class ReceiptCursor(DesktopFocus, FocusBehavior, Slider):
    """Keyboard navigation belongs to local replay and never to machine motion."""

    def __init__(self, panel, **kwargs):
        super().__init__(value_track=True, value_track_color=ACCENT, **kwargs)
        self.panel = panel
        with self.canvas.after:
            self._focus_color = Color(*ACCENT[:3], 0)
            self._focus_line = Line(width=dp(1))
        self.bind(focus=self._desktop_focus_changed)
        self.bind(focus=self._paint_focus, pos=self._paint_focus, size=self._paint_focus)
        self._paint_focus()

    def _paint_focus(self, *_args):
        self._focus_color.a = 1 if self.focus else 0
        self._focus_line.rounded_rectangle = (*self.pos, *self.size, dp(5))

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if not self.focus or not displayed_control(self):
            return False
        if not modifiers:
            key = keycode[1]
            if key in ("left", "right", "home", "end"):
                self._activation_key = key
                self.panel.step({"left": -1, "right": 1, "home": None, "end": "last"}[key])
                return True
            if key == "spacebar":
                self._activation_key = key
                self.panel.toggle_playback()
                return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class ReplaySection(Fold):
    """Secondary replay controls retain state and size to their responsive content."""

    def __init__(self, title, widgets):
        body = Surface(orientation="vertical", padding=dp(4), spacing=dp(6), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        for widget in widgets:
            if widget.parent is not None:
                widget.parent.remove_widget(widget)
            body.add_widget(widget)
        super().__init__(title, body)
        body.bind(height=self._resize_body)
        self.toggle.bind(width=self._wrap_heading, texture_size=self._resize_body)
        self._wrap_heading()
        self._resize_body()

    def _wrap_heading(self, *_):
        self.toggle.text_size = (max(1, self.toggle.width - dp(16)), None)
        self.toggle.valign = "middle"

    def _resize_body(self, *_):
        self.body_height = self.content.height
        self.toggle.height = max(dp(32), self.toggle.texture_size[1] + dp(12))
        self.height = self.toggle.height + dp(16) + (dp(6) + self.body_height if self.expanded else 0)

    def set_expanded(self, value):
        if not value:
            release_screen_focus(self.content)
        super().set_expanded(value)
        self._resize_body()


class RunRecordingPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.replay = None
        self.playback = None
        self._playback_event = None
        self._playback_seek = False
        self._playback_missing = False
        self.busy = False
        self._last_sequence = None
        self._generation = 0
        self.previous_buffer = None
        self.included_program = None
        self.setup_archives = {}
        self.camera_writer = None
        self.camera_archive = None
        self.camera_replay_enabled = False
        self.recorded_camera_frame = None
        self.camera_replay_status = "Recorded camera unavailable"
        self._camera_request = 0
        self._camera_decode_busy = False
        self._desired_camera = None
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
        self.cursor = ReceiptCursor(self, min=0, max=1, value=0, step=1, height=dp(32), size_hint_y=None, disabled=True)
        self.cursor_hint = content_label(
            "Timeline keys: Left/Right step · Home/End first/last · Space play/pause receipts"
        )
        self.cursor.bind(value=self._cursor_changed)
        self.add_widget(self.cursor)
        playback_controls = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.playback_action = Action("Play recorded receipts", self.toggle_playback, disabled=True)
        self.playback_speed = Choice(text="1× receipts", values=("0.25× receipts", "1× receipts", "4× receipts"))
        playback_controls.add_widget(self.playback_action)
        playback_controls.add_widget(self.playback_speed)
        self.playback_note = content_label(
            "Local receipt playback · pauses at evidence gaps · never executes a program"
        )
        self.marker_enabled = False
        self.marker_action = Action("Show recorded position", self.toggle_marker, height=dp(36))
        self.add_widget(self.marker_action)
        self.marker_note = content_label(
            "Purple archive marker · uses current scene registration; program binding unverified"
        )
        self.add_widget(self.marker_note)
        self.binding_note = content_label("Buffer has no historical program/setup binding.")
        self.full_binding_note = content_label("No exact file identities in this buffer.")
        self.identity_section = ReplaySection("Full file identities", [self.full_binding_note])
        self.add_widget(self.binding_note)
        self.setup_action = Action("Use recorded stock & offset", self.restore_setup, disabled=True)
        self.historical_action = Action("Load recorded scene & tools", self.restore_historical_scene, disabled=True)
        self.previous_scene_action = Action("Restore previous scene", self.restore_previous_scene, disabled=True)
        self.previous_scene = None
        self.previous_scene_labels = None
        self.recorded_tool_options = {"Follow program": None}
        self._updating_recorded_tools = False
        self.recorded_tool_choice = Choice(text="Follow program", values=("Follow program",), disabled=True)
        self.recorded_tool_choice.bind(text=self._select_recorded_tool)
        self.add_widget(self.setup_action)
        self.program_action = Action("Open matching program…", self.choose_program, disabled=True)
        self.add_widget(self.program_action)
        camera_actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.camera_start_action = Action("Record live camera", self.start_camera)
        self.camera_stop_action = Action("Stop camera recording", self.stop_camera, disabled=True)
        camera_actions.add_widget(self.camera_start_action)
        camera_actions.add_widget(self.camera_stop_action)
        self.add_widget(camera_actions)
        self.camera_note = content_label("Camera recording off · 256 MiB accepted JPEG budget / 10,000 frames per part")
        self.add_widget(self.camera_note)
        archive_actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.camera_open_action = Action("Open camera manifest…", self.choose_camera_archive, disabled=True)
        self.camera_last_action = Action("Use last camera part", self.use_last_camera, disabled=True)
        self.camera_archive_action = Action("Show recorded camera", self.show_recorded_camera, disabled=True)
        self.camera_live_action = Action("Show live camera", self.show_live_camera)
        self.camera_bundle_open = Action("Import camera bundle…", self.choose_camera_bundle, disabled=True)
        self.camera_bundle_save = Action("Export camera bundle…", self.export_camera, disabled=True)
        self.camera_first_observation = Action("First camera observation", self.seek_camera_observation, disabled=True)
        self.camera_last_observation = Action(
            "Last camera observation", lambda: self.seek_camera_observation(last=True), disabled=True
        )
        for action in (
            self.camera_open_action,
            self.camera_last_action,
            self.camera_archive_action,
            self.camera_live_action,
            self.camera_bundle_open,
            self.camera_bundle_save,
            self.camera_first_observation,
            self.camera_last_observation,
        ):
            archive_actions.add_widget(action)
        self.add_widget(archive_actions)
        self.camera_archive_note = content_label("Freeze/open a status recording, then associate its camera manifest.")
        self.add_widget(self.camera_archive_note)
        self.details = content_label("Freeze the local buffer or open an archive to inspect recorded observations.")
        self.add_widget(self.details)
        self.notice = content_label(
            "Recorded status is separate from Live/Preview. No interpolation, execution inference or machine commands. "
            "Start a bound recording to retain local program/setup selection. Camera replay follows local receipt time; exposure timing is unqualified."
        )
        self.add_widget(self.notice)
        # Keep the selected observation beside its timeline. File custody, scene
        # association and camera configuration stay available through disclosure.
        files = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        for action in (self.previous_action, self.export_action, self.import_action):
            actions.remove_widget(action)
            files.add_widget(action)
        self.setup_start_action = Action("Start with setup assets", lambda: self.start_recording(retain_setup=True))
        files.add_widget(self.setup_start_action)
        self.full_run_open = Action("Open full run…", self.choose_full_run)
        self.full_run_save = Action("Export full run…", self.export_full_run, disabled=True)
        self.included_program_action = Action("Open included program", self.open_included_program, disabled=True)
        for action in (self.full_run_open, self.full_run_save, self.included_program_action):
            files.add_widget(action)
        self.observation = content_label("No status observation selected")
        self.packet_section = ReplaySection("Full packet details", [self.details])
        self.files_section = ReplaySection("Recording files & buffers", [files])
        self.scene_section = ReplaySection(
            "Recorded scene & program",
            [
                self.marker_action,
                self.marker_note,
                self.binding_note,
                self.identity_section,
                self.setup_action,
                self.program_action,
                self.historical_action,
                content_label("Archived cutter preview · local geometry only"),
                self.recorded_tool_choice,
                self.previous_scene_action,
            ],
        )
        self.camera_section = ReplaySection(
            "Camera capture & replay", [camera_actions, self.camera_note, archive_actions, self.camera_archive_note]
        )
        self.clear_widgets()
        for widget in (
            self.summary,
            actions,
            navigation,
            self.cursor,
            self.cursor_hint,
            playback_controls,
            self.playback_note,
            self.observation,
            self.notice,
            self.files_section,
            self.scene_section,
            self.camera_section,
            self.packet_section,
        ):
            self.add_widget(widget)

    def _worker(self, work, done):
        if self.busy:
            return
        self.pause_playback()
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
        playing = self.playback is not None and self.playback.running
        self.playback_action.disabled = self.busy or self.playback is None or not self.playback.times
        self.playback_action.text = "Pause recorded receipts" if playing else "Play recorded receipts"
        self.playback_speed.disabled = self.busy or playing
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
        self.historical_action.disabled = (
            self.busy or self.replay is None or self.replay.payload["session_id"] not in self.setup_archives
        )
        self.previous_scene_action.disabled = self.busy or self.previous_scene is None
        self.recorded_tool_choice.disabled = self.busy or self.previous_scene is None
        camera_active = self.camera_writer is not None and self.camera_writer.thread.is_alive()
        camera_state = (
            "recording live" if camera_active else ("viewing archive" if self.camera_replay_enabled else "idle")
        )
        self.camera_section.title = "Camera capture & replay · " + camera_state
        self.camera_section.toggle.text = ("−  " if self.camera_section.expanded else "+  ") + self.camera_section.title
        self.camera_start_action.disabled = self.busy or camera_active
        self.camera_stop_action.disabled = self.busy or not camera_active
        self.start_action.disabled = self.busy or camera_active
        self.setup_start_action.disabled = self.busy or camera_active
        self.camera_open_action.disabled = self.busy or self.replay is None
        self.camera_last_action.disabled = (
            self.busy or self.replay is None or self.camera_writer is None or camera_active
        )
        matching = (
            self.replay is not None
            and self.camera_archive is not None
            and self.camera_archive.header["recording_session_id"] == self.replay.payload["session_id"]
        )
        self.camera_archive_action.disabled = self.busy or not matching
        self.camera_live_action.disabled = not self.camera_replay_enabled
        self.camera_bundle_open.disabled = self.busy or self.replay is None
        self.camera_bundle_save.disabled = self.busy or not matching
        self.camera_first_observation.disabled = self.busy or not matching
        self.camera_last_observation.disabled = self.busy or not matching
        self.full_run_open.disabled = self.busy
        self.full_run_save.disabled = self.busy or self.replay is None or "context" not in self.replay.payload
        self.included_program_action.disabled = self.busy or self.included_program is None

    def choose_full_run(self):
        self.workspace.choose_profile_file(
            self._import_full_run, extension=".cvsession", title="Open full recorded run"
        )

    def _import_full_run(self, filename):
        directory = self.workspace.profile_store.path.parent / "recorded-runs" / "jobs"

        def done(loaded):
            self.show_live_camera()
            self.load(loaded.replay)
            self.included_program = loaded.program
            if loaded.setup_archive is not None:
                self.setup_archives[loaded.replay.payload["session_id"]] = loaded.setup_archive
            self.camera_archive = loaded.camera
            if loaded.camera is not None:
                self._camera_loaded(loaded.camera, loaded.replay.payload["session_id"])
            else:
                self.camera_archive_note.text = "No camera part included in this run."
            self.notice.text = (
                "Full run verified · "
                + ("camera included" if loaded.camera else "no camera part bundled")
                + "; program available for local preview; historical tools/calibration unavailable."
            )

        self._worker(lambda: import_recorded_job(filename, directory), done)

    def export_full_run(self):
        self.workspace.choose_profile_file(
            self._export_full_run, save=True, extension=".cvsession", title="Export full recorded run"
        )

    def _export_full_run(self, filename):
        if self.replay is None:
            return
        replay = self.replay
        program = self.included_program or self.workspace.app.selected_local_filename
        if not program:
            self.notice.text = "Open the matching program before exporting a full run."
            return
        camera = self.camera_archive
        if camera is not None and camera.header["recording_session_id"] != replay.payload["session_id"]:
            self.notice.text = "Associate the matching camera part or return to a recording without camera association."
            return

        def done(receipt):
            self.notice.text = "Full run saved and verified · " + (
                "camera included" if receipt["camera_included"] else "no camera part associated"
            )

        self._worker(
            lambda: export_recorded_job(
                replay, program, filename, camera, self.setup_archives.get(replay.payload["session_id"])
            ),
            done,
        )

    def open_included_program(self):
        if self.included_program is not None:
            self._open_program(str(self.included_program))

    def choose_camera_archive(self):
        self.workspace.choose_profile_file(
            self._import_camera, extension=".jsonl", title="Open recorded camera manifest"
        )

    def use_last_camera(self):
        if self.camera_writer is not None and not self.camera_writer.thread.is_alive():
            self._import_camera(str(self.camera_writer.folder / "frames.jsonl"))

    def _import_camera(self, filename):
        if self.replay is None:
            self.notice.text = "Freeze/open the matching status recording first."
            return
        session = self.replay.payload["session_id"]

        def work():
            manifest = Path(filename)
            if manifest.name != "frames.jsonl":
                raise ValueError("Select the camera part’s frames.jsonl manifest")
            archive = CameraRunReplay(manifest.parent)
            if archive.header["recording_session_id"] != session:
                raise ValueError("Camera manifest belongs to a different status session")
            return archive

        self._worker(work, lambda archive: self._camera_loaded(archive, session))

    def _camera_loaded(self, archive, session):
        if self.replay is None or self.replay.payload["session_id"] != session:
            self.notice.text = "Status selection changed; camera association withheld."
            return
        self.camera_archive = archive
        self.camera_archive_note.text = (
            f"Matched camera part · {len(archive.frames)} frames · "
            + (
                f"{archive.footer['dropped']} missing"
                if archive.footer
                else "partial manifest; final accounting unknown"
            )
            + "\nServer clock/exposure offset and historical registration unqualified"
        )
        self.notice.text = "Camera part validated and associated with the selected status recording."
        self.show_event()

    def choose_camera_bundle(self):
        self.workspace.choose_profile_file(
            self._import_camera_bundle, extension=".cvcamera", title="Import recorded camera bundle"
        )

    def _import_camera_bundle(self, filename):
        if self.replay is None:
            self.notice.text = "Freeze/open the matching status recording first."
            return
        session = self.replay.payload["session_id"]
        directory = self.workspace.profile_store.path.parent / "recorded-runs" / "camera"
        self._worker(
            lambda: import_camera_bundle(filename, directory, session),
            lambda archive: self._camera_loaded(archive, session),
        )

    def export_camera(self):
        self.workspace.choose_profile_file(
            self._export_camera_bundle, save=True, extension=".cvcamera", title="Export recorded camera bundle"
        )

    def _export_camera_bundle(self, filename):
        if self.camera_archive is None:
            return
        archive = self.camera_archive

        def done(receipt):
            self.notice.text = (
                f"Camera bundle saved and verified · {receipt['frames']} frames / {receipt['assets']} JPEG assets"
            )

        self._worker(lambda: export_camera_bundle(archive, filename), done)

    def show_recorded_camera(self):
        if (
            self.replay is None
            or self.camera_archive is None
            or self.camera_archive.header["recording_session_id"] != self.replay.payload["session_id"]
        ):
            return
        self.camera_replay_enabled = True
        self.workspace.camera_texture.update(None)
        self.show_event()
        self._paint_actions()

    def show_live_camera(self):
        self.camera_replay_enabled = False
        self._camera_request += 1
        self._desired_camera = None
        self.recorded_camera_frame = None
        self.workspace.camera_texture.update(None)
        self.workspace._refresh_camera()
        self._paint_actions()

    def seek_camera_observation(self, *, last=False):
        if self.busy or self.replay is None or self.camera_archive is None:
            return
        from carveracontroller.machine.recorded_camera_navigation import camera_observation_index

        try:
            index = camera_observation_index(self.replay, self.camera_archive, last=last)
        except ValueError:
            self.notice.text = "Camera part belongs to another status session; selection preserved."
            return
        if index is None:
            self.notice.text = "No retained status observation overlaps valid camera receipts; selection preserved."
            return
        self.pause_playback()
        self.cursor.value = index
        self.show_recorded_camera()
        self.notice.text = (
            "Camera receipt observation selected · exposure timing and executed motion remain unqualified."
        )

    def _seek_camera(self, event=None):
        self._camera_request += 1
        self.recorded_camera_frame = None
        self._desired_camera = None
        if not self.camera_replay_enabled:
            return
        if self._playback_missing:
            self.camera_replay_status = "Recorded camera · missing telemetry interval / connection boundary"
        elif event is None or event["kind"] != "status":
            self.camera_replay_status = "Recorded camera · no status association at this event"
        elif (
            self.camera_archive is None
            or self.replay is None
            or self.camera_archive.header["recording_session_id"] != self.replay.payload["session_id"]
        ):
            self.camera_replay_status = "Recorded camera · session association unavailable"
        else:
            self._desired_camera = (self.camera_archive, event["monotonic_at"])
            self.camera_replay_status = "Recorded camera · loading selected receipt"
        self.workspace._refresh_camera()
        self._decode_camera()

    def _decode_camera(self):
        if self._camera_decode_busy or self._desired_camera is None:
            return
        archive, timestamp = self._desired_camera
        request = self._camera_request
        self._camera_decode_busy = True

        def run():
            frame, text = None, ""
            try:
                result = archive.at(timestamp)
                receipt = result["frame"]
                if receipt is None:
                    text = "Recorded camera · " + result["reason"]
                else:
                    data = archive.read_frame(receipt)
                    with Image.open(io.BytesIO(data)) as image:
                        if image.format != "JPEG" or image.size != tuple(receipt["size"]):
                            raise ValueError("Recorded JPEG dimensions/format differ")
                        rgb = image.convert("RGB")
                        frame = CameraFrame(
                            rgb.size,
                            rgb.tobytes(),
                            receipt["server_captured_at"],
                            receipt["received_at"],
                            request,
                            data,
                        )
                    text = f"Recorded camera · receipt age {result['receipt_age_seconds']:.2f}s · exposure timing unqualified"
            except Exception:
                text = "Recorded camera unavailable · asset validation/decoding failed"

            def finish(_dt):
                self._camera_decode_busy = False
                if request == self._camera_request and self.camera_replay_enabled:
                    self.recorded_camera_frame = frame
                    self.camera_replay_status = text
                    self.workspace._refresh_camera()
                elif self._desired_camera is not None:
                    self._decode_camera()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=run, name="recorded-camera-decode", daemon=True).start()

    def start_camera(self):
        if self.camera_writer is not None and self.camera_writer.thread.is_alive():
            return
        store = self.workspace.profile_store
        if store is None:
            self.notice.text = "A local profile storage directory is required for camera recording."
            return
        directory = store.path.parent / "recorded-runs" / "camera"
        session = self.workspace.machine.controller.run_recording.session_id

        def done(writer):
            self.camera_writer = writer
            self.workspace.camera_client.set_frame_observer(writer.submit)
            self.camera_note.text = "Camera recording active · " + str(writer.folder)

        self._worker(lambda: CameraRunWriter(directory, session), done)

    def stop_camera(self):
        writer = self.camera_writer
        if writer is None:
            return
        self.workspace.camera_client.set_frame_observer(None)
        writer.request_stop()

        def done(status):
            self.camera_note.text = (
                f"Camera recording saved · {status['written']} frames · {status['dropped']} missing · {writer.folder}"
            )

        self._worker(writer.close, done)

    def shutdown_camera(self):
        self.pause_playback()
        self.workspace.camera_client.set_frame_observer(None)
        if self.camera_writer is not None:
            self.camera_writer.request_stop()

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

    def restore_historical_scene(self):
        if self.busy or self.replay is None:
            return
        ws, replay = self.workspace, self.replay
        archive = self.setup_archives.get(replay.payload["session_id"])
        if archive is None or ws.profile_store is None:
            self.notice.text = "A retained setup archive and local storage are required."
            return
        program = ws.operation_panel.program
        if program is None:
            self.notice.text = "Open the exact recorded program before loading its scene and tools."
            return
        if ws.app.playing or ws.app.state not in ("Idle", "N/A"):
            self.notice.text = "Stop the active run or preview before replacing local scene geometry."
            return
        viewer = ws.machine.gcode_viewer
        filename, cam_table, scale = ws.app.selected_local_filename, viewer.tool_table, viewer.move_scale_by_positon
        cam_tools, cam_scale = deepcopy(cam_table or {}), viewer.tool_unit_scale
        destination = ws.profile_store.path.parent / "recorded-runs" / "preview" / str(uuid4())

        def work():
            from carveracontroller.machine.historical_scene import prepare_historical_scene

            return prepare_historical_scene(
                replay, archive, destination, cam_tools, cam_scale, scale, filename, program.file_hash
            )

        def done(prepared):
            current = ws.operation_panel.program
            if (
                self.replay is not replay
                or ws.app.selected_local_filename != filename
                or viewer.tool_table is not cam_table
                or viewer.move_scale_by_positon != scale
                or current is None
                or current.file_hash != program.file_hash
                or ws.app.playing
                or ws.app.state not in ("Idle", "N/A")
            ):
                self.notice.text = "Prepared assets retained; selection/activity changed, so scene was not applied."
                return
            from carveracontroller.desktop_historical_scene import apply_historical_scene

            try:
                previous = apply_historical_scene(viewer, prepared)
            except Exception:
                logger.exception("Historical scene publication failed")
                self.notice.text = "Historical scene could not be rendered; previous scene restoration attempted."
                return
            if self.previous_scene is None:
                self.previous_scene = previous
                self.previous_scene_labels = (ws.profile_status.text, ws.tool_library_summary.text)
            ws.historical_preview = prepared.context
            self._set_recorded_tools(prepared.definitions)
            ws.profile_status.text = "Recorded setup preview\nArchived tooling · unverified"
            ws.tool_library_summary.text = (
                f"Archived tools: {len(prepared.definitions)} definitions\n"
                "Restore previous scene in Run record to exit."
            )
            ws.enter_preview()
            self.show_event()
            self.notice.text = (
                f"Recorded scene and {len(prepared.definitions)} tools loaded · local preview only. "
                "Physical setup, holder reach and calibration remain unqualified. Restore previous scene to exit."
            )

        self._worker(work, done)

    def restore_previous_scene(self):
        if self.busy or self.previous_scene is None:
            return
        ws, previous = self.workspace, self.previous_scene
        if ws.app.playing or ws.app.state not in ("Idle", "N/A"):
            self.notice.text = "Stop the active run or preview before restoring local scene geometry."
            return
        viewer = ws.machine.gcode_viewer
        filename, cam_table, scale = ws.app.selected_local_filename, viewer.tool_table, viewer.move_scale_by_positon
        cam_tools, cam_scale = deepcopy(cam_table or {}), viewer.tool_unit_scale

        def work():
            from carveracontroller.desktop_historical_scene import prepare_previous_scene

            return prepare_previous_scene(previous, cam_tools, cam_scale, scale)

        def done(result):
            if (
                self.previous_scene is not previous
                or ws.app.selected_local_filename != filename
                or viewer.tool_table is not cam_table
                or viewer.move_scale_by_positon != scale
                or ws.app.playing
                or ws.app.state not in ("Idle", "N/A")
            ):
                self.notice.text = "Selection/activity changed; previous scene remains retained. Try restoration again."
                return
            from carveracontroller.desktop_historical_scene import publish_scene

            try:
                publish_scene(viewer, *result)
            except Exception:
                logger.exception("Previous scene restoration failed")
                self.notice.text = "Previous scene restoration failed; retained state remains available."
                return
            self.previous_scene = None
            ws.historical_preview = None
            self._set_recorded_tools({})
            if self.previous_scene_labels is not None:
                ws.profile_status.text, ws.tool_library_summary.text = self.previous_scene_labels
                self.previous_scene_labels = None
            self.show_event()
            self.notice.text = "Previous local scene and tools restored. Live machine state was not changed."

        self._worker(work, done)

    def _set_recorded_tools(self, definitions):
        self._updating_recorded_tools = True
        try:
            self.recorded_tool_options = {"Follow program": None}
            self.recorded_tool_options.update(
                {
                    f"T{number} · {tool.description or tool.tool_type.value.replace('_', ' ')}": number
                    for number, tool in sorted(definitions.items())
                }
            )
            self.recorded_tool_choice.values = tuple(self.recorded_tool_options)
            self.recorded_tool_choice.text = "Follow program"
        finally:
            self._updating_recorded_tools = False

    def _select_recorded_tool(self, _choice, title):
        if self._updating_recorded_tools or self.busy or self.previous_scene is None:
            return
        number = self.recorded_tool_options.get(title)
        self.workspace.enter_preview()
        self.workspace.machine.gcode_viewer.select_preview_tool(number)
        self.notice.text = (
            "Archived cutter follows the associated program · execution association unverified"
            if number is None
            else f"Archived T{number} geometry shown · physical tool identity unverified"
        )

    def start_recording(self, retain_setup=False):
        if self.previous_scene is not None:
            self.notice.text = "Restore the previous scene before starting a new setup-bound recording."
            return
        if self.camera_writer is not None and self.camera_writer.thread.is_alive():
            self.notice.text = "Stop the current camera recording before starting a new status session."
            return
        filename = self.workspace.app.selected_local_filename
        if not filename:
            self.notice.text = "Choose a local program before starting a bound recording."
            return
        setup = asdict(self.workspace.machine.gcode_viewer.machine_setup)
        job = None
        if retain_setup:
            from carveracontroller.desktop_job_packages import capture_recording_job

            try:
                job = capture_recording_job(self.workspace)
            except ValueError as exc:
                self.notice.text = "Setup snapshot unavailable: " + str(exc)
                return

        def done(result):
            record, archive = result
            if archive is not None:
                self.setup_archives[record.session_id] = archive
            controller = self.workspace.machine.controller
            self.previous_buffer = controller.run_recording
            controller.run_recording = record
            self.return_live()
            self._update_binding(record.snapshot().get("context"))
            self.notice.text = "New bound buffer active · previous buffer retained for inspection/export"

        def work():
            if job is None:
                return RunRecording(context=selected_context(filename, setup)), None
            from carveracontroller.machine.recording_setup import bind_recording_setup

            directory = self.workspace.profile_store.path.parent / "recorded-runs" / "setup"
            return bind_recording_setup(filename, setup, job, directory)

        self._worker(work, done)

    def inspect_previous(self):
        if self.previous_buffer is not None:
            self._worker(lambda: RecordingReplay(self.previous_buffer.export_bytes()), self.load)

    @staticmethod
    def _context_text(context, *, exact=False):
        if context is None:
            return "No historical program/setup binding in this recording."
        program, setup = context["program"], context["setup"]
        suffix = "" if exact else " prefix"
        program_digest = program["sha256"] if exact else program["sha256"][:12]
        configuration = context.get("configuration")
        archive_text = "Setup assets not retained"
        if configuration:
            digest = configuration["sha256"] if exact else configuration["sha256"][:12]
            archive_text = f"Setup archive bound · SHA-256{suffix}: {digest}"
        return (
            f"Selected at recording start: {program['name']} · {program['size_bytes']} bytes\n"
            f"SHA-256{suffix}: {program_digest}\n"
            f"Declared work offset mm: {tuple(setup['work_offset_mm'])}\n"
            f"Declared stock origin/size mm: {tuple(setup['stock_origin_mm'])} / {setup['stock_size_mm']}\n"
            f"{archive_text}\n"
            "Local selection evidence · machine execution and physical registration unverified"
        )

    def _update_binding(self, context):
        self.binding_note.text = self._context_text(context)
        self.full_binding_note.text = self._context_text(context, exact=True)

    def freeze(self):
        self._worker(lambda: RecordingReplay(self.workspace.machine.controller.run_recording.export_bytes()), self.load)

    def load(self, replay):
        self.pause_playback()
        self._playback_missing = False
        self.replay = replay
        self.playback = ReceiptPlayback(replay)
        self.included_program = None
        if (
            self.camera_archive is not None
            and self.camera_archive.header["recording_session_id"] != replay.payload["session_id"]
        ):
            self.show_live_camera()
            self.camera_archive = None
            self.camera_archive_note.text = "Associate a camera part matching this status recording."
        self._update_binding(replay.payload.get("context"))
        events = replay.payload["events"]
        self.cursor.max = max(1, len(events) - 1)
        self.cursor.disabled = not events
        self.cursor.value = max(0, len(events) - 1)
        self.summary.text = (
            f"Replay · {len(events)} retained events · {replay.payload['dropped_events']} earlier events dropped"
        )
        self.notice.text = "Archive observations · associate a camera part for receipt-time replay; executed-program attribution unverified"
        self.details.text = "No events retained in this archive."
        self.observation.text = self.details.text
        self.show_event()
        self._paint_actions()

    def return_live(self):
        self.pause_playback()
        self._playback_missing = False
        self.replay = None
        self.playback = None
        self.included_program = None
        self.show_live_camera()
        self.workspace.machine.gcode_viewer.set_recorded_machine_point(None)
        self._last_sequence = None
        self.cursor.disabled = True
        self.refresh()

    def toggle_marker(self):
        self.marker_enabled = not self.marker_enabled
        self.marker_action.text = "Hide recorded position" if self.marker_enabled else "Show recorded position"
        self.show_event()

    def _update_marker(self, index=None):
        point = (
            self.replay.machine_point(index)
            if self.marker_enabled and self.replay and index is not None and not self._playback_missing
            else None
        )
        self.workspace.machine.gcode_viewer.set_recorded_machine_point(point)
        self.marker_note.text = (
            "Purple archive XYZ marker · current scene registration; program binding unverified"
            if point is not None
            else "Recorded marker withheld · missing telemetry interval / connection boundary"
            if self._playback_missing
            else "Recorded marker hidden"
            if not self.marker_enabled
            else "Recorded marker unavailable: needs same-packet XYZ/units and zero rotary angle"
        )

    def refresh(self):
        if self.camera_writer is not None:
            status = self.camera_writer.status()
            self.camera_note.text = (
                f"Camera archive · {status['written']} written · {status['dropped']} missing"
                + (" · " + status["error"] if status["error"] else "")
                + (" · writer stopped" if status["closed"] else " · writer active")
            )
            self._paint_actions()
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
        self._update_binding(payload.get("context"))
        self.details.text = (
            "Latest received state: " + latest["data"]["state"] + f" · monotonic {latest['monotonic_at']:.3f} s"
            if latest and latest["kind"] == "status"
            else "No status packet retained yet"
        )
        self.observation.text = self.details.text
        self.notice.text = "Freeze for local replay; live machine/camera views continue independently."
        self._paint_actions()

    def step(self, offset):
        if self.replay is None:
            return
        self.pause_playback()
        self.cursor.value = 0 if offset is None else self.cursor.max if offset == "last" else self.cursor.value + offset

    def _cursor_changed(self, *_args):
        if not self._playback_seek:
            self.pause_playback()
        self._playback_missing = False
        self.show_event()

    def pause_playback(self):
        if self.playback is not None:
            self.playback.pause()
        if self._playback_event is not None:
            self._playback_event.cancel()
            self._playback_event = None
        if hasattr(self, "playback_action"):
            self.playback_action.text = "Play recorded receipts"
            self.playback_speed.disabled = self.busy

    def toggle_playback(self):
        if self.busy or self.playback is None or not self.playback.times:
            return
        if self.playback.running:
            self.pause_playback()
            self.playback_note.text = (
                "Receipt playback paused in a missing interval · motion remains unknown"
                if self._playback_missing
                else "Receipt playback paused · selected observations remain visible"
            )
            return
        if int(self.cursor.value) >= len(self.playback.times) - 1:
            self.cursor.value = 0
        speed = {"0.25× receipts": 0.25, "1× receipts": 1, "4× receipts": 4}[self.playback_speed.text]
        self.playback.play(int(self.cursor.value), time.monotonic(), speed)
        self._playback_missing = False
        self.show_event()
        self.playback_note.text = f"Playing receipt intervals at {speed:g}× · observations only; pauses at gaps"
        self._playback_event = Clock.schedule_interval(self._advance_playback, 0.05)
        self._paint_actions()

    def _advance_playback(self, _dt):
        if self.busy or self.replay is None or self.playback is None or not self.playback.running:
            self.pause_playback()
            return False
        try:
            result = self.playback.advance(time.monotonic())
        except ValueError:
            self.pause_playback()
            self.playback_note.text = "Receipt playback paused · local clock invalid"
            return False
        if int(self.cursor.value) != result.index:
            self._playback_seek = True
            try:
                self.cursor.value = result.index
            finally:
                self._playback_seek = False
        if result.missing and not self._playback_missing:
            self._playback_missing = True
            self.workspace.machine.gcode_viewer.set_recorded_machine_point(None)
            self._seek_camera()
            self.observation.text = "Missing telemetry / connection boundary · recorded motion unknown"
        if not result.running:
            self.pause_playback()
            self.playback_note.text = (
                "Paused at " + result.reason.replace("_", " ") + " · review this boundary, then explicitly resume"
                if result.missing
                else "End of retained receipts · playback stopped"
            )
            return False
        return True

    def show_event(self):
        if self._playback_missing:
            self._update_marker()
            self._seek_camera()
            self.observation.text = "Missing telemetry / connection boundary · recorded motion unknown"
            return
        if self.replay is None or not self.replay.payload["events"]:
            self._update_marker()
            self._seek_camera()
            return
        events = self.replay.payload["events"]
        index = min(int(self.cursor.value), len(events) - 1)
        event = events[index]
        self._seek_camera(event)
        self._update_marker(index)
        heading = (
            f"Event {index + 1}/{len(events)} · sequence {event['sequence']} · connection {event['generation']}\n"
            f"Receive time: UTC epoch {event['utc_at']:.3f} · monotonic {event['monotonic_at']:.3f} s"
        )
        if event["kind"] != "status":
            self.details.text = heading + "\n" + event["kind"].replace("_", " ").title() + " · motion unknown"
            if event["kind"] == "gap":
                self.details.text += f"\nMissing interval: {event['data']['duration_seconds']:g} seconds"
            self.observation.text = (
                f"Archive event {index + 1}/{len(events)} · "
                + event["kind"].replace("_", " ").title()
                + " · motion unknown"
            )
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
        tool, spindle = fields.get("T", []), fields.get("S", [])
        self.observation.text = (
            f"Archive event {index + 1}/{len(events)} · reported {body['state']}\n"
            + (f"Reported T{tool[0]:g}" if tool else "Tool unknown")
            + " · "
            + (f"Actual RPM report {spindle[0]:g}" if spindle else "RPM unknown")
            + " · receipt-time observation"
        )

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
