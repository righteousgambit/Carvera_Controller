"""Local, cancellable alternative comparison inside the clearance inspector."""

import copy
import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, QuantityField, Surface, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.setup_remedies import Remedy, compare_remedy
from carveracontroller.machine.simulation_preview import simulation_tools


def asset_identity(definition):
    """Actual bytes as well as declared identity; same-path replacement is a change."""
    return tuple(asset_digest(path) for path in (definition.geometry_path, definition.holder_geometry_path))


class RemedyPanel(Surface):
    def __init__(self, simulation, line, component, obstacle, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.simulation, self.line, self.component, self.obstacle = simulation, line, component, obstacle
        self.identity = simulation.clearance_identity
        self.inputs = simulation.clearance_inputs
        self.cancel_event = threading.Event()
        self.generation = 0
        self.running = False
        self.comparison = None
        self.request = None
        viewer = simulation.workspace.machine.gcode_viewer
        self.definitions = copy.deepcopy(viewer.library_tool_table_mm)
        self.add_widget(label("Compare a setup remedy", 13, bold=True, height=24))
        self.add_widget(
            content_label(
                "Alternatives use the same captured path and stock. Nothing is applied to the setup or controller."
            )
        )
        modes = ["Alternative tool geometry"]
        if self.inputs and any(o.name == obstacle for o in self.inputs[2].obstacles):
            modes.append("Shift obstacle bounds")
        self.mode = Choice(text=modes[0], values=tuple(modes))
        self.add_widget(self.mode)
        self.form = AdaptiveGrid(max_cols=2, min_width=170, row_height=82, spacing=dp(6))
        tools = self.inputs[1] if self.inputs else {}
        matching = sorted({s.tool_id for s in self.inputs[0] if s.line == line}) if self.inputs else []
        self.target = Choice(
            text=matching[0] if len(matching) == 1 else "Select program tool", values=tuple(sorted(tools))
        )
        self.alternative = Choice(
            text="Select loaded tool geometry", values=tuple(f"T{number}" for number in sorted(self.definitions))
        )
        self.shifts = [QuantityField(text="0 mm", kind="length", minimum=-1000, maximum=1000) for _ in range(3)]
        self.mode.bind(text=lambda *_: self.rebuild_form())
        self.add_widget(self.form)
        self.rebuild_form()
        actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
        self.compare_action = Action("Compare captured path", self.start, primary=True)
        self.cancel_action = Action("Cancel comparison", self.cancel_event.set, disabled=True)
        actions.add_widget(self.compare_action)
        actions.add_widget(self.cancel_action)
        self.add_widget(actions)
        self.result = content_label(
            "Select a declared alternative. A changed cutter may change finished dimensions; "
            "moved obstacle bounds do not establish valid clamping."
        )
        self.add_widget(self.result)
        self.contact_actions = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None, height=0)
        self.contact_actions.bind(minimum_height=self.contact_actions.setter("height"))
        self.add_widget(self.contact_actions)
        for control in (self.mode, self.target, self.alternative, *self.shifts):
            control.bind(text=self.draft_changed)

    def draft(self):
        return (self.mode.text, self.target.text, self.alternative.text, *(f.text for f in self.shifts))

    def draft_changed(self, *_):
        self.comparison = None
        self.contact_actions.clear_widgets()
        if self.running:
            self.cancel_event.set()
        self.result.text = "Draft changed. Compare again to evaluate this alternative."

    def rebuild_form(self):
        self.form.clear_widgets()
        entries = (
            (("Program tool", self.target), ("Loaded alternative", self.alternative))
            if self.mode.text == "Alternative tool geometry"
            else tuple((f"{axis} shift · program mm", field) for axis, field in zip("XYZ", self.shifts))
        )
        for title, control in entries:
            cell = BoxLayout(orientation="vertical", spacing=dp(4))
            cell.add_widget(label(title, 10, height=20))
            cell.add_widget(control)
            self.form.add_widget(cell)

    def current(self):
        return not self.simulation.clearance_stale and self.identity == self.simulation._identity()

    def close(self, *_):
        self.generation += 1
        self.cancel_event.set()

    def start(self):
        if self.running:
            return
        self.comparison = None
        self.contact_actions.clear_widgets()
        if not self.inputs or not self.current():
            self.result.text = "Captured setup changed. Recompute material removal before comparing remedies."
            return
        definition, number = None, None
        try:
            if self.mode.text == "Alternative tool geometry":
                if self.alternative.text not in self.alternative.values:
                    raise ValueError("Choose a loaded alternative tool geometry before comparing.")
                if self.target.text not in self.target.values:
                    raise ValueError("Choose a program tool from the captured path before comparing.")
                number = int(self.alternative.text.removeprefix("T"))
                definition = self.definitions.get(number)
                current = self.simulation.workspace.machine.gcode_viewer.library_tool_table_mm.get(number)
                if definition is None:
                    raise ValueError("Select an explicitly loaded alternative tool")
                if definition != current:
                    raise ValueError(
                        "Alternative definition changed. Reopen the inspector to capture current geometry."
                    )
                target = str(int(self.target.text))
                if target not in self.inputs[1]:
                    raise ValueError("Select a tool used in the captured path")
                shift = None
            else:
                target = None
                shift = Vec3(*(field.value() for field in self.shifts))
        except (ValueError, TypeError) as exc:
            self.result.text = str(exc)
            return
        self.generation += 1
        generation = self.generation
        self.request = (self.draft(), number, copy.deepcopy(definition))
        self.cancel_event.clear()
        self.running = True
        self.compare_action.disabled, self.cancel_action.disabled = True, False
        self.result.text = "Calculating baseline and alternative on independent stock copies…"
        inputs = self.inputs

        def run():
            assets = None
            try:
                if definition is not None:
                    assets = asset_identity(definition)
                    replacement = simulation_tools({int(target): definition}, {target})[target]
                    remedy = Remedy(
                        f"Program T{target} with captured T{number} geometry "
                        f"(Ø{replacement.diameter_mm:g}, flute {replacement.flute_length_mm:g}, "
                        f"shank Ø{replacement.shank_diameter_mm:g}, exposed {replacement.overall_length_mm:g} mm)",
                        tool_id=target,
                        replacement=replacement,
                    )
                else:
                    remedy = Remedy(
                        f"Shift {self.obstacle} bounds by {shift.tuple} mm", obstacle=self.obstacle, shift=shift
                    )
                comparison = compare_remedy(*inputs, remedy, cancelled=self.cancel_event.is_set)
                if definition is not None and assets != asset_identity(definition):
                    raise ValueError("Alternative CAD bytes changed during comparison")
                error = None
            except (ValueError, ArithmeticError, OSError) as exc:
                comparison, error = None, str(exc)
            Clock.schedule_once(lambda _dt: self.finish(generation, comparison, error, assets), 0)

        threading.Thread(target=run, daemon=True).start()

    def finish(self, generation, comparison, error, assets=None):
        if generation != self.generation:
            return
        self.running = False
        self.compare_action.disabled, self.cancel_action.disabled = False, True
        draft, number, definition = self.request
        if draft != self.draft():
            self.result.text = "Draft changed during comparison. Compare again; the prior result was not accepted."
            return
        if not self.current():
            self.result.text = (
                "Setup changed during comparison. Historical result was not accepted; recompute current inputs."
            )
            return
        if error:
            self.result.text = "Comparison failed: " + error
            return
        if definition is not None:
            current = self.simulation.workspace.machine.gcode_viewer.library_tool_table_mm.get(number)
            try:
                unchanged = definition == current and assets == asset_identity(definition)
            except (ValueError, OSError):
                unchanged = False
            if not unchanged:
                self.result.text = (
                    "Alternative geometry changed during comparison. Reopen the inspector and compare again."
                )
                return
        if not comparison.complete:
            self.result.text = "Cancelled comparison · partial observations do not establish a remedy."
            return
        self.comparison = comparison
        self.accepted_assets = assets
        before, after = comparison.baseline, comparison.candidate
        selected = (self.line, self.component, self.obstacle)
        selected_status = (
            "persists"
            if selected in after.candidates
            else "absent in candidate"
            if selected in before.candidates
            else "not reproduced in baseline"
        )
        self.result.text = (
            f"{comparison.title}\nSelected contact: {selected_status}\n"
            f"Conservative contact candidates: {len(before.candidates)} to {len(after.candidates)}\n"
            f"Removed contact locations: {len(comparison.removed_contacts)} · new: {len(comparison.new_contacts)}\n"
            f"Calculated removal: {before.removed_volume_mm3:.1f} to {after.removed_volume_mm3:.1f} mm³ "
            f"(delta {comparison.removal_delta_mm3:+.1f} mm³)\n" + "\n".join(comparison.warnings)
        )
        if comparison.new_contacts:
            self.result.text += "\nNew candidate locations: " + "; ".join(
                f"line {line}: {body} / {obstacle}" for line, body, obstacle in comparison.new_contacts[:8]
            )
        for title, contacts in (
            ("New contact", comparison.new_contacts),
            ("Removed contact", comparison.removed_contacts),
        ):
            for line, body, obstacle in contacts[:8]:
                action = Action(
                    f"{title}: line {line}\n{body} / {obstacle}",
                    lambda n=line, expected=comparison: self.inspect_contact(n, expected),
                    height=dp(52),
                    halign="left",
                    valign="middle",
                )
                action.bind(
                    width=lambda widget, width: setattr(widget, "text_size", (max(dp(1), width - dp(20)), None))
                )
                action.bind(texture_size=lambda widget, size: setattr(widget, "height", max(dp(52), size[1] + dp(16))))
                self.contact_actions.add_widget(action)

    def inspect_contact(self, line, comparison):
        """Navigate the original captured motion; never apply the alternative."""
        if self.comparison is not comparison or not self.current():
            self.contact_actions.clear_widgets()
            self.comparison = None
            self.result.text = "Comparison is older than the current setup. Recompute before inspecting motions."
            return
        draft, number, definition = self.request
        viewer = self.simulation.workspace.machine.gcode_viewer
        if draft != self.draft() or (definition is not None and definition != viewer.library_tool_table_mm.get(number)):
            self.draft_changed()
            return
        if definition is not None:
            try:
                unchanged = self.accepted_assets == asset_identity(definition)
            except (ValueError, OSError):
                unchanged = False
            if not unchanged:
                self.draft_changed()
                self.result.text = "Alternative CAD bytes changed. Reopen the inspector and compare again."
                return
        self.simulation.workspace.operation_panel.inspect_line(line, seek=True)
