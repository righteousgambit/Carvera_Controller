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
    Field,
    Surface,
    label,
    release_screen_focus,
)
from carveracontroller.machine.commissioning_capture import load_capture
from carveracontroller.machine.commissioning_channels import (
    CHANNEL_GROUPS,
    channel_page,
    hal_group_items,
    hal_item_detail,
)
from carveracontroller.machine.commissioning_compare import difference_page, hal_differences
from carveracontroller.machine.commissioning_exchange import read_comparison, write_comparison
from carveracontroller.machine.commissioning_trace import TRACE_METRICS, TRACE_PAGE, joint_trace


class CommissioningPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.capture = None
        self.comparison_raw = None
        self.cursor = 0
        self.channel_cursor = 0
        self.reference_cursor = 0
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
        self.open_comparison_button = Action("Open comparison…", self.open_comparison)
        controls.add_widget(self.open_comparison_button)
        controls.add_widget(Action("Clear review", self.clear))
        self.add_widget(controls)
        self.storage_note = flowing_text("", 26)
        self.add_widget(self.storage_note)
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
        self.hal_tools = Surface(orientation="vertical", padding=0, spacing=dp(5), size_hint_y=None)
        self.hal_tools.bind(minimum_height=self.hal_tools.setter("height"))
        self.hal_search = Field(hint_text="Search names, types or driver pins")
        self._filter_render = Clock.create_trigger(lambda _dt: self.render_channels(), 0.12)
        self.hal_search.bind(text=lambda *_: self.change_filter())
        self.hal_mode = Choice(text="Recorded values", values=("Recorded values", "Changed since reference"))
        self.hal_mode.bind(text=lambda *_: self.change_channel_group())
        self.hal_tools.add_widget(self.hal_mode)
        self.reference_button = Action("Use selected sample as reference", self.set_reference)
        self.hal_tools.add_widget(self.reference_button)
        self.export_comparison_button = Action("Save before/after comparison…", self.save_comparison)
        self.hal_tools.add_widget(self.export_comparison_button)
        self.reference_note = flowing_text("", 26)
        self.hal_tools.add_widget(self.reference_note)
        self.hal_tools.add_widget(self.hal_search)
        self.hal_filter_note = flowing_text("", 24)
        self.hal_tools.add_widget(self.hal_filter_note)
        self.hal_selected = Choice(text="No matching HAL items", values=())
        self.hal_selected.bind(text=lambda *_: self.render_hal_detail())
        self.hal_tools.add_widget(self.hal_selected)
        self.hal_detail = flowing_text("", 45)
        self.hal_tools.add_widget(self.hal_detail)
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

    def storage_job(self, operation, completed):
        if self.busy:
            return
        self.generation += 1
        generation = self.generation
        self.busy = True
        self.import_button.disabled = self.open_comparison_button.disabled = self.export_comparison_button.disabled = (
            True
        )
        self.storage_note.text = "Processing comparison off the UI thread…"

        def worker():
            result, error = None, None
            try:
                result = operation()
            except (ValueError, OSError, RecursionError) as exc:
                error = str(exc)

            def deliver(_dt):
                if generation != self.generation:
                    return
                self.busy = False
                self.import_button.disabled = self.open_comparison_button.disabled = False
                self.export_comparison_button.disabled = self.capture is None
                if error:
                    self.storage_note.text = "Comparison failed: " + error + " · existing review retained"
                else:
                    completed(result)

            Clock.schedule_once(deliver, 0)

        threading.Thread(target=worker, name="commissioning-comparison-storage", daemon=True).start()

    def save_comparison(self):
        if self.capture is None or self.busy:
            return
        capture, reference, selected = self.capture, self.reference_cursor, self.cursor
        group, raw = self.channel_choice.text, self.comparison_raw

        def saved(result):
            self.storage_note.text = f"Saved and read back historical comparison · SHA256 {result.file_sha256}"

        self.workspace.choose_profile_file(
            lambda path: self.storage_job(
                lambda: write_comparison(capture, reference, selected, group, path, raw), saved
            ),
            save=True,
            extension=".cvcompare",
            title="Save historical before/after comparison",
        )

    def open_comparison(self):
        if self.busy:
            return

        def loaded(result):
            self.deliver(self.generation, result.capture, None)
            self.comparison_raw = result.raw_capture
            self.reference_cursor, self.cursor = result.reference, result.selected
            self.channel_choice.text = result.group
            self.hal_mode.text = "Changed since reference"
            self.render()
            self.storage_note.text = (
                f"Historical comparison · saved {result.saved_at} · file SHA256 {result.file_sha256}"
            )

        self.workspace.choose_profile_file(
            lambda path: self.storage_job(lambda: read_comparison(path), loaded),
            extension=".cvcompare",
            title="Open historical before/after comparison",
        )

    def choose(self):
        self.workspace.choose_profile_file(self.request_load, extension=".jsonl", title="Import commissioning capture")

    def request_load(self, path):
        self.generation += 1
        generation = self.generation
        self.busy = True
        self.import_button.disabled = self.open_comparison_button.disabled = self.export_comparison_button.disabled = (
            True
        )
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
        self.import_button.disabled = self.open_comparison_button.disabled = False
        self.export_comparison_button.disabled = self.capture is None
        if error:
            self.note.text = "Import failed: " + error + " · previous review retained"
            return
        self.capture = capture
        self.comparison_raw = None
        self.export_comparison_button.disabled = False
        self.storage_note.text = ""
        self.reference_cursor = 0
        self.cursor = 0
        self.hal_mode.text = "Recorded values"
        self.channel_cursor = 0
        if self.details.parent is None:
            self.add_widget(self.details)
        self.joint_choice.values = tuple(f"Joint {j.index}" for j in capture.observations[0].joints) or ("No joints",)
        self.joint_choice.text = self.joint_choice.values[0]
        self.render()

    def clear(self):
        self.generation += 1
        self.capture = None
        self.comparison_raw = None
        self.storage_note.text = ""
        self.busy = False
        self.import_button.disabled = self.open_comparison_button.disabled = False
        self.export_comparison_button.disabled = True
        self.joint_choice.is_open = False
        self.channel_choice.is_open = False
        self.trace_choice.is_open = False
        self.hal_selected.is_open = False
        self.hal_mode.is_open = False
        self.reference_cursor = 0
        release_screen_focus(self.hal_tools)
        self.hal_search.text = ""
        self._filter_render.cancel()
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

    def change_filter(self):
        self.channel_cursor = 0
        self._filter_render()

    def current_hal(self):
        observations = getattr(self.capture, "hal_observations", ())
        return observations[self.cursor] if observations else None

    def set_reference(self):
        if self.capture is not None:
            self.reference_cursor = self.cursor
            self.channel_cursor = 0
            self.render_channels()

    def reference_hal(self):
        observations = getattr(self.capture, "hal_observations", ())
        return observations[self.reference_cursor] if observations else None

    def render_hal_detail(self):
        if len(self.hal_search.text) > 256:
            self.hal_detail.text = ""
            return
        if self.capture is not None and self.channel_choice.text.startswith("HAL "):
            if self.hal_mode.text == "Changed since reference":
                changes, note = hal_differences(
                    self.reference_hal(), self.current_hal(), self.channel_choice.text, self.hal_search.text
                )
                item = next((item for item in changes if item.name == self.hal_selected.text), None)
                self.hal_detail.text = item.detail() if item else note
            else:
                self.hal_detail.text = hal_item_detail(
                    self.current_hal(), self.channel_choice.text, self.hal_selected.text
                )
        else:
            self.hal_detail.text = ""

    def move_channels(self, delta):
        self.channel_cursor += delta
        self.render_channels()

    def render_channels(self):
        if self.capture is None:
            return
        hal = self.current_hal()
        is_hal = self.channel_choice.text.startswith("HAL ")
        if is_hal and self.hal_tools.parent is None:
            self.details.add_widget(self.hal_tools, index=self.details.children.index(self.channel_choice))
        elif not is_hal and self.hal_tools.parent is self.details:
            self.hal_selected.is_open = False
            self.hal_mode.is_open = False
            release_screen_focus(self.hal_tools)
            self.details.remove_widget(self.hal_tools)
        query = self.hal_search.text if is_hal else ""
        self.hal_search.validation_error = "Search is limited to 256 characters" if len(query) > 256 else ""
        if self.hal_search.validation_error:
            self.hal_filter_note.text = self.hal_search.validation_error
            self.channel_previous.disabled = self.channel_next.disabled = True
            self.hal_selected.values = ()
            self.hal_selected.is_open = False
            self.hal_selected.disabled = True
            self.hal_selected.text = "Invalid search"
            self.channel_values.text = "Shorten the search to browse recorded items"
            self.channel_range.text = "—"
            self.hal_detail.text = ""
            return
        page = channel_page(
            self.capture.observations[self.cursor],
            self.capture.transitions[self.cursor],
            self.channel_choice.text,
            self.channel_cursor,
            hal,
            query,
        )
        comparison_note = ""
        comparing = is_hal and self.hal_mode.text == "Changed since reference"
        if comparing:
            differences, comparison_note = hal_differences(self.reference_hal(), hal, self.channel_choice.text, query)
            page = difference_page(differences, self.channel_cursor)
        self.reference_note.text = (
            f"Reference sample {self.reference_cursor + 1} · {self.capture.utc_times[self.reference_cursor]}"
        )
        self.reference_button.disabled = self.reference_cursor == self.cursor
        self.channel_cursor = page.index
        self.channel_range.text = f"{page.first}–{page.last} / {page.total}"
        self.channel_previous.disabled = page.index == 0
        self.channel_next.disabled = page.index == page.pages - 1
        self.channel_values.text = "\n".join(f"{name}: {value}" for name, value in page.rows) or "No recorded channels"
        if self.channel_choice.text.startswith("HAL ") and hal is None:
            self.channel_values.text = "HAL was not captured in this recording"
        if is_hal:
            recorded = hal_group_items(hal, self.channel_choice.text)
            total = len(recorded or ())
            self.hal_filter_note.text = f"{page.total} matches / {total} recorded · all search words must match"
            choices = tuple(name for name, _value in page.rows)
            if self.hal_selected.values != choices:
                self.hal_selected.is_open = False
            self.hal_selected.values = choices
            self.hal_selected.disabled = not page.rows
            if self.hal_selected.text not in self.hal_selected.values:
                self.hal_selected.text = self.hal_selected.values[0] if page.rows else "No matching HAL items"
            if not page.rows and hal is not None:
                self.channel_values.text = (
                    "No HAL items match this search" if query.strip() else "No recorded HAL items"
                )
            if recorded is None and hal is not None:
                self.channel_values.text = "HAL parameters were not captured in this recording"
                self.hal_filter_note.text = "Parameter coverage unavailable · older capture or reader"
            if comparing:
                self.hal_filter_note.text = comparison_note
                if not page.rows:
                    self.channel_values.text = (
                        "No matching changes" if "unavailable" not in comparison_note else comparison_note
                    )
            self.render_hal_detail()

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
