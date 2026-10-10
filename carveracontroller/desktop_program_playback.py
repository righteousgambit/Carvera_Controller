"""Feed-aware loaded-program playback; no machine commands or setup mutation."""

from fractions import Fraction as F
from math import floor
from time import monotonic

from carveracontroller.desktop_components import Action
from carveracontroller.desktop_contact_pose import ContactPoseStage
from carveracontroller.desktop_generated_playback import GeneratedPlaybackControls
from carveracontroller.desktop_planning import planning_field
from carveracontroller.machine.contact_pose_view import prepare_path_pose_view
from carveracontroller.machine.program_playback_material import ProgramMaterialCursor, prepare_program_material
from carveracontroller.machine.program_playback_preparation import prepare_program_playback
from carveracontroller.machine.program_playback_timing import PlaybackClock, prepare_program_timing


class ProgramPlaybackControls(GeneratedPlaybackControls):
    def __init__(self, surfaces):
        self.surfaces = surfaces
        self.preparation = self.nominal_retained = None
        self.timing = self.clock = self.gap = None
        self.last_tick = None
        super().__init__(
            surfaces,
            title="Loaded program playback",
            state_title="Material representation",
            advance_title="Nominal playback speed",
        )
        self.advance.values = ("1×", "2×", "5×", "10×")
        self.advance.text = "1×"
        self.rapid = planning_field(self.content, "Rapid estimate · mm/min (blank = unknown)", "", multiline=False)
        self.rapid.bind(text=self.timing_changed)
        self.continue_action = Action("Continue after timing gap", self.continue_after_gap, disabled=True)
        self.content.add_widget(self.continue_action)
        self.prepare_action = Action("Prepare nominal playback", self.prepare)
        self.content.add_widget(self.prepare_action, index=len(self.content.children))
        self.qualification.text = (
            "Nominal feed/chord timing, with a declared rapid estimate. Acceleration, overrides, spindle settling and live registration remain unqualified. "
            "Timing gaps pause playback. Manual seeks acknowledge earlier gaps. Slow rendering can skip display frames; every preceding cut is still replayed."
        )
        self.status.text = "Prepare nominal playback or use a retained surface review; choose ordered stock to show remaining material."

    @property
    def owner(self):
        return self.surfaces.review.card.owner

    @property
    def source(self):
        return self.preparation.scene if self.preparation is not None else self.surfaces.result

    @property
    def retained(self):
        return self.nominal_retained if self.preparation is not None else self.surfaces.review.retained_inputs

    def prepare(self):
        if self.owner.closed or self.owner.running:
            return
        try:
            source, captures, offsets, start, end = self.surfaces.review.inputs(False)
            resolution = (
                self.surfaces.stock_resolution.value()
                if self.surfaces.stock_mode.text == "Initial CAD + ordered stock"
                else None
            )
        except (ValueError, ArithmeticError) as exc:
            self.status.text = str(exc)
            return
        self.close()
        self.status.text = "Preparing complete nominal machine, tools and material · clearance is not being reviewed."

        def completed(preparation):
            try:
                current = self.surfaces.review.inputs(False)
                same = (
                    current[0].motion is source.motion
                    and current[0].file_hash == source.file_hash
                    and current[0].parse_settings == source.parse_settings
                    and current[2] == offsets
                    and {t: c.digest for t, c in current[1].items()} == {t: c.digest for t, c in captures.items()}
                )
            except (ValueError, ArithmeticError):
                same = False
            if not same:
                self.status.text = "Program or scene changed; nominal preparation withheld."
                return
            self.preparation, self.nominal_retained = preparation, (source, dict(offsets))
            self.timing = self.clock = self.gap = self.cursor = None
            self.position = F(0)
            self.reflect_position(self.position)
            self.status.text = "Nominal playback prepared · clearance has not been reviewed."
            self.set_busy(False)

        self.owner._start(
            lambda cancelled: prepare_program_playback(
                source, captures, offsets, stock_resolution_mm=resolution, cancelled=cancelled
            ),
            completed,
            error_target=self.status,
        )

    def set_busy(self, busy):
        source = self.source
        available = source is not None and self.retained is not None and not self.owner.closed
        if hasattr(self, "prepare_action"):
            self.prepare_action.disabled = self.owner.closed or busy
        for widget in (
            self.view,
            self.play,
            self.first,
            self.previous,
            self.next,
            self.last,
            self.move,
            self.fraction,
            self.state,
            self.timeline,
        ):
            widget.disabled = not available or (busy and not self.inflight)
        self.stop.disabled = not (self.playing or self.inflight)
        self.fit.disabled = self.back.disabled = self.visibility.disabled = self.stage is None
        if hasattr(self, "continue_action"):
            self.continue_action.disabled = self.gap is None or busy or not available
        if source is not None:
            self.syncing = True
            self.timeline.max = len(source.body_review.segments)
            values = (
                ("Remaining ordered stock", "Initial CAD") if source.stock_evolution is not None else ("Initial CAD",)
            )
            self.state.values = values
            if self.state.text not in values:
                self.state.text = values[0]
            self.syncing = False

    def clear(self):
        self.close()
        self.preparation = self.nominal_retained = None
        self.timing = self.clock = self.gap = self.last_tick = None
        self.position = F(0)
        self.syncing = True
        self.timeline.value = 0
        self.move.text, self.fraction.text = "1", "0"
        self.syncing = False
        self.status.text = "Prepare the current loaded program for nominal playback."
        self.set_busy(False)

    def timing_changed(self, *_):
        self.pause()
        self.timing = self.clock = self.gap = None
        self.set_busy(self.owner.running)

    def seek_last(self):
        if self.source is not None:
            self.seek(F(len(self.source.body_review.segments)))

    def seek(self, position):
        source = self.source
        if source is not None and source.body_review.segments:
            self.reflect_position(min(F(len(source.body_review.segments)), max(F(0), position)))
            self.request()

    def reflect_position(self, position):
        source = self.source
        if source is None or not source.body_review.segments:
            return
        index = min(floor(position), len(source.body_review.segments) - 1)
        self.syncing = True
        self.move.text, self.fraction.text = str(index + 1), str(position - index)
        self.timeline.value = float(position)
        self.syncing = False

    def current_source(self, source, retained):
        # Detached archives remain bound to their retained report. Live parser
        # replacement invalidates the view even if the file bytes are identical.
        program = self.owner.workspace.operation_panel.program
        return (
            not self.owner.closed
            and self.source is source
            and self.retained is retained
            and (
                program is None
                or (
                    program.file_hash == retained[0].file_hash
                    and program.motion_segments is retained[0].motion
                    and program.parse_settings == retained[0].parse_settings
                )
            )
        )

    def request(self, *, clock=None, timed=False, seconds=0):
        source, retained = self.source, self.retained
        if source is None or retained is None or self.owner.closed:
            return
        try:
            if len(self.move.text) > 16 or len(self.fraction.text) > 128 or len(self.rapid.text) > 32:
                raise ValueError("Playback inputs exceed bounded sizes")
            index, sample = int(self.move.text) - 1, F(self.fraction.text)
            if not 0 <= index < len(source.body_review.segments) or not 0 <= sample <= 1 or sample.denominator > 10**12:
                raise ValueError("Choose a retained move and fraction from 0 to 1")
            rapid = float(self.rapid.text) if self.rapid.text.strip() else None
            if not self.current_source(source, retained):
                raise ValueError("Loaded program changed; prepare its nominal scene or review its surfaces again")
            if self.state.text not in self.state.values:
                raise ValueError("Choose a retained material representation")
        except (ValueError, ArithmeticError) as exc:
            self.status.text = str(exc)
            self.pause(restore_position=False)
            return
        self.generation += 1
        self.pending = (source, retained, index, sample, self.state.text, rapid, self.generation, clock, timed, seconds)
        self.status.text = f"Preparing L{source.body_review.segments[index].line} · previous complete image retained."
        self.keep_ticking()
        self.tick()

    def toggle_play(self):
        if self.playing:
            self.pause()
            return
        self.playing = True
        self.play.text = "Pause play"
        self.last_tick = monotonic()
        # First play covers the source prefix; subsequent manual seeks are
        # explicit starting points, with previous gaps acknowledged.
        self.request(clock=self.clock or PlaybackClock(), timed=True)

    def continue_after_gap(self):
        if self.gap is None or self.clock is None:
            return
        self.clock = PlaybackClock(self.clock.span + 1, F(0), self.clock.elapsed_seconds)
        self.gap = None
        self.toggle_play()

    def tick(self, *_):
        if self.owner.closed or (self.stage is not None and not self.stage.current()):
            self.close()
            return False
        if self.inflight:
            if self.owner.running:
                return None
            self.inflight = False
            if not self.delivered and self.pending is None:
                self.playing = False
                self.play.text = "Play"
        if self.owner.running:
            return None
        if self.pending is not None:
            request, self.pending = self.pending, None
            self.launch(request)
            return None
        canvas = self.stage.canvas if self.stage is not None else None
        if canvas is not None and (canvas.projecting or canvas.pending is not None or canvas.trigger.is_triggered):
            return None
        if canvas is not None and canvas.displayed_scene is not canvas.scene:
            self.pause()
            self.status.text = (
                canvas.projection_error or "Frame display unavailable"
            ) + " · Playback paused; previous image retained."
        if self.playing and self.stage is not None and self.timing is not None and self.clock is not None:
            now = monotonic()
            seconds = min(3600, max(0, now - (self.last_tick or now)) * int(self.advance.text[:-1]))
            self.last_tick = now
            self.request(clock=self.clock, timed=True, seconds=seconds)
            return None
        if not self.inflight and self.pending is None and not self.playing:
            self.set_busy(False)
            self.event = None
            return False

    def launch(self, request):
        source, retained, index, sample, state, rapid, generation, requested_clock, timed, seconds = request
        if self.cursor is None or self.cursor.source is not source:
            self.cursor = ProgramMaterialCursor(source)
        cursor = self.cursor
        self.inflight, self.delivered = True, False

        def current():
            return self.current_source(source, retained)

        def work(cancelled):
            def stopped():
                return cancelled() or generation != self.generation or not current()

            timing = self.timing
            expected_rapid = (
                rapid
                if rapid is not None
                else (retained[0].parse_settings.rapid_mm_min if retained[0].parse_settings is not None else None)
            )
            if (
                timing is None
                or timing.source is not retained[0]
                or timing.body is not source.body_review
                or timing.rapid_mm_min != expected_rapid
            ):
                timing = prepare_program_timing(
                    retained[0], source.body_review, retained[1], rapid_mm_min=rapid, cancelled=stopped
                )
            frame_index, frame_sample = index, sample
            advance = timing.advance(requested_clock, seconds) if timed else None
            if advance is not None:
                frame_index = min(floor(advance.position), len(source.body_review.segments) - 1)
                frame_sample = advance.position - frame_index
            scene = prepare_path_pose_view(
                source,
                int(source.body_review.segments[frame_index].tool_id),
                frame_index,
                frame_sample,
                cancelled=stopped,
            )
            material = (
                prepare_program_material(source, scene, cursor=cursor, cancelled=stopped)
                if state == "Remaining ordered stock"
                else None
            )
            clock = advance.clock if advance is not None else timing.seek(frame_index, frame_sample)
            return (
                timing,
                material.view if material is not None else scene,
                material,
                clock,
                advance,
                frame_index,
                frame_sample,
            )

        def complete(value):
            if not current() or generation != self.generation or state != self.state.text:
                self.status.text = "Playback inputs changed; frame withheld."
                return
            timing, scene, material, clock, advance, frame_index, frame_sample = value
            index, sample = frame_index, frame_sample
            self.delivered = True
            self.timing = timing
            self.clock = clock
            self.gap = advance.gap if advance is not None else None
            if advance is not None and (advance.gap is not None or advance.done):
                self.playing = False
                self.play.text = "Play"
            self.position = F(index) + sample
            self.reflect_position(self.position)
            segment = source.body_review.segments[index]
            caption = f"Loaded program playback · L{segment.line} · T{segment.tool_id} · {index + 1}/{len(source.body_review.segments)} · {100 * float(sample):.1f}% · Esc to return"
            if self.preparation is not None:
                caption = "Nominal · clearance not reviewed · " + caption

            def closed():
                self.stage = None
                self.pause()
                self.cursor = None
                self.status.text = "Program view restored. Retained playback inputs remain available."

            if self.stage is None:
                self.stage = ContactPoseStage(
                    self.owner.workspace, scene, self.display_status, current, closed, caption=caption
                )
            else:
                self.stage.update_scene(scene, caption)
            self.stage.program_material = material
            self.visibility.values = ("All bodies", "Machine only", "Stock and target") + tuple(
                b.name for b in scene.bodies
            )
            if self.visibility.text not in self.visibility.values:
                self.visibility.text = "All bodies"
            self.show_bodies()
            material_text = (
                "; ".join(f"{name}: {volume:g} mm³" for name, volume in material.remaining_mm3.items())
                if material is not None
                else "Initial declared CAD · material removal not displayed"
            )
            gaps = timing.gap_count
            self.summary = f"L{segment.line} · T{segment.tool_id} · move {index + 1}/{len(source.body_review.segments)} at {sample}\n{material_text}\n{self.clock.elapsed_seconds:.2f}s known elapsed / {timing.known_seconds:.2f}s known duration · {gaps} timing gaps · nominal polyline estimate"
            if self.preparation is not None:
                self.summary += "\nClearance has not been reviewed for this nominal preparation."
            if self.clock.span == len(timing.spans):
                self.summary += "\nEnd of retained program."
            if self.gap is not None:
                self.summary += f"\nTiming gap at L{self.gap.line}: {self.gap.reason}. Continue explicitly; unknown time remains excluded."
            self.status.text = self.summary
            self.set_busy(False)

        self.owner._start(work, complete, error_target=self.status)
