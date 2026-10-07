"""Read-only declared feed/RPM review with explicit optional ceilings."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, QuantityField, Surface, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.cutting_parameters import program_feed_rpm, review_cutting_parameters


class CuttingParameterBench(Surface):
    def __init__(self, comparison):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(8), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.comparison = comparison
        self.result = None
        self.source_snapshot = None
        row = next((row for row in comparison.rows if row.number == comparison.selected), None)
        self.tool_number = row.number if row else None
        self.add_widget(label("Declared milling parameters", 13, height=30, bold=True))
        self.context = wrapped()
        self.context.text = (
            f"Nominal snapshot T{row.number} · {row.name}. Diameter is a declared library value."
            if row
            else "No nominal tool selected. Enter diameter and flute count explicitly."
        )
        self.add_widget(self.context)
        self.add_widget(Action("Use selected program line", self.load_program_line))
        grid = AdaptiveGrid(max_cols=2, min_width=230, row_height=78, spacing=dp(8))
        self.fields = {}
        for key, title, kind, value, optional in (
            ("diameter", "Effective cutting diameter · mm", "length", row.library_diameter_mm if row else None, False),
            ("flutes", "Active cutting flutes · whole number", "scalar", None, False),
            ("rpm", "Declared spindle · RPM", "rpm", None, False),
            ("feed", "Declared linear feed · mm/min", "feed", None, False),
            ("max_rpm", "Optional RPM ceiling", "rpm", None, True),
            ("max_feed", "Optional feed ceiling · mm/min", "feed", None, True),
            ("max_chip", "Optional chip-load ceiling · mm/tooth", "length", None, True),
        ):
            cell = BoxLayout(orientation="vertical", spacing=dp(3))
            cell.add_widget(label(title, 11, height=23))
            field = QuantityField(
                kind=kind,
                text=f"{value:g}" if isinstance(value, (int, float)) else "",
                minimum=0 if key == "feed" else 1 if key == "flutes" else 1e-9 if key == "max_chip" else 0.001,
                maximum=1000 if key == "flutes" else 10000 if key == "diameter" else 1e9,
                step=0.001 if key == "max_chip" else None,
                integer=key == "flutes",
                optional=optional,
            )
            self.fields[key] = field
            cell.add_widget(field)
            grid.add_widget(cell)
        self.add_widget(grid)
        self.add_widget(Action("Review declared parameters", self.calculate))
        self.output = wrapped()
        self.output.text = (
            "Enter diameter, flute count, RPM and feed. Ceilings are optional and must be supplied explicitly."
        )
        self.add_widget(self.output)
        self.assumptions = wrapped()
        self.assumptions.text = (
            "Nominal kinematics: chip load = feed/(RPM × flutes); cutting speed = π × diameter × RPM. "
            "Effective diameter and active flute count are operator assumptions. Actual chip thickness depends on "
            "engagement; radial/axial engagement, material, cutter capability, runout, power, torque, stability "
            "and physical machine limits are unqualified. Only supplied ceilings are compared. "
            "A result within those ceilings is not cutting feasibility or permission to run. "
            "Program import copies a declared line snapshot; subsequent edits are local and do not rewrite or execute it."
        )
        self.add_widget(self.assumptions)
        for field in self.fields.values():
            field.bind(text=self.invalidate)

    def invalidate(self, *_):
        self.result = None
        self.output.text = "Inputs changed · review again for a current comparison."
        self.output.color = MUTED

    def load_program_line(self):
        panel = self.comparison.workspace.operation_panel
        program, number = panel.program, panel.selected_line
        try:
            if program is None or number is None or not 1 <= number <= len(program.checkpoints):
                raise ValueError("Inspect a program feed line first")
            state = program.checkpoints[number - 1].state
            feed, rpm = program_feed_rpm(state, self.tool_number)
        except ValueError as exc:
            self.result = None
            self.output.text = f"Cannot import: {exc}. Existing fields were retained."
            self.output.color = AMBER
            return
        self.fields["rpm"].text = f"{rpm:.12g}"
        self.fields["feed"].text = f"{feed:.12g}"
        self.source_snapshot = (program.file_hash, number, state)
        self.context.text = (
            f"Declared source snapshot {program.file_hash} · line {number} · T{state.tool} · "
            f"{state.units}/{state.feed_mode} · F{state.feed:g}/S{state.spindle_speed:g}. "
            "Converted feed and RPM are editable local inputs; no engagement is inferred."
        )

    def calculate(self):
        self.result = None
        try:
            v = {key: field.value() for key, field in self.fields.items()}
            result = review_cutting_parameters(
                v["diameter"],
                v["flutes"],
                v["rpm"],
                v["feed"],
                max_rpm=v["max_rpm"],
                max_feed_mm_min=v["max_feed"],
                max_chip_mm_tooth=v["max_chip"],
            )
        except ValueError as exc:
            self.output.text = f"Cannot review: {exc}"
            self.output.color = AMBER
            return
        self.result = result
        self.output.text = (
            f"Nominal chip load {result.chip_mm_tooth:.6g} mm/tooth · {result.chip_mm_tooth / 25.4:.6g} in/tooth\n"
            f"Feed per revolution {result.feed_mm_rev:.6g} mm/rev\n"
            f"Cutting speed {result.surface_m_min:.6g} m/min · {result.surface_m_min / 0.3048:.6g} ft/min\n"
            f"Declared feed {result.feed_mm_min:g} mm/min · spindle {result.rpm:g} RPM\n\n"
            + (
                "\n".join(result.violations)
                if result.violations
                else "No supplied ceiling exceeded."
                if result.checked_limits
                else "No ceilings supplied · constraints unassessed."
            )
            + ("\nChecked: " + "; ".join(result.checked_limits) if result.checked_limits else "")
            + "\nEngagement and full cutting feasibility remain unqualified."
        )
        self.output.color = AMBER if result.violations else MUTED


def open_cutting_parameters(comparison):
    bench = CuttingParameterBench(comparison)
    comparison.custody.dialog("Feed & chip-load review", [bench], None, "Close")
    comparison.cutting_parameter_bench = bench
