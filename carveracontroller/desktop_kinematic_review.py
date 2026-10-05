"""Workbench review of declared kinematics; never a motion control surface."""

import hashlib
import json
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, BG, RAISED, TEXT, Action, AdaptiveGrid, Choice, Field
from carveracontroller.desktop_planning import PlanningCard, planning_field
from carveracontroller.machine.kinematic_review import (
    example_profile,
    machine_from_record,
    profile_digest,
    review_branches,
    vector,
)


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
        self.results = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=0)
        self.results.bind(minimum_height=self.results.setter("height"))
        self.content.add_widget(self.results)
        self.detail = flowing_text("Select a calculated branch to inspect joints, limits and local sensitivity.", 40)
        self.content.add_widget(self.detail)
        self._show_profile("Illustrative example; not the connected machine")
        self.topology.bind(text=self._example_changed)
        for field in (*self.target_fields, self.axis_field, self.length_field, self.seeds):
            field.bind(text=self._invalidate)

    def _show_profile(self, source):
        machine = machine_from_record(self.record)
        joints = machine.tool_chain + machine.work_chain
        chain = lambda values: " / ".join(j.name for j in values) or "fixed"
        self.profile_note.text = f"{self.record.get('name', 'Declared profile')}\nSpindle: {chain(machine.tool_chain)} · Workpiece: {chain(machine.work_chain)}\n{source} · profile {profile_digest(self.record)[:12]}"
        self.seed_note.text = "One seed per line · " + " / ".join(
            j.name + (" mm" if j.kind == "linear" else " deg") for j in joints
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

    def _invalidate(self, *_):
        self.generation += 1
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.reviews = ()
        self.selected_branch = None
        self.results.clear_widgets()
        self.branch_buttons = []
        self.status.text = "Inputs changed · results require a new review."
        self.detail.text = "Inputs changed · calculate branches for the current declared geometry."

    def _example_changed(self, _choice, topology):
        if topology not in self.topology.values:
            return
        self._invalidate()
        self.record = example_profile(topology)
        self._show_profile("Illustrative example; not the connected machine")

    def _start(self, work, done):
        if self.closed or self.running:
            self.status.text = "Wait for the current review to stop."
            return
        self.running = True
        self.generation += 1
        generation = self.generation
        cancelled = threading.Event()
        self.cancel_event = cancelled
        self.solve_action.disabled = self.import_action.disabled = True
        self.cancel_action.disabled = False
        self.status.text = "Reviewing declared geometry…"

        def worker():
            result, error = None, None
            try:
                result = work(cancelled.is_set)
            except (ValueError, TypeError, OSError, KeyError, ArithmeticError, RecursionError) as exc:
                error = str(exc)

            def deliver(_dt):
                self.running = False
                self.cancel_event = None
                self.solve_action.disabled = self.import_action.disabled = False
                self.cancel_action.disabled = True
                if self.closed:
                    return
                if cancelled.is_set() or generation != self.generation:
                    self.status.text = "Review cancelled or inputs changed · prior result discarded."
                elif error:
                    self.status.text = "Review unavailable: " + error
                else:
                    done(result)

            Clock.schedule_once(deliver, 0)

        threading.Thread(target=worker, name="kinematic-branch-review", daemon=True).start()

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

    def dispose(self):
        self.closed = True
        self.generation += 1
        self.cancel()
