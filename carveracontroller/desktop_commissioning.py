"""Historical commissioning samples, isolated from current machine controls."""

import threading

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_commissioning_trace import JointTracePlot
from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    Surface,
    label,
    release_screen_focus,
)
from carveracontroller.machine.commissioning_capture import load_capture
from carveracontroller.machine.commissioning_channels import CHANNEL_GROUPS, channel_page
from carveracontroller.machine.commissioning_trace import TRACE_METRICS, TRACE_PAGE, joint_trace


class CommissioningPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.capture = None
        self.cursor = 0
        self.channel_cursor = 0
        self.generation = 0
        self.busy = False
        self.add_widget(label("Commissioning captures", 14, height=28))
        self.note = flowing_text(
            "Import a LinuxCNC status capture to inspect joints and I/O. Historical review only.", 38
        )
        self.add_widget(self.note)
        controls = AdaptiveGrid(max_cols=2, min_width=170, row_height=34, spacing=dp(6))
        self.import_button = Action("Import status capture…", self.choose)
        controls.add_widget(self.import_button)
        controls.add_widget(Action("Clear review", self.clear))
        self.add_widget(controls)
        self.details = Surface(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None)
        self.details.bind(minimum_height=self.details.setter("height"))
        self.sample_note = flowing_text("", 38)
        self.details.add_widget(self.sample_note)
        navigation = AdaptiveGrid(max_cols=4, min_width=75, row_height=32, spacing=dp(4))
        self.first = Action("First", lambda: self.move(0))
        self.previous = Action("Previous", lambda: self.move(self.cursor - 1))
        self.next = Action("Next", lambda: self.move(self.cursor + 1))
        self.last = Action("Last", lambda: self.move(len(self.capture.observations) - 1) if self.capture else None)
        for button in (self.first, self.previous, self.next, self.last):
            navigation.add_widget(button)
        self.details.add_widget(navigation)
        self.joint_choice = Choice(text="Joint 0", values=("Joint 0",))
        self.joint_choice.bind(text=lambda *_: self.render())
        self.details.add_widget(self.joint_choice)
        self.trace_choice = Choice(text=TRACE_METRICS[0], values=TRACE_METRICS)
        self.trace_choice.bind(text=lambda *_: self.render_trace())
        self.details.add_widget(self.trace_choice)
        self.trace_plot = JointTracePlot(self.move)
        self.details.add_widget(self.trace_plot)
        self.trace_note = flowing_text("", 48)
        self.details.add_widget(self.trace_note)
        trace_navigation = AdaptiveGrid(max_cols=2, min_width=120, row_height=32, spacing=dp(4))
        self.trace_older = Action("Earlier trace", lambda: self.move(self.cursor - TRACE_PAGE))
        self.trace_newer = Action("Later trace", lambda: self.move(self.cursor + TRACE_PAGE))
        for button in (self.trace_older, self.trace_newer):
            trace_navigation.add_widget(button)
        self.details.add_widget(trace_navigation)
        self.joint_note = flowing_text("", 100)
        self.scope_note = flowing_text("", 55)
        for widget in (self.joint_note, self.scope_note):
            self.details.add_widget(widget)
        self.details.remove_widget(self.scope_note)
        self.channel_choice = Choice(text=CHANNEL_GROUPS[0], values=CHANNEL_GROUPS)
        self.channel_choice.bind(text=lambda *_: self.change_channel_group())
        self.details.add_widget(self.channel_choice)
        paging = AdaptiveGrid(max_cols=3, min_width=100, row_height=32, spacing=dp(4))
        self.channel_previous = Action("Previous page", lambda: self.move_channels(-1))
        self.channel_range = label("", 10, height=32)
        self.channel_next = Action("Next page", lambda: self.move_channels(1))
        for widget in (self.channel_previous, self.channel_range, self.channel_next):
            paging.add_widget(widget)
        self.details.add_widget(paging)
        self.channel_values = flowing_text("", 24)
        self.details.add_widget(self.channel_values)
        self.details.add_widget(self.scope_note)

    def choose(self):
        self.workspace.choose_profile_file(self.request_load, extension=".jsonl", title="Import commissioning capture")

    def request_load(self, path):
        self.generation += 1
        generation = self.generation
        self.busy = True
        self.import_button.disabled = True
        self.note.text = "Loading capture off the UI thread… existing review retained."

        def worker():
            result, error = None, None
            try:
                result = load_capture(path)
            except (ValueError, OSError, RecursionError) as exc:
                error = str(exc)
            Clock.schedule_once(lambda _dt: self.deliver(generation, result, error), 0)

        threading.Thread(target=worker, name="commissioning-capture-import", daemon=True).start()

    def deliver(self, generation, capture, error):
        if generation != self.generation:
            return
        self.busy = False
        self.import_button.disabled = False
        if error:
            self.note.text = "Import failed: " + error + " · previous review retained"
            return
        self.capture = capture
        self.cursor = 0
        self.channel_cursor = 0
        if self.details.parent is None:
            self.add_widget(self.details)
        self.joint_choice.values = tuple(f"Joint {j.index}" for j in capture.observations[0].joints) or ("No joints",)
        self.joint_choice.text = self.joint_choice.values[0]
        self.render()

    def clear(self):
        self.generation += 1
        self.capture = None
        self.busy = False
        self.import_button.disabled = False
        self.joint_choice.is_open = False
        self.channel_choice.is_open = False
        self.trace_choice.is_open = False
        self.trace_plot.show(None, 0)
        release_screen_focus(self.details)
        if self.details.parent is self:
            self.remove_widget(self.details)
        self.note.text = "Capture review cleared · connected machine and saved setup unchanged"

    def move(self, index):
        if self.capture:
            self.cursor = max(0, min(index, len(self.capture.observations) - 1))
            self.render()

    def change_channel_group(self):
        self.channel_cursor = 0
        self.render_channels()

    def move_channels(self, delta):
        self.channel_cursor += delta
        self.render_channels()

    def render_channels(self):
        if self.capture is None:
            return
        hal_observations = getattr(self.capture, "hal_observations", ())
        hal = hal_observations[self.cursor] if hal_observations else None
        page = channel_page(
            self.capture.observations[self.cursor],
            self.capture.transitions[self.cursor],
            self.channel_choice.text,
            self.channel_cursor,
            hal,
        )
        self.channel_cursor = page.index
        self.channel_range.text = f"{page.first}–{page.last} / {page.total}"
        self.channel_previous.disabled = page.index == 0
        self.channel_next.disabled = page.index == page.pages - 1
        self.channel_values.text = "\n".join(f"{name}: {value}" for name, value in page.rows) or "No recorded channels"
        if self.channel_choice.text.startswith("HAL ") and hal is None:
            self.channel_values.text = "HAL was not captured in this recording"

    def render_trace(self):
        if self.capture is None:
            return
        selected = self.joint_choice.text
        index = int(selected[5:]) if selected.startswith("Joint ") else -1
        trace = joint_trace(self.capture.observations, self.cursor, index, self.trace_choice.text)
        self.trace_plot.show(trace, self.cursor)
        self.trace_older.disabled = trace.first == 0
        self.trace_newer.disabled = trace.last == trace.total
        values = [value for point in trace.points for value in point.values]
        if trace.points:
            self.trace_note.text = (
                f"Samples {trace.first + 1}–{trace.last} / {trace.total} · "
                f"{trace.points[0].elapsed:g}–{trace.points[-1].elapsed:g} s\n"
                f"{'teal Commanded · amber Actual' if len(trace.names) == 2 else trace.names[0]} · "
                f"range {min(values):g} to {max(values):g}\n{trace.unit} · tap a point to inspect"
            )
        else:
            self.trace_note.text = "No comparable joint samples in this trace page"

    def render(self):
        capture = self.capture
        if capture is None:
            return
        observation = capture.observations[self.cursor]
        choices = tuple(f"Joint {j.index}" for j in observation.joints) or ("No joints",)
        if self.joint_choice.values != choices:
            self.joint_choice.values = choices
        if self.joint_choice.text not in choices:
            self.joint_choice.text = choices[0]
        self.note.text = (
            f"Imported {observation.machine_id} · {len(capture.observations)} samples · "
            + ("complete capture" if capture.complete else "incomplete capture")
            + (f" · stopped: {capture.failure}" if capture.failure else "")
        )
        self.sample_note.text = (
            f"Sample {self.cursor + 1}/{len(capture.observations)} · {capture.utc_times[self.cursor]}\n"
            f"Elapsed {observation.observed_at - capture.observations[0].observed_at:.3f} s · reported tool {observation.tool_in_spindle}"
        )
        self.first.disabled = self.previous.disabled = self.cursor == 0
        self.next.disabled = self.last.disabled = self.cursor == len(capture.observations) - 1
        joint = next((j for j in observation.joints if self.joint_choice.text == f"Joint {j.index}"), None)
        if joint is None:
            self.joint_note.text = "No joint observations in this sample"
        else:
            unit = "mm" if joint.kind == "linear" else "degree"
            home = "homing" if joint.homing else ("homed" if joint.homed else "not homed")

            def state(value):
                return "active" if value else "clear"

            self.joint_note.text = (
                f"Joint {joint.index} · {joint.kind} · {joint.units_per_mm_or_degree:g} raw units per {unit}\n"
                f"Commanded {joint.commanded:g} · actual {joint.actual:g} · following error {joint.following_error:g}\n"
                f"Velocity {joint.velocity:g} raw units/s · home: {home}\n"
                f"Drive {'enabled' if joint.enabled else 'disabled'} · amplifier fault {state(joint.fault)}\n"
                f"Hard limits: lower {state(joint.min_hard_limit)}, upper {state(joint.max_hard_limit)}\n"
                f"Soft limits: lower {state(joint.min_soft_limit)}, upper {state(joint.max_soft_limit)}"
            )

        self.scope_note.text = (
            f"Historical, unverified source · file SHA256 {capture.sha256[:16]}…\n"
            f"INI SHA256 {capture.ini_sha256[:16]}… · excludes included configuration\n"
            "Sample changes are observation intervals. This review grants no live capability or machine permissive."
        )
        self.scope_note.color = MUTED
        if any(getattr(capture, "hal_observations", ())):
            self.scope_note.text += "\nHAL and NML are separate samples, not one atomic machine snapshot."
        self.render_channels()
        self.render_trace()
