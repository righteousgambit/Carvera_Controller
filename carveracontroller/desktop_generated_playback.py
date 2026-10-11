"""Completion-paced generated-path material playback in the existing workspace."""

from __future__ import annotations

from fractions import Fraction as F
from math import floor, isfinite

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.slider import Slider

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_contact_pose import ContactPoseStage
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.contact_pose_material import MaterialCursor, prepare_contact_material
from carveracontroller.machine.contact_pose_view import prepare_path_pose_view


class GeneratedPlaybackControls(PlanningCard):
    def __init__(
        self,
        controller,
        *,
        title="Material playback",
        state_title="Starting stock state",
        advance_title="Advance per displayed frame",
    ):
        super().__init__(title)
        self.controller = controller
        self.stage = self.cursor = self.event = None
        self.pending = None
        self.generation = 0
        self.playing = self.inflight = self.delivered = self.syncing = False
        self.position = F(0)
        options = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.move = planning_field(options, "Move · one based", "1", multiline=False)
        self.fraction = planning_field(options, "Within move · 0–1", "0", multiline=False)
        self.state = planning_choice(options, state_title, ("No machine review",))
        self.advance = planning_choice(options, advance_title, ("Whole move", "Quarter move"))
        self.content.add_widget(options)
        self.timeline = Slider(min=0, max=1, value=0, size_hint_y=None, height=dp(32))
        self.timeline.bind(value=self.scrub)
        self.content.add_widget(self.timeline)
        actions = AdaptiveGrid(max_cols=3, min_width=105, row_height=36, spacing=dp(6))
        self.view = Action("View frame", self.request)
        self.play = Action("Play", self.toggle_play)
        self.stop = Action("Pause", self.pause)
        self.first = Action("First", lambda: self.seek(F(0)))
        self.previous = Action("Previous", lambda: self.seek(max(F(0), self.position - 1)))
        self.next = Action("Next", lambda: self.seek(self.position + 1))
        self.last = Action("Last", self.seek_last)
        self.fit = Action("Fit", self.fit_view)
        self.back = Action("Return", self.close)
        for action in (
            self.view,
            self.play,
            self.stop,
            self.first,
            self.previous,
            self.next,
            self.last,
            self.fit,
            self.back,
        ):
            actions.add_widget(action)
        self.content.add_widget(actions)
        self.visibility = planning_choice(
            self.content, "Playback visibility", ("All bodies", "Machine only", "Stock and target")
        )
        self.visibility.bind(text=self.show_bodies)
        self.state.bind(text=self.state_changed)
        for field in (self.move, self.fraction):
            field.bind(on_text_validate=lambda *_: self.request())
        self.status = flowing_text(
            "Review a complete generated machine path first. Playback is a local simulation.", 45
        )
        self.content.add_widget(self.status)
        self.qualification = flowing_text(
            "Blue: remaining cells · purple: target · amber: missing CAD. Frames advance when calculation and display finish; this is not feed-rate timing or live machine motion.",
            45,
        )
        self.content.add_widget(self.qualification)
        self.set_busy(False)

    @property
    def owner(self):
        return self.controller.owner

    def set_busy(self, busy):
        source = self.controller.result
        available = source is not None and not self.owner.closed
        own_work = self.inflight
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
            widget.disabled = not available or (busy and not own_work)
        self.stop.disabled = not (self.playing or own_work)
        self.fit.disabled = self.back.disabled = self.stage is None
        self.visibility.disabled = self.stage is None
        if source is not None:
            self.syncing = True
            self.timeline.max = len(source.plan.moves)
            values = tuple(source.plan.states)
            self.state.values = values
            if self.state.text not in values:
                self.state.text = values[0]
            self.syncing = False

    def keep_ticking(self):
        if self.event is None:
            self.event = Clock.schedule_interval(self.tick, 0.1)

    def pause(self, restore_position=True):
        self.playing = False
        self.play.text = "Play"
        self.pending = None
        self.generation += 1
        if self.inflight:
            self.owner.cancel()
        if restore_position:
            self.reflect_position(self.position)
        self.set_busy(self.owner.running)

    def close(self):
        self.pause()
        if self.stage is not None:
            self.stage.close()
        if self.event is not None:
            self.event.cancel()
            self.event = None
        self.cursor = None
        # A closed stage no longer owns delivery. The worker still drains via
        # its owner, but no stopped timer is needed to clear this UI flag.
        self.inflight = self.delivered = False

    def clear(self):
        self.close()
        self.syncing = True
        self.state.values = ("No machine review",)
        self.state.text = self.state.values[0]
        self.timeline.value = 0
        self.move.text, self.fraction.text = "1", "0"
        self.syncing = False
        self.position = F(0)
        self.status.text = "Review the current complete generated machine path first."

    def state_changed(self, *_):
        if not self.syncing and (self.stage is not None or self.inflight):
            self.request()

    def scrub(self, _slider, value):
        if not self.syncing and isfinite(value):
            self.seek(F(str(value)).limit_denominator(1_000_000))

    def seek_last(self):
        if self.controller.result is not None:
            self.seek(F(len(self.controller.result.plan.moves)))

    def seek(self, position):
        source = self.controller.result
        if source is None:
            return
        position = min(F(len(source.plan.moves)), max(F(0), position))
        self.reflect_position(position)
        self.request()

    def reflect_position(self, position):
        source = self.controller.result
        if source is None:
            return
        index = min(floor(position), len(source.plan.moves) - 1)
        self.syncing = True
        self.move.text, self.fraction.text = str(index + 1), str(position - index)
        self.timeline.value = float(position)
        self.syncing = False

    def request(self):
        source = self.controller.result
        if source is None or self.owner.closed:
            return
        try:
            if len(self.move.text) > 16 or len(self.fraction.text) > 128:
                raise ValueError("Playback move or fraction input exceeds its bounded size")
            index, sample = int(self.move.text) - 1, F(self.fraction.text)
            if not 0 <= index < len(source.plan.moves) or not 0 <= sample <= 1 or sample.denominator > 10**12:
                raise ValueError("Choose a retained move and a finite fraction from 0 to 1")
            if self.state.text not in source.plan.states:
                raise ValueError("Choose a retained independent starting stock state")
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            self.status.text = str(exc)
            self.pause(restore_position=False)
            return
        self.generation += 1
        self.pending = (source, index, sample, self.state.text, self.generation)
        self.status.text = (
            f"Requested move {index + 1} at {sample} · previous displayed frame retained while preparing."
        )
        self.keep_ticking()
        self.tick()

    def toggle_play(self):
        if self.controller.result is None or self.owner.closed:
            return
        if self.playing:
            self.pause()
            return
        self.playing = True
        self.play.text = "Pause play"
        self.request()

    def tick(self, *_):
        if self.owner.closed:
            self.close()
            return False
        if self.stage is not None and not self.stage.current():
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
            self.playing = False
            self.play.text = "Play"
            self.status.text = (
                canvas.projection_error or "Frame display unavailable"
            ) + " · Playback paused; previous image retained."
        if self.playing and self.stage is not None:
            count = len(self.controller.result.plan.moves)
            if self.position >= count:
                self.playing = False
                self.play.text = "Play"
                self.status.text += "\nEnd of generated path."
            else:
                self.seek(self.position + (F(1) if self.advance.text == "Whole move" else F(1, 4)))
                return None
        if not self.inflight and self.pending is None and not self.playing:
            self.set_busy(False)
            self.event = None
            return False

    def launch(self, request):
        source, index, sample, state, generation = request
        if self.cursor is None or self.cursor.source is not source or self.cursor.state != state:
            self.cursor = MaterialCursor(source, state)
        cursor = self.cursor
        previous = self.stage.canvas.displayed_scene if self.stage is not None else None
        self.inflight, self.delivered = True, False

        def current_source():
            return (
                not self.owner.closed
                and self.controller.result is source
                and self.controller.generated.result is source.plan
                and self.controller.generated.target.sections.surfaces.result is source.parent
            )

        def work(cancelled):
            def stopped():
                return cancelled() or generation != self.generation or not current_source()

            scene = prepare_path_pose_view(
                source.scene, source.plan.tool, index, sample, previous=previous, cancelled=stopped
            )
            return prepare_contact_material(source, scene, state, cursor=cursor, cancelled=stopped)

        def complete(material):
            if not current_source() or generation != self.generation or state != self.state.text:
                self.status.text = "Playback inputs changed; frame withheld."
                return
            self.delivered = True
            self.position = F(index) + sample
            self.reflect_position(self.position)
            scene = material.view
            move = source.plan.moves[index]
            caption = f"Generated playback · T{source.plan.tool} · move {index + 1}/{len(source.plan.moves)} · {move.kind} · {100 * float(sample):.1f}% · Esc to return"

            def closed():
                self.stage = None
                self.pause()
                self.cursor = None
                self.status.text = "Program view restored. Generated simulation remains retained."

            if self.stage is None:
                self.controller.close_pose()
                self.stage = ContactPoseStage(
                    self.owner.workspace, scene, self.display_status, current_source, closed, caption=caption
                )
            else:
                self.stage.update_scene(scene, caption)
            self.stage.material = material
            self.visibility.values = ("All bodies", "Machine only", "Stock and target") + tuple(
                b.name for b in scene.bodies
            )
            if self.visibility.text not in self.visibility.values:
                self.visibility.text = "All bodies"
            self.show_bodies()
            self.summary = f"Move {index + 1}/{len(source.plan.moves)} · {move.kind} · layer {move.layer} · t={sample}\n{state}: {material.remaining_mm3:g} mm³ remaining / {material.removed_mm3:g} mm³ removed · {material.replayed_moves} moves replayed for this frame."
            self.status.text = self.summary
            self.set_busy(False)

        self.owner._start(work, complete, error_target=self.status)

    def display_status(self, text):
        self.status.text = getattr(self, "summary", "") + "\n" + text

    def show_bodies(self, *_):
        if self.stage is None:
            return
        canvas = self.stage.canvas
        bodies = canvas.scene.bodies
        value = self.visibility.text
        names = (
            tuple(b.name for b in bodies)
            if value == "All bodies"
            else tuple(b.name for b in bodies if b.kind == "cad")
            if value == "Machine only"
            else tuple(b.name for b in bodies if b.kind in ("remaining", "target"))
            if value == "Stock and target"
            else (value,)
        )
        if canvas.names != names:
            # Keep the user's orbit/zoom/pan while the material changes.
            canvas.names, canvas.surfaces_only = names, False
            canvas.queue_redraw()

    def fit_view(self):
        if self.stage is not None:
            self.stage.canvas.fit()
