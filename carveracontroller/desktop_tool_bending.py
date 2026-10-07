"""Explicit assumed-load bending comparison from the selected nominal tool."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, QuantityField, Surface, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.tool_bending import estimate_cantilever


class ToolBendingBench(Surface):
    def __init__(self, comparison):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(8), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.result = None
        row = next((row for row in comparison.rows if row.number == comparison.selected), None)
        self.add_widget(label("Assumed transverse tip load · uniform circular cantilever", 13, height=30, bold=True))
        self.context = wrapped()
        self.context.text = (
            f"Nominal snapshot T{row.number} · {row.name}. Diameter and stickout are declared library values; "
            "review the equivalent beam diameter and unsupported length below."
            if row
            else "No selected nominal tool. Enter the two beam geometries explicitly."
        )
        self.add_widget(self.context)
        self.fields = {}
        grid = AdaptiveGrid(max_cols=2, min_width=230, row_height=78, spacing=dp(8))
        for key, title, kind, value, minimum, maximum in (
            ("force", "Assumed tip force · N", "force", "", 0, 1e9),
            ("modulus", "Assumed elastic modulus · MPa", "pressure", "", 0.001, 1e9),
            (
                "diameter",
                "Reference equivalent diameter · mm",
                "length",
                row.library_diameter_mm if row else None,
                0.001,
                10000,
            ),
            ("length", "Reference unsupported length · mm", "length", row.stickout_mm if row else None, 0.001, 10000),
            ("candidate_diameter", "Candidate equivalent diameter · mm", "length", None, 0.001, 10000),
            ("candidate_length", "Candidate unsupported length · mm", "length", None, 0.001, 10000),
        ):
            cell = BoxLayout(orientation="vertical", spacing=dp(3))
            cell.add_widget(label(title, 11, height=23))
            field = QuantityField(
                kind=kind,
                text=f"{value:g}" if isinstance(value, (int, float)) else "",
                minimum=minimum,
                maximum=maximum,
            )
            self.fields[key] = field
            cell.add_widget(field)
            grid.add_widget(cell)
        self.add_widget(grid)
        self.add_widget(Action("Compare declared bending", self.calculate))
        self.output = wrapped()
        self.output.text = "Enter force, modulus and both geometries, then compare."
        self.add_widget(self.output)
        self.assumptions = wrapped()
        self.assumptions.text = (
            "Model: I = πd⁴/64; tip displacement = FL³/(3EI); root bending stress = FLd/(2I). "
            "The candidate uses the same force and modulus. Fixed root, constant solid circular section and "
            "small elastic deflection are assumed. Flutes, distributed loads, holder/spindle compliance, "
            "chatter and strength limits are omitted. No force is inferred from RPM or feed. "
            "Equivalent diameter is an operator assumption; nominal cutting diameter is not a verified beam section. "
            "Results are local sensitivity estimates, not dimensional acceptance or permission to cut."
        )
        self.add_widget(self.assumptions)
        for field in self.fields.values():
            field.bind(text=self.invalidate)

    def invalidate(self, *_):
        self.result = None
        self.output.text = "Inputs changed · compare again to obtain a current estimate."
        self.output.color = MUTED

    def calculate(self):
        self.result = None
        try:
            values = {key: field.value() for key, field in self.fields.items()}
            reference = estimate_cantilever(values["diameter"], values["length"], values["force"], values["modulus"])
            candidate = estimate_cantilever(
                values["candidate_diameter"], values["candidate_length"], values["force"], values["modulus"]
            )
        except ValueError as exc:
            self.output.text = f"Cannot compare: {exc}"
            self.output.color = AMBER
            return
        self.result = (reference, candidate)
        lines = []
        for name, result in (("Reference", reference), ("Candidate", candidate)):
            lines.append(
                f"{name} · Ø {result.diameter_mm:g} mm · unsupported {result.overhang_mm:g} mm\n"
                f"Tip displacement {result.displacement_mm * 1000:.6g} µm · root stress {result.root_stress_mpa:.6g} MPa\n"
                f"Compliance {result.compliance_mm_per_n * 1000:.6g} µm/N · tip slope {result.tip_slope_rad:.6g} rad"
            )
            lines.extend(result.limitations)
        ratio = candidate.compliance_mm_per_n / reference.compliance_mm_per_n
        lines.append(
            f"Candidate/reference compliance {ratio:.6g}× · {(ratio - 1) * 100:+.3g}% under identical load and modulus"
        )
        lines.append(f"Declared force {reference.force_n:g} N · declared modulus {reference.modulus_mpa:g} MPa")
        self.output.text = "\n\n".join(lines)
        self.output.color = AMBER if reference.limitations or candidate.limitations else MUTED


def open_bending_comparison(comparison):
    bench = ToolBendingBench(comparison)
    comparison.custody.dialog("Tool bending sensitivity", [bench], None, "Close")
    comparison.bending_bench = bench
