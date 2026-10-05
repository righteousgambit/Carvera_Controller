"""Measured surface review and boundary-facing workflow in the workbench."""

import hashlib
import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.widget import Widget

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Field, label
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field, stage_program
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.surface_planning import FacingParameters, FacingPlan, HeightMap, HeightSample


def points(text, columns):
    if len(text) > 128 * 1024:
        raise ValueError("Coordinate input exceeds 128 KB")
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.split(",") if "," in line else line.split()
        if len(values) != columns:
            raise ValueError(f"Each row needs {columns} numbers; received {line!r}")
        rows.append(tuple(parse_quantity(value, "length") for value in values))
    if len(rows) > 1000:
        raise ValueError("Input is limited to 1,000 rows")
    return tuple(rows)


class HeightMapPlot(Widget):
    height_map = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=0, **kwargs)
        self.bind(pos=self.redraw, size=self.redraw, height_map=self.redraw)

    def redraw(self, *_):
        self.canvas.clear()
        heights = self.height_map
        self.height = dp(150) if heights is not None else 0
        if heights is None:
            return
        xmin = min(p[0] for p in heights.boundary)
        ymin = min(p[1] for p in heights.boundary)
        width = max(p[0] for p in heights.boundary) - xmin
        height = max(p[1] for p in heights.boundary) - ymin
        scale = min(max(1, self.width - dp(20)) / width, max(1, self.height - dp(20)) / height)
        ox, oy = self.x + (self.width - width * scale) / 2, self.y + (self.height - height * scale) / 2

        def xy(p):
            return ox + (p[0] - xmin) * scale, oy + (p[1] - ymin) * scale

        zs = [s.z_mm for s in heights.samples]
        lo, hi = (min(zs), max(zs)) if zs else (0, 0)
        with self.canvas:
            Color(0.27, 0.8, 0.73, 1)
            Line(points=[v for p in heights.boundary for v in xy(p)], close=True, width=1.2)
            for exclusion in heights.exclusions:
                Color(0.98, 0.72, 0.32, 1)
                Line(points=[v for p in exclusion for v in xy(p)], close=True, width=1)
            for sample in heights.samples:
                fraction = (sample.z_mm - lo) / (hi - lo) if hi > lo else 0.5
                Color(fraction, 0.7, 1 - fraction, 1)
                x, y = xy((sample.x_mm, sample.y_mm))
                Ellipse(pos=(x - dp(3), y - dp(3)), size=(dp(6), dp(6)))


class SurfacePlanningPanel(PlanningCard):
    def __init__(self, workspace, **kwargs):
        super().__init__("Surface map & boundary facing", **kwargs)
        self.workspace = workspace
        self.height_map = None
        self.plan = None
        self.running = False
        self.tools = {}
        self.fields = {}
        self.content.add_widget(label("1 · Stock boundary in work coordinates", 13, height=26, bold=True))
        self.boundary = Field(multiline=True, height=dp(90), hint_text="X Y · one polygon vertex per row · mm")
        self.content.add_widget(self.boundary)
        self.content.add_widget(Action("Use scene stock footprint", self.use_stock))
        options = AdaptiveGrid(max_cols=2, min_width=180, row_height=62, spacing=dp(7))
        self.wcs = planning_choice(options, "Work offset", tuple(f"G{i}" for i in range(54, 60)))
        self.tool = planning_choice(options, "Facing cutter", ("No loaded flat cutter",))
        self.content.add_widget(options)
        self.content.add_widget(Action("Refresh loaded cutter choices", self.refresh_tools))
        self.content.add_widget(label("2 · Measured surface · optional", 13, height=26, bold=True))
        self.samples = Field(
            multiline=True, height=dp(100), hint_text="X Y Z uncertainty · mm · one measurement per row"
        )
        self.content.add_widget(self.samples)
        self.content.add_widget(label("Excluded regions · polygons separated by a blank row", 10, MUTED, 28))
        self.exclusions = Field(
            multiline=True, height=dp(80), hint_text="X Y · no interpolation across excluded regions"
        )
        self.content.add_widget(self.exclusions)
        sample_fields = AdaptiveGrid(max_cols=2, min_width=180, row_height=78, spacing=dp(7))
        self.source = planning_field(sample_fields, "Measurement source / instrument", "")
        self.timestamp = planning_field(sample_fields, "Observation time · ISO 8601", "")
        self.gap = planning_field(sample_fields, "Maximum interpolation gap · mm", "20", quantity="length", minimum=0)
        self.query_x = planning_field(sample_fields, "Inspect surface at X · mm", "0", quantity="length")
        self.query_y = planning_field(sample_fields, "Inspect surface at Y · mm", "0", quantity="length")
        self.content.add_widget(sample_fields)
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=34, spacing=dp(6))
        for title, callback in (
            ("Review entered measurements", self.review_map),
            ("Inspect sampled height", self.query_height),
            ("Load surface map", self.load_map),
            ("Save surface map", self.save_map),
            ("Use measured upper height", self.use_measured_top),
        ):
            actions.add_widget(Action(title, callback))
        self.content.add_widget(actions)
        self.plot = HeightMapPlot()
        self.content.add_widget(self.plot)
        self.map_note = label(
            "Blue = lower · red = higher · points are measured samples; empty areas have no implied measurement.",
            11,
            MUTED,
            58,
        )
        self.content.add_widget(self.map_note)
        self.content.add_widget(label("3 · Facing target & process", 13, height=26, bold=True))
        self.content.add_widget(
            label(
                "Use 1/4 in, 127/2 mm, or 12 ipm. Interpretation stays visible; generated programs use mm.",
                10,
                MUTED,
                42,
            )
        )
        process = AdaptiveGrid(max_cols=3, min_width=165, row_height=78, spacing=dp(7))
        for key, title, value in (
            ("top_z_mm", "Starting top Z · mm", "0"),
            ("final_z_mm", "Final face Z · mm", "-0.2"),
            ("clearance_z_mm", "Clearance Z · mm", "5"),
            ("stepover_mm", "Stepover · mm", "2"),
            ("pass_depth_mm", "Depth per pass · mm", "0.1"),
            ("overtravel_mm", "Extra edge overtravel · mm", "0"),
            ("feed_mm_min", "Cutting feed · mm/min", "300"),
            ("plunge_feed_mm_min", "Plunge feed · mm/min", "80"),
            ("spindle_rpm", "Spindle · RPM", "12000"),
            ("flute_count", "Flutes", "3"),
            ("material", "Material / alloy", "6061"),
        ):
            quantity = (
                None
                if key == "material"
                else "scalar"
                if key == "flute_count"
                else "rpm"
                if key == "spindle_rpm"
                else "feed"
                if "feed" in key
                else "length"
            )
            self.fields[key] = planning_field(
                process,
                title,
                value,
                quantity=quantity,
                **({"integer": True, "minimum": 1} if key == "flute_count" else {}),
            )
        self.content.add_widget(process)
        actions = AdaptiveGrid(max_cols=3, min_width=145, row_height=36, spacing=dp(6))
        for title, callback in (
            ("Generate facing preview", self.generate),
            ("Save facing recipe", self.save_recipe),
            ("Load facing recipe", self.load_recipe),
        ):
            actions.add_widget(Action(title, callback, primary=title.startswith("Generate")))
        self.content.add_widget(actions)
        self.content.add_widget(self.note)

    def use_stock(self):
        setup = self.workspace.machine.gcode_viewer.machine_setup
        if setup.stock_size_mm is None:
            self.note.text = "Choose stock size and placement in Scene first."
            return
        x, y, z = setup.stock_origin_mm
        sx, sy, sz = setup.stock_size_mm
        self.boundary.text = "\n".join(f"{a:g} {b:g}" for a, b in ((x, y), (x + sx, y), (x + sx, y + sy), (x, y + sy)))
        self.fields["top_z_mm"].text = f"{z + sz:g}"
        self.fields["clearance_z_mm"].text = f"{z + sz + 5:g}"
        self.note.text = "Scene footprint copied as unmeasured geometry. Confirm boundary and final height."

    def refresh_tools(self):
        self.tools = {
            f"T{n} · {t.description or 'Flat end mill'}": t
            for n, t in self.workspace.machine.gcode_viewer.library_tool_table_mm.items()
            if t.tool_type == ToolType.FLAT_END_MILL
        }
        self.tool.values = tuple(self.tools) or ("No loaded flat cutter",)
        if self.tool.text not in self.tool.values:
            self.tool.text = self.tool.values[0]

    def review_map(self):
        try:
            if not self.source.text.strip() or not self.timestamp.text.strip():
                raise ValueError("Enter the measurement source and actual observation time")
            observed = datetime.fromisoformat(self.timestamp.text.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError("Observation time needs a timezone, for example 2026-10-03T20:00:00Z")
            rows = points(self.samples.text, 4)
            if not rows:
                raise ValueError("Enter at least one measured sample")
            heights = HeightMap(
                points(self.boundary.text, 2),
                [HeightSample(*row[:3], self.source.text, self.timestamp.text, row[3]) for row in rows],
                exclusions=tuple(
                    points(block, 2) for block in self.exclusions.text.strip().split("\n\n") if block.strip()
                ),
                max_gap_mm=self.gap.value(),
                wcs=self.wcs.text,
            )
            self.height_map = heights
            self.plot.height_map = heights
            self.plot.redraw()
            self.map_note.text = f"{len(rows)} samples · Z {min(s.z_mm for s in heights.samples):g} to {max(s.z_mm for s in heights.samples):g} mm · {heights.wcs}\nColor spans measured range; interpolation requires bounded supporting samples."
        except (ValueError, TypeError) as exc:
            self.map_note.text = str(exc)

    def query_height(self):
        try:
            if self.height_map is None:
                raise ValueError("Review or load a surface map first")
            estimate = self.height_map.query(self.query_x.value(), self.query_y.value())
            self.map_note.text = (
                f"{estimate.kind}: Z {estimate.z_mm:.5f} mm · sample/instrument uncertainty {estimate.uncertainty_mm:.5f} mm\nUnknown surface curvature is not bounded by this estimate."
                if estimate
                else "No supported measurement here: outside the boundary, excluded, or beyond interpolation support."
            )
        except (ValueError, TypeError) as exc:
            self.map_note.text = str(exc)

    def use_measured_top(self):
        if self.height_map is None or not self.height_map.samples:
            self.note.text = "Load or review measured samples first."
            return
        try:
            boundary = points(self.boundary.text, 2)
        except ValueError as exc:
            self.note.text = str(exc)
            return
        if self.height_map.wcs != self.wcs.text or self.height_map.boundary != boundary:
            self.note.text = "Map boundary and work offset must match the facing setup."
            return
        samples = [s for s in self.height_map.samples if self.height_map._allowed((s.x_mm, s.y_mm))]
        if not samples:
            self.note.text = "No measured samples inside the allowed boundary."
            return
        self.fields["top_z_mm"].text = f"{max(s.z_mm + s.uncertainty_mm for s in samples):.5f}"
        self.note.text = "Upper measured height includes sample uncertainty. Unsampled high spots remain unknown."

    def parameters(self):
        tool = self.tools.get(self.tool.text)
        if tool is None:
            raise ValueError("Load a flat cutter profile and refresh cutter choices")
        current = self.workspace.machine.gcode_viewer.library_tool_table_mm.get(tool.number)
        if current != tool:
            raise ValueError("Loaded cutter profile changed; refresh cutter choices")
        if any(v is None or not math.isfinite(v) or v <= 0 for v in (tool.diameter, tool.flute_length, tool.stickout)):
            raise ValueError("Cutter profile needs measured diameter, flute length and stickout")
        if not isinstance(tool.number, int) or not 1 <= tool.number <= 255:
            raise ValueError("Cutter profile needs a valid physical tool number")
        values = {key: field.text if key == "material" else field.value() for key, field in self.fields.items()}
        p = FacingParameters(
            boundary=points(self.boundary.text, 2),
            tool_diameter_mm=tool.diameter,
            tool_id=str(tool.number),
            wcs=self.wcs.text,
            **values,
        )
        if p.top_z_mm - p.final_z_mm > min(tool.flute_length, tool.stickout):
            raise ValueError("Facing depth exceeds cutter flute length or stickout")
        return p, tool

    def generate(self):
        if self.running:
            return
        try:
            p, tool = self.parameters()
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        tool_snapshot = repr(tool)
        self.running = True
        self.note.text = "Computing stock-boundary passes…"

        def calculate():
            try:
                plan, error = FacingPlan.from_params(p), None
            except (ValueError, ArithmeticError) as exc:
                plan, error = None, str(exc)
            Clock.schedule_once(lambda _dt: finish(plan, error), 0)

        def finish(plan, error):
            self.running = False
            if error:
                self.note.text = error
                return
            try:
                current, current_tool = self.parameters()
                if current != p or repr(current_tool) != tool_snapshot:
                    raise ValueError("Setup changed during calculation; generate again")
                text = plan.gcode()
                # The selected physical slot is explicit; the engine's tool_id is metadata.
                text = text.replace(p.wcs + "\n", p.wcs + f"\nT{tool.number} M6\n", 1)
                path = stage_program(self.workspace, text, "boundary-facing")
                self.plan = plan
                self.note.text = f"{len(plan.segments):,} cutting spans · {p.chipload_mm_per_tooth:.4f} mm/tooth · {p.radial_engagement_fraction:.0%} radial engagement\nLocal preview: {path.name}. Physical travel/workholding review remains required."
            except (OSError, ValueError, TypeError) as exc:
                self.note.text = str(exc)

        threading.Thread(target=calculate, daemon=True).start()

    def save_map(self):
        if self.height_map is None:
            self.map_note.text = "Review measurements first."
            return

        def save(path):
            try:
                self.height_map.save(path)
                self.map_note.text = "Surface map saved with measurement provenance."
            except (OSError, ValueError) as exc:
                self.map_note.text = str(exc)

        self.workspace.choose_profile_file(save, save=True, extension=".cvmap", title="Save measured surface")

    def load_map(self):
        def load(path):
            try:
                heights = HeightMap.load(path)
                self.boundary.text = "\n".join(f"{x:g} {y:g}" for x, y in heights.boundary)
                self.wcs.text = heights.wcs
                self._restore_map_controls(heights)
                self.map_note.text = f"Loaded {len(heights.samples)} samples; original source/time retained in saved map. Re-entering measurements creates new provenance."
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.map_note.text = str(exc)

        self.workspace.choose_profile_file(load, extension=".cvmap", title="Load measured surface")

    def _restore_map_controls(self, heights):
        self.height_map = heights
        self.plot.height_map = heights
        self.samples.text = (
            "\n".join(f"{s.x_mm:g} {s.y_mm:g} {s.z_mm:g} {s.uncertainty_mm:g}" for s in heights.samples)
            if heights
            else ""
        )
        self.exclusions.text = (
            "\n\n".join("\n".join(f"{x:g} {y:g}" for x, y in polygon) for polygon in heights.exclusions)
            if heights
            else ""
        )
        sources = {s.source for s in heights.samples} if heights else set()
        times = {s.observed_at for s in heights.samples} if heights else set()
        self.source.text = next(iter(sources)) if len(sources) == 1 else ""
        self.timestamp.text = next(iter(times)) if len(times) == 1 else ""
        if heights:
            self.gap.text = str(heights.max_gap_mm)
        self.plot.redraw()

    def save_recipe(self):
        try:
            p, tool = self.parameters()
            if self.height_map and (self.height_map.wcs != p.wcs or self.height_map.boundary != p.boundary):
                raise ValueError("Surface map boundary/work offset differs from the facing recipe")
            record = {
                "schema_version": 1,
                "parameters": p.to_dict(),
                "tool_geometry": {
                    "diameter": tool.diameter,
                    "flute_length": tool.flute_length,
                    "stickout": tool.stickout,
                },
                "surface_map": self.height_map.to_dict() if self.height_map else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return

        def save(path):
            try:
                with Path(path).open("x", encoding="utf-8") as stream:
                    json.dump(record, stream, allow_nan=False)
                self.note.text = "Facing recipe saved with cutter dimensions and optional surface map."
            except (OSError, ValueError) as exc:
                self.note.text = str(exc)

        self.workspace.choose_profile_file(save, save=True, extension=".cvface", title="Save facing recipe")

    def load_recipe(self):
        self.workspace.choose_profile_file(self.load_path, extension=".cvface", title="Load facing recipe")

    def load_path(self, path, expected_digest=None):
        try:
            source = Path(path)
            if source.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Facing recipe exceeds 2 MB")
            raw = source.read_bytes()
            if expected_digest is not None and hashlib.sha256(raw).hexdigest() != expected_digest:
                raise ValueError("Recipe file changed since linking; review its new content")
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise ValueError("Facing recipe must be an object")
            if record.get("schema_version") != 1:
                raise ValueError("Unsupported facing recipe")
            p = FacingParameters.from_dict(record["parameters"])
            if not isinstance(record["tool_geometry"], dict) or set(record["tool_geometry"]) != {
                "diameter",
                "flute_length",
                "stickout",
            }:
                raise ValueError("Invalid cutter geometry snapshot")
            heights = HeightMap.from_dict(record["surface_map"]) if record.get("surface_map") else None
            if heights and (heights.wcs != p.wcs or heights.boundary != p.boundary):
                raise ValueError("Surface map boundary/work offset differs from the facing recipe")
            self.restore_reviewed_recipe(p, record["tool_geometry"], heights)
        except (OSError, ValueError, TypeError, KeyError, StopIteration) as exc:
            self.note.text = str(exc)

    def restore_reviewed_recipe(self, p, geometry, heights):
        """Apply already parsed recipe inputs after checking the currently loaded tool."""
        try:
            self.refresh_tools()
            match = next(
                (
                    name
                    for name, t in self.tools.items()
                    if str(t.number) == p.tool_id and all(getattr(t, key) == value for key, value in geometry.items())
                ),
                None,
            )
            if match is None:
                raise ValueError("Load the matching cutter slot/dimensions before restoring this recipe")
            self.boundary.text = "\n".join(f"{x:g} {y:g}" for x, y in p.boundary)
            self.wcs.text, self.tool.text = p.wcs, match
            for key, field in self.fields.items():
                field.text = str(getattr(p, key))
            self._restore_map_controls(heights)
            self.note.text = "Recipe restored for local review. Physical setup remains unverified."
        except (ValueError, TypeError, KeyError) as exc:
            self.note.text = str(exc)
