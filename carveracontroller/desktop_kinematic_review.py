"""Workbench review of declared kinematics; never a motion control surface."""

import hashlib
import json
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.graphics import Color, Line, Mesh, Rectangle
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    DANGER,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
)
from carveracontroller.desktop_joint_clearance import JointClearancePanel
from carveracontroller.desktop_planning import PlanningCard, planning_field
from carveracontroller.machine.indexed_setup_review import review_indexed_setup
from carveracontroller.machine.joint_path_review import review_joint_path
from carveracontroller.machine.kinematic_review import (
    example_profile,
    machine_from_record,
    profile_digest,
    review_branches,
    vector,
)


class JointPathPlot(Widget):
    """Selectable rank trace: sample index is not elapsed time."""

    def __init__(self, selected, **kwargs):
        super().__init__(**kwargs)
        self.selected = selected
        self.review = None
        self.index = 0
        self.bind(pos=self._draw, size=self._draw)

    def show(self, review, index=0):
        self.review, self.index = review, index
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        if self.review is None:
            return
        samples = self.review.samples
        x, y, width, height = self.x + dp(8), self.y + dp(8), max(1, self.width - dp(16)), max(1, self.height - dp(16))
        expected = max(sample.rank[1] for sample in samples)
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            Color(*MUTED)
            Line(points=[x, y + height, x + width, y + height], width=1)
            Color(*ACCENT)
            Line(
                points=[
                    value
                    for i, sample in enumerate(samples)
                    for value in (x + width * i / (len(samples) - 1), y + height * sample.rank[0] / expected)
                ],
                width=dp(1.2),
            )
            Color(*DANGER)
            ticks = []
            for i in self.review.singular_indices:
                px = x + width * i / (len(samples) - 1)
                ticks.extend((px, y, 0, 0, px, y + dp(8), 0, 0))
            if ticks:
                Mesh(vertices=ticks, indices=list(range(len(ticks) // 4)), mode="lines")
            Color(*TEXT)
            px = x + width * self.index / (len(samples) - 1)
            Line(points=[px, y, px, y + height], width=dp(1))

    def on_touch_down(self, touch):
        if self.review is not None and self.collide_point(*touch.pos) and not self.disabled:
            if getattr(touch, "is_mouse_scrolling", False):
                return super().on_touch_down(touch)
            ratio = min(1, max(0, (touch.x - self.x - dp(8)) / max(1, self.width - dp(16))))
            self.selected(round(ratio * (len(self.review.samples) - 1)))
            return True
        return super().on_touch_down(touch)


class IndexedSetupPanel(PlanningCard):
    """One fixed orientation, with a separate explicit route handoff."""

    def __init__(self, owner):
        super().__init__("Indexed 3+2 setup")
        self.owner = owner
        self.review = None
        self.rotary_fields = {}
        self.point_buttons = []
        self.selected_point = None
        self.content.add_widget(
            flowing_text(
                "Hold every rotary axis at the angles below. Map ordered workpiece XYZ points to the three linear axes using declared pivots, work frame and tool length.",
                50,
            )
        )
        self.rotary_grid = AdaptiveGrid(max_cols=3, min_width=130, row_height=78, spacing=dp(6))
        self.content.add_widget(self.rotary_grid)
        self.branch_action = Action("Use selected branch orientation", self.use_branch, disabled=True)
        self.content.add_widget(self.branch_action)
        self.points = planning_field(
            self.content, "Ordered work points · XYZ mm, one point per line", "10 15 25\n20 15 25"
        )
        self.points.multiline = True
        self.points.height = dp(84)
        self.points.parent.height = dp(108)
        self.points.bind(text=owner._invalidate)
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.review_action = Action("Map work points", self.map_points)
        self.copy_action = Action("Copy to joint route", self.copy_waypoints, disabled=True)
        actions.add_widget(self.review_action)
        actions.add_widget(self.copy_action)
        self.content.add_widget(actions)
        self.note = flowing_text("Choose a fixed orientation and map work points. No indexing command is sent.", 45)
        self.content.add_widget(self.note)
        self.point_choices = AdaptiveGrid(max_cols=2, min_width=150, row_height=54, spacing=dp(6))
        self.point_choices.height = 0
        self.content.add_widget(self.point_choices)
        self.details = flowing_text("", 0)
        self.content.add_widget(self.details)

    def set_profile(self):
        self.rotary_grid.clear_widgets()
        self.rotary_fields = {}
        machine = machine_from_record(self.owner.record)
        first = self.owner._waypoints(machine)[0]
        for joint in machine.tool_chain + machine.work_chain:
            if joint.kind == "rotary":
                field = planning_field(
                    self.rotary_grid,
                    f"Fixed {joint.name} · deg",
                    first[joint.name],
                    quantity="angle",
                    minimum=joint.minimum,
                    maximum=joint.maximum,
                )
                field.bind(text=self.owner._invalidate)
                self.rotary_fields[joint.name] = field

    def clear_result(self):
        self.review = None
        self.selected_point = None
        self.point_choices.clear_widgets()
        self.point_choices.height = 0
        self.point_buttons = []
        self.copy_action.disabled = True
        self.branch_action.disabled = True
        self.note.text = "Inputs changed · indexed work points require a new review."
        self.details.text = ""

    def use_branch(self):
        index = self.owner.selected_branch
        if self.owner.running or index is None or not self.owner.reviews[index].result.converged:
            return
        positions = self.owner.reviews[index].result.positions
        for name, field in self.rotary_fields.items():
            field.text = format(positions[name], ".12g")
        self.note.text = "Copied the selected branch's rotary angles. Map work points to review this fixed setup."

    def map_points(self):
        if self.owner.running:
            return
        try:
            if len(self.points.text) > 4096:
                raise ValueError("Work-point input exceeds the bounded review size")
            machine = machine_from_record(self.owner.record)
            fixed = {name: field.value() for name, field in self.rotary_fields.items()}
            points = [
                vector([float(word) for word in line.split()]) for line in self.points.text.splitlines() if line.strip()
            ]
            length = self.owner.length_field.value()
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = "Indexed setup unavailable: " + str(exc)
            return
        self.clear_result()
        self.note.text = "Mapping declared fixed-orientation work points…"
        self.owner._start(
            lambda cancelled: review_indexed_setup(machine, fixed, points, length, cancelled=cancelled),
            self._reviewed,
            error_target=self.note,
        )

    def _reviewed(self, review):
        if review is None:
            return
        self.review = review
        self.copy_action.disabled = len(review.points) < 2
        self.note.text = (
            f"{len(review.points)} work points mapped · rotary angles stay fixed\n"
            f"Tool axis in work: {' / '.join(format(v, '.5g') for v in review.tool_axis.tuple)}\n"
            f"Linear basis determinant {review.basis_determinant:.5g} · maximum tip residual {max(p.tip_error_mm for p in review.points):.4g} mm\n"
            "Indexing approach, clearance, offsets, feed and backend coordinate conventions require separate qualification."
        )
        self.point_choices.clear_widgets()
        self.point_buttons = []
        for index, point in enumerate(review.points):
            coordinates = " / ".join(format(v, ".3g") for v in point.target_mm.tuple)
            action = Action(
                f"Point {index + 1}\n{coordinates} mm",
                lambda index=index: self.select_point(index),
                height=dp(54),
            )
            action.bind(width=lambda button, width: setattr(button, "text_size", (max(dp(10), width - dp(12)), None)))
            self.point_choices.add_widget(action)
            self.point_buttons.append(action)
        self.select_point(0)
        self.owner.status.text = "Declared indexed setup mapped · no controller indexing or cutting program."

    def select_point(self, index):
        if self.review is None or not 0 <= index < len(self.review.points):
            return
        self.selected_point = index
        for i, button in enumerate(self.point_buttons):
            button.base_color = ACCENT if i == index else RAISED
            button.color = BG if i == index else TEXT
            button._paint()
        point = self.review.points[index]
        machine = machine_from_record(self.owner.record)
        lines = [f"Work point {index + 1} · " + " / ".join(format(v, ".5g") for v in point.target_mm.tuple) + " mm"]
        for joint in machine.tool_chain + machine.work_chain:
            unit = "mm" if joint.kind == "linear" else "deg"
            lines.append(
                f"{joint.name} {point.positions[joint.name]:.5g} {unit} · limit margin {point.limit_margin[joint.name]:.5g} {unit}"
            )
        self.details.text = "\n".join(lines)

    def copy_waypoints(self):
        review = self.review
        if self.owner.running or review is None or len(review.points) < 2:
            return
        machine = machine_from_record(self.owner.record)
        names = [j.name for j in machine.tool_chain + machine.work_chain]
        self.owner.seeds.text = "\n".join(
            " ".join(format(point.positions[name], ".12g") for name in names) for point in review.points
        )
        self.owner.path_note.text = (
            "Copied fixed-orientation mapped points. Review the route separately; no indexing approach is included."
        )
        if not self.owner.path_card.expanded:
            self.owner.path_card.toggle()


class KinematicReviewPanel(PlanningCard):
    def __init__(self, workspace):
        super().__init__("Five-axis reachability & branches")
        self.workspace = workspace
        self.closed = False
        self.running = False
        self.generation = 0
        self.cancel_event = None
        self.branch_buttons = []
        self.reviews = ()
        self.selected_branch = None
        self.path_review = None
        self.path_index = 0
        self.record = example_profile("Head / head")
        row = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.topology = Choice(text="Head / head", values=("Head / head", "Head / table", "Table / table"))
        row.add_widget(self.topology)
        self.import_action = Action("Import declared geometry", self.import_profile, height=dp(36))
        row.add_widget(self.import_action)
        self.content.add_widget(row)
        self.profile_note = flowing_text("", 38)
        self.content.add_widget(self.profile_note)
        grid = AdaptiveGrid(max_cols=3, min_width=130, row_height=78, spacing=dp(6))
        self.target_fields = [
            planning_field(grid, f"Target {axis} · work mm", value, quantity="length", minimum=-1e6, maximum=1e6)
            for axis, value in zip("XYZ", (10, 15, 25))
        ]
        self.content.add_widget(grid)
        self.axis_field = planning_field(self.content, "Target tool axis · unit XYZ vector", "0.5 0 0.8660254037844386")
        self.length_field = planning_field(
            self.content, "Spindle origin to tip · mm", 5, quantity="length", minimum=0, maximum=1e6
        )
        self.seed_note = flowing_text("", 28)
        self.content.add_widget(self.seed_note)
        self.seeds = Field(multiline=True, height=dp(84))
        self.content.add_widget(self.seeds)
        self.status = flowing_text(
            "Declared geometry only · no controller TCP, collision or execution qualification.", 42
        )
        self.content.add_widget(self.status)
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.solve_action = Action("Compare seed branches", self.solve, height=dp(36))
        self.cancel_action = Action("Cancel review", self.cancel, height=dp(36), disabled=True)
        actions.add_widget(self.solve_action)
        actions.add_widget(self.cancel_action)
        self.content.add_widget(actions)
        self.frame_action = Action("Inspect declared frame chain", self.inspect_frames)
        self.content.add_widget(self.frame_action)
        self.results = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=0)
        self.results.bind(minimum_height=self.results.setter("height"))
        self.content.add_widget(self.results)
        self.detail = flowing_text("Select a calculated branch to inspect joints, limits and local sensitivity.", 40)
        self.content.add_widget(self.detail)
        self.indexed_panel = IndexedSetupPanel(self)
        self.content.add_widget(self.indexed_panel)
        self.path_card = PlanningCard("Joint transition review")
        self.content.add_widget(self.path_card)
        self.path_card.content.add_widget(
            flowing_text(
                "Uses the entered seed rows as ordered joint waypoints. Full rotary turns are retained; this is joint interpolation, not a TCP or cutting program.",
                50,
            )
        )
        grid = AdaptiveGrid(max_cols=2, min_width=150, row_height=78, spacing=dp(6))
        self.path_linear_step = planning_field(
            grid, "Maximum linear sample step · mm", 2, quantity="length", minimum=0.001, maximum=1e6
        )
        self.path_rotary_step = planning_field(
            grid, "Maximum rotary sample step · deg", 2, quantity="angle", minimum=0.001, maximum=1e6
        )
        self.path_card.content.add_widget(grid)
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.path_action = Action("Review entered joint route", self.review_path)
        self.path_solution_action = Action("Copy solutions to waypoints", self.solutions_to_waypoints, disabled=True)
        actions.add_widget(self.path_action)
        actions.add_widget(self.path_solution_action)
        self.path_card.content.add_widget(actions)
        self.path_note = flowing_text(
            "No route reviewed. Choose two to eight waypoint rows; review uses at most 2001 samples.", 45
        )
        self.path_card.content.add_widget(self.path_note)
        self.path_plot = JointPathPlot(self.select_path_sample, height=dp(100), size_hint_y=None)
        self.path_plot.height = 0
        self.path_card.content.add_widget(self.path_plot)
        self.path_navigation = AdaptiveGrid(max_cols=4, min_width=65, row_height=32, spacing=dp(5))
        for caption, offset in (("First", None), ("Previous", -1), ("Next", 1), ("Last", "last")):
            self.path_navigation.add_widget(Action(caption, lambda offset=offset: self.step_path(offset)))
        self.path_detail = flowing_text("", 0)
        self.path_card.content.add_widget(self.path_detail)
        self.clearance_panel = JointClearancePanel(self)
        self.content.add_widget(self.clearance_panel)
        self._show_profile("Illustrative example; not the connected machine")
        self.topology.bind(text=self._example_changed)
        for field in (
            *self.target_fields,
            self.axis_field,
            self.length_field,
            self.seeds,
            self.path_linear_step,
            self.path_rotary_step,
        ):
            field.bind(text=self._invalidate)

    def _show_profile(self, source):
        machine = machine_from_record(self.record)
        joints = machine.tool_chain + machine.work_chain
        chain = lambda values: " / ".join(j.name for j in values) or "fixed"
        self.profile_note.text = f"{self.record.get('name', 'Declared profile')}\nSpindle: {chain(machine.tool_chain)} · Workpiece: {chain(machine.work_chain)}\n{source} · profile {profile_digest(self.record)[:12]}"
        self.seed_note.text = (
            "One joint row per line · seeds for solving, ordered waypoints for route review · "
            + " / ".join(j.name + (" mm" if j.kind == "linear" else " deg") for j in joints)
        )
        self.seeds.text = "\n".join(
            " ".join(
                str(
                    min(
                        j.maximum,
                        max(
                            j.minimum,
                            (-angle if self.topology.text == "Table / table" else angle)
                            if j.name == "B"
                            else 180
                            if j.name == "C" and angle < 0
                            else 0,
                        ),
                    )
                )
                for j in joints
            )
            for angle in (30, -30)
        )

        self.indexed_panel.set_profile()
        self.clearance_panel.set_profile()

    def _invalidate(self, *_):
        self.generation += 1
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.reviews = ()
        self.selected_branch = None
        self.indexed_panel.clear_result()
        self.results.clear_widgets()
        self.branch_buttons = []
        self.path_review = None
        self.path_index = 0
        self.path_plot.show(None)
        self.path_plot.height = 0
        if self.path_navigation.parent is not None:
            self.path_navigation.parent.remove_widget(self.path_navigation)
        self.path_detail.text = ""
        self.path_note.text = "Inputs changed · route requires a new review."
        self.path_solution_action.disabled = True
        self.clearance_panel.clear_result()
        self.status.text = "Inputs changed · results require a new review."
        self.detail.text = "Inputs changed · calculate branches for the current declared geometry."

    def _example_changed(self, _choice, topology):
        if topology not in self.topology.values:
            return
        self._invalidate()
        self.record = example_profile(topology)
        self._show_profile("Illustrative example; not the connected machine")

    def _start(self, work, done, error_target=None):
        if self.closed or self.running:
            self.status.text = "Wait for the current review to stop."
            return
        self.running = True
        self.generation += 1
        generation = self.generation
        cancelled = threading.Event()
        self.cancel_event = cancelled
        self.solve_action.disabled = self.import_action.disabled = self.path_action.disabled = (
            self.path_solution_action.disabled
        ) = True
        self.frame_action.disabled = True
        self.clearance_panel.review_action.disabled = True
        self.indexed_panel.review_action.disabled = True
        self.indexed_panel.copy_action.disabled = True
        self.indexed_panel.branch_action.disabled = True
        self.cancel_action.disabled = False
        self.status.text = "Reviewing declared geometry…"

        def worker():
            result, error = None, None
            try:
                result = work(cancelled.is_set)
            except (ValueError, TypeError, OSError, KeyError, ArithmeticError, RecursionError, InterruptedError) as exc:
                error = str(exc)
            except Exception as exc:
                Logger.exception("Kinematics: Unexpected review worker failure")
                error = f"Review failed: {type(exc).__name__}"

            def deliver(_dt):
                self._release_review_controls()
                if self.closed:
                    return
                if cancelled.is_set() or generation != self.generation:
                    self.status.text = "Review cancelled or inputs changed · prior result discarded."
                    if error_target is not None:
                        error_target.text = self.status.text
                elif error:
                    self.status.text = "Review unavailable: " + error
                    if error_target is not None:
                        error_target.text = self.status.text
                else:
                    done(result)

            Clock.schedule_once(deliver, 0)

        try:
            threading.Thread(target=worker, name="kinematic-branch-review", daemon=True).start()
        except RuntimeError:
            self._release_review_controls()
            self.status.text = "Review unavailable: worker could not start"
            if error_target is not None:
                error_target.text = self.status.text

    def _release_review_controls(self):
        self.running = False
        self.cancel_event = None
        self.solve_action.disabled = self.import_action.disabled = self.path_action.disabled = False
        self.frame_action.disabled = False
        self.clearance_panel.review_action.disabled = False
        self.path_solution_action.disabled = not (
            len(self.reviews) >= 2 and all(r.result.converged for r in self.reviews)
        )
        self.indexed_panel.review_action.disabled = False
        self.indexed_panel.copy_action.disabled = not (
            self.indexed_panel.review is not None and len(self.indexed_panel.review.points) >= 2
        )
        self.indexed_panel.branch_action.disabled = not (
            self.selected_branch is not None and self.reviews[self.selected_branch].result.converged
        )
        self.cancel_action.disabled = True

    def cancel(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.status.text = "Stopping review…"

    def import_profile(self):
        def selected(path):
            def load(_cancelled):
                with Path(path).open("rb") as stream:
                    data = stream.read(65537)
                if len(data) > 65536:
                    raise ValueError("Kinematic profile exceeds 64 KiB")
                record = json.loads(data)
                machine_from_record(record)
                return record, hashlib.sha256(data).hexdigest()

            def loaded(result):
                record, source_sha = result
                self._invalidate()
                self.record = record
                self.topology.text = "Imported geometry"
                self._show_profile(f"Imported declaration: {Path(path).name} · file SHA {source_sha[:12]}")
                self.status.text = "Imported declared geometry · controller capability remains unverified."

            self._start(load, loaded)

        self.workspace.choose_asset_file(selected, suffixes=(".json",))

    def solve(self):
        if self.running:
            return
        try:
            if len(self.seeds.text) > 8192 or len(self.axis_field.text) > 128:
                raise ValueError("Seed/axis input exceeds the bounded review size")
            machine = machine_from_record(self.record)
            target = vector([field.value() for field in self.target_fields])
            axis = vector([float(word) for word in self.axis_field.text.split()])
            length = self.length_field.value()
            names = [j.name for j in machine.tool_chain + machine.work_chain]
            seeds = []
            for line in self.seeds.text.splitlines():
                if not line.strip():
                    continue
                values = [float(word) for word in line.split()]
                if len(values) != len(names):
                    raise ValueError("Each seed needs exactly one value per joint")
                seeds.append(dict(zip(names, values)))
            if not 1 <= len(seeds) <= 8:
                raise ValueError("Enter one to eight seed rows")
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.status.text = "Review unavailable: " + str(exc)
            return
        self._invalidate()
        self._start(
            lambda cancelled: review_branches(machine, target, axis, seeds, length, cancelled=cancelled), self._reviewed
        )

    def _reviewed(self, reviews):
        self.reviews = reviews
        self.path_solution_action.disabled = not (len(reviews) >= 2 and all(r.result.converged for r in reviews))
        self.results.clear_widgets()
        for index, review in enumerate(reviews):
            result = review.result
            caption = f"Seed {index + 1} · {'Converged locally' if result.converged else 'No local solution'}\nTip error {result.tip_error_mm:.4g} mm · axis error {result.axis_error:.4g}"
            button = Action(caption, lambda index=index: self.select_branch(index), height=dp(54))
            self.branch_buttons.append(button)
            self.results.add_widget(button)
        self.status.text = f"{sum(r.result.converged for r in reviews)}/{len(reviews)} seeds converged locally · seed results may coincide. No global reachability or clearance claim."
        if reviews:
            self.select_branch(0)

    def select_branch(self, index):
        if not 0 <= index < len(self.reviews):
            return
        self.selected_branch = index
        self.indexed_panel.branch_action.disabled = self.running or not self.reviews[index].result.converged
        for i, button in enumerate(self.branch_buttons):
            button.base_color = ACCENT if i == index else RAISED
            button.color = BG if i == index else TEXT
            button._paint()
        review = self.reviews[index]
        machine = machine_from_record(self.record)
        lines = [f"Seed {index + 1} · {review.result.reason} · {review.result.iterations} iterations"]
        for joint in machine.tool_chain + machine.work_chain:
            name = joint.name
            unit = "mm" if joint.kind == "linear" else "deg"
            equivalent = review.equivalent_positions
            alternative = (
                f" · nearest equivalent {equivalent[name]:.4f}" if equivalent and joint.kind == "rotary" else ""
            )
            lines.append(
                f"{name} {review.result.positions[name]:.4f} {unit}{alternative} · limit margin {review.limit_margin[name]:.4f} {unit}"
            )
        rank, expected = review.rank
        lines.append(f"Local tip/axis Jacobian rank {rank}/{expected} · normalized residual threshold 1e-3.")
        if rank < expected:
            lines.append("Dependent local directions · orientation/position sensitivity needs review.")
        lines.append(
            "Equivalent rotary angles are endpoint alternatives, not an unwind path. Tool/holder clearance, cable travel, TCP and backend execution remain unverified."
        )
        self.detail.text = "\n".join(lines)

    def _waypoints(self, machine):
        if len(self.seeds.text) > 8192:
            raise ValueError("Waypoint input exceeds the bounded review size")
        names = [j.name for j in machine.tool_chain + machine.work_chain]
        rows = []
        for line in self.seeds.text.splitlines():
            if not line.strip():
                continue
            values = [float(word) for word in line.split()]
            if len(values) != len(names):
                raise ValueError("Each waypoint needs exactly one value per joint")
            rows.append(dict(zip(names, values)))
        return rows

    def inspect_frames(self):
        if self.running or self.closed:
            return None
        from carveracontroller.desktop_kinematic_frames import open_kinematic_frames

        try:
            machine = machine_from_record(self.record)
            if self.selected_branch is not None and self.reviews:
                state = self.reviews[self.selected_branch].result.positions
                source = (
                    f"Calculated branch {self.selected_branch + 1} · {self.reviews[self.selected_branch].result.reason}"
                )
            else:
                rows = self._waypoints(machine)
                if not rows:
                    raise ValueError("Enter a joint row before inspecting its frame chain")
                state = rows[0]
                source = "First entered joint row · not a solved branch"
            return open_kinematic_frames(self.record, state, self.length_field.value(), source)
        except (ValueError, TypeError) as exc:
            self.status.text = str(exc)
            return None

    def solutions_to_waypoints(self):
        if self.running or len(self.reviews) < 2 or not all(r.result.converged for r in self.reviews):
            return
        names = [
            j.name for j in machine_from_record(self.record).tool_chain + machine_from_record(self.record).work_chain
        ]
        text = "\n".join(" ".join(format(r.result.positions[name], ".12g") for name in names) for r in self.reviews)
        self.seeds.text = text
        self.path_note.text = (
            "Copied local endpoint solutions to waypoint rows. The connecting route still requires review."
        )
        if not self.path_card.expanded:
            self.path_card.toggle()

    def review_path(self):
        if self.running:
            return
        try:
            machine = machine_from_record(self.record)
            waypoints = self._waypoints(machine)
            length = self.length_field.value()
            linear_step = self.path_linear_step.value()
            rotary_step = self.path_rotary_step.value()
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.path_note.text = "Route unavailable: " + str(exc)
            return
        self.path_review = None
        self.path_plot.show(None)
        self.path_plot.height = 0
        self.path_detail.text = ""
        if self.path_navigation.parent is not None:
            self.path_navigation.parent.remove_widget(self.path_navigation)
        self.path_note.text = "Reviewing entered joint interpolation…"
        self._start(
            lambda cancelled: review_joint_path(
                machine, waypoints, length, linear_step_mm=linear_step, rotary_step_deg=rotary_step, cancelled=cancelled
            ),
            self._path_reviewed,
            error_target=self.path_note,
        )

    def _path_reviewed(self, review):
        if review is None:
            return
        self.path_review = review
        self.path_plot.height = dp(100)
        if self.path_navigation.parent is None:
            self.path_card.content.add_widget(self.path_navigation, index=1)
        self.path_note.text = (
            f"{len(review.samples)} samples · {len(review.singular_indices)} with dependent local directions\n"
            f"Largest sampled tip step {review.largest_tip_step_mm:.4g} mm · axis step {review.largest_axis_step_deg:.4g} deg\n"
            f"Maximum tip deviation from each endpoint chord {review.largest_tip_chord_error_mm:.4g} mm\n"
            "Rank trace: horizontal = sample order, vertical = local rank; red ticks = dependent directions. Between samples, clearance, feed, cables, TCP and execution remain unqualified."
        )
        self.status.text = "Declared joint route reviewed · samples are geometry diagnostics, not a motion program."
        self.select_path_sample(review.singular_indices[0] if review.singular_indices else 0)

    def step_path(self, offset):
        if self.path_review is None:
            return
        index = (
            0 if offset is None else len(self.path_review.samples) - 1 if offset == "last" else self.path_index + offset
        )
        self.select_path_sample(index)

    def select_path_sample(self, index):
        if self.path_review is None:
            return
        self.path_index = min(len(self.path_review.samples) - 1, max(0, index))
        sample = self.path_review.samples[self.path_index]
        self.path_plot.show(self.path_review, self.path_index)
        machine = machine_from_record(self.record)
        lines = [
            f"Sample {self.path_index + 1}/{len(self.path_review.samples)} · segment {sample.segment + 1} · {100 * sample.fraction:.1f}%",
            f"Local rank {sample.rank[0]}/{sample.rank[1]} · normalized residual threshold 1e-3",
            "Tip in work mm: " + " / ".join(f"{value:.5g}" for value in sample.tip_mm.tuple),
            "Tool axis: " + " / ".join(f"{value:.5g}" for value in sample.axis.tuple),
        ]
        for joint in machine.tool_chain + machine.work_chain:
            unit = "mm" if joint.kind == "linear" else "deg"
            lines.append(
                f"{joint.name} {sample.positions[joint.name]:.5g} {unit} · limit margin {sample.limit_margin[joint.name]:.5g} {unit} · total route travel {self.path_review.joint_travel[joint.name]:.5g} {unit}"
            )
        if sample.rank[0] < sample.rank[1]:
            lines.append("Dependent task directions at this sample: revise the route or review another configuration.")
        self.path_detail.text = "\n".join(lines)

    def dispose(self):
        self.closed = True
        self.generation += 1
        self.cancel()
