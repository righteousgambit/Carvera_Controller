"""Editable articulated body envelopes and continuous joint-route clearance."""

from copy import deepcopy

from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, DANGER, MUTED, Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.desktop_scene_clearance import SceneClearanceControls
from carveracontroller.machine.joint_clearance import (
    bodies_from_record,
    body_transform,
    corners,
    review_joint_clearance,
)
from carveracontroller.machine.kinematic_review import machine_from_record, profile_digest, vector


class JointBodyPlot(Widget):
    """Equal-scale XY/XZ projections of actual declared body boxes at one pose."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(200), **kwargs)
        self.geometry = ()
        self.selected = ()
        self.bind(pos=self.draw, size=self.draw)

    def show(self, machine, bodies, state, selected=()):
        self.geometry = tuple(
            (b.name, tuple(body_transform(machine, b, state).apply(p).tuple for p in corners(b.bounds))) for b in bodies
        )
        self.selected = selected
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        if not self.geometry:
            return
        all_points = [p for _name, points in self.geometry for p in points]
        for pane, vertical in enumerate((1, 2)):
            width, height = max(1, self.width / 2 - dp(20)), max(1, self.height - dp(20))
            lo = (min(p[0] for p in all_points), min(p[vertical] for p in all_points))
            hi = (max(p[0] for p in all_points), max(p[vertical] for p in all_points))
            scale = min(width / max(1e-9, hi[0] - lo[0]), height / max(1e-9, hi[1] - lo[1]))
            x = self.x + pane * self.width / 2 + dp(10) + (width - (hi[0] - lo[0]) * scale) / 2
            y = self.y + dp(10) + (height - (hi[1] - lo[1]) * scale) / 2
            for name, points in self.geometry:
                with self.canvas:
                    Color(*(DANGER if name in self.selected else ACCENT))
                    for i, first in enumerate(points):
                        for j, second in enumerate(points):
                            if j > i and (i ^ j) in (1, 2, 4):
                                Line(
                                    points=[
                                        x + (first[0] - lo[0]) * scale,
                                        y + (first[vertical] - lo[1]) * scale,
                                        x + (second[0] - lo[0]) * scale,
                                        y + (second[vertical] - lo[1]) * scale,
                                    ],
                                    width=dp(1.2),
                                )


class JointClearancePanel(PlanningCard):
    def __init__(self, owner):
        super().__init__("Continuous machine-body clearance")
        self.owner = owner
        self.result = None
        self.review_inputs = None
        self.syncing = False
        self.frames = {}
        self.body_drafts = {}
        self.body_selection = None
        self.choice_names = {"New body": None}
        self.content.add_widget(
            flowing_text(
                "Attach each conservative body box to world, a spindle/workpiece base, or a joint link. Enter bounds in that attachment's local millimetres. Route review covers the full entered joint interpolation, including full rotary turns.",
                60,
            )
        )
        self.scene_capture = SceneClearanceControls(self)
        self.content.add_widget(self.scene_capture)
        self.choice = planning_choice(self.content, "Declared body", ("New body",))
        self.choice.bind(text=self.fill_body)
        fields = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.name_field = planning_field(fields, "Body name", "Body 1")
        self.frame = planning_choice(fields, "Attachment", ("World",))
        self.minimum = planning_field(fields, "Local minimum · XYZ mm", "-1, -1, -1")
        self.maximum = planning_field(fields, "Local maximum · XYZ mm", "1, 1, 1")
        self.content.add_widget(fields)
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.apply_action = Action("Apply body draft", self.apply_body)
        self.remove_action = Action("Remove selected body", self.remove_body)
        self.save_action = Action("Save declared geometry…", self.save_profile)
        self.discard_action = Action("Discard body draft", self.discard_body)
        for action in (self.apply_action, self.discard_action, self.remove_action, self.save_action):
            actions.add_widget(action)
        self.content.add_widget(actions)
        self.draft_status = flowing_text("No unapplied body drafts.", 28)
        self.content.add_widget(self.draft_status)
        self.exclusions = planning_field(self.content, "Excluded mounted pairs · one 'body | body' per line", "")
        self.exclusions.multiline = True
        self.exclusions.height = dp(72)
        self.exclusions.parent.height = dp(96)
        self.content.add_widget(
            flowing_text(
                "Exclusions omit only named pairs. Use them for intentional mounting contact; they are retained in the profile and report. No pair is silently ignored.",
                40,
            )
        )
        self.tolerance = planning_field(
            self.content, "Maximum unresolved motion bound · mm", 0.05, quantity="length", minimum=0.000001, maximum=10
        )
        self.review_action = Action("Review continuous joint clearance", self.review)
        self.content.add_widget(self.review_action)
        files = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.save_review_action = Action("Save clearance review…", self.save_review, disabled=True)
        self.load_review_action = Action("Load clearance review…", self.load_review)
        files.add_widget(self.save_review_action)
        files.add_widget(self.load_review_action)
        self.content.add_widget(files)
        self.note = flowing_text(
            "Declare at least two bodies, then review the entered waypoint rows. Geometry completeness and physical registration remain unqualified.",
            50,
        )
        self.content.add_widget(self.note)
        self.contact = planning_choice(self.content, "Possible contact interval", ("No review",))
        self.contact.bind(text=lambda *_: self.select_contact())
        self.projection_note = flowing_text("World projections · XY left / XZ right · equal scale within each view", 28)
        self.content.add_widget(self.projection_note)
        self.plot = JointBodyPlot()
        self.plot.height = 0
        self.content.add_widget(self.plot)
        self.details = flowing_text("", 0)
        self.content.add_widget(self.details)
        for field in (self.name_field, self.frame, self.minimum, self.maximum, self.exclusions, self.tolerance):
            field.bind(text=self.changed)

    def changed(self, *_):
        if not self.syncing:
            if self.body_text() != self.body_baseline:
                self.body_drafts[self.body_selection] = self.body_text()
            else:
                self.body_drafts.pop(self.body_selection, None)
            self.refresh_drafts()
            self.owner._invalidate()

    def refresh_drafts(self):
        self.draft_status.text = (
            f"{len(self.body_drafts)} retained body drafts · apply or discard before review/save."
            if self.body_drafts
            else "No unapplied body drafts."
        )

    def discard_body(self):
        self.body_drafts.pop(self.body_selection, None)
        self.fill_body()
        self.refresh_drafts()
        self.owner._invalidate()

    def clear_result(self):
        self.result = None
        self.save_review_action.disabled = True
        self.review_inputs = None
        self.contact.values = ("No review",)
        self.contact.text = "No review"
        self.plot.geometry = ()
        self.plot.height = 0
        self.plot.draw()
        self.details.text = ""
        self.note.text = "Inputs changed · review the current declared bodies and joint route."

    def set_profile(self, reset_drafts=True):
        self.syncing = True
        try:
            if reset_drafts:
                self.body_drafts = {}
            machine = machine_from_record(self.owner.record)
            self.frames = {"World": ("world", 0)}
            for frame, title, chain in (
                ("tool", "Spindle", machine.tool_chain),
                ("work", "Workpiece", machine.work_chain),
            ):
                self.frames[title + " base"] = (frame, 0)
                for i, joint in enumerate(chain):
                    self.frames[f"{title} after {joint.name}"] = (frame, i + 1)
            self.frame.values = tuple(self.frames)
            bodies, _excluded = bodies_from_record(self.owner.record, machine)
            self.choice_names = {"New body": None}
            self.choice_names.update({f"{i + 1} · {b.name}": b.name for i, b in enumerate(bodies)})
            self.choice.values = tuple(self.choice_names)
            self.choice.text = "New body"
            self.exclusions.text = "\n".join(
                " | ".join(pair) for pair in self.owner.record.get("collision_exclusions", [])
            )
            self.fill_body()
        finally:
            self.syncing = False
        self.clear_result()
        self.refresh_drafts()
        self.scene_capture.source_changed()

    def fill_body(self, *_):
        before = self.syncing
        self.syncing = True
        try:
            bodies, _ = bodies_from_record(self.owner.record, machine_from_record(self.owner.record))
            name = self.choice_names.get(self.choice.text)
            self.body_selection = name
            body = next((b for b in bodies if b.name == name), None)
            self.name_field.text = body.name if body else f"Body {len(bodies) + 1}"
            attachment = (body.frame, body.joint_count) if body else ("world", 0)
            self.frame.text = next(name for name, value in self.frames.items() if value == attachment)
            self.minimum.text = (
                ", ".join(format(v, ".12g") for v in body.bounds.minimum.tuple) if body else "-1, -1, -1"
            )
            self.maximum.text = ", ".join(format(v, ".12g") for v in body.bounds.maximum.tuple) if body else "1, 1, 1"
            self.body_baseline = self.body_text()
            if self.body_selection in self.body_drafts:
                for field, text in zip(
                    (self.name_field, self.frame, self.minimum, self.maximum), self.body_drafts[self.body_selection]
                ):
                    field.text = text
        finally:
            self.syncing = before
        self.refresh_drafts()

    def body_text(self):
        return tuple(field.text for field in (self.name_field, self.frame, self.minimum, self.maximum))

    def pair_rows(self):
        if len(self.exclusions.text) > 8192:
            raise ValueError("Excluded-pair input exceeds 8192 characters")
        return [[part.strip() for part in row.split("|")] for row in self.exclusions.text.splitlines() if row.strip()]

    def draft_profile(self):
        if self.body_drafts:
            raise ValueError("Apply or discard all retained body drafts before saving or reviewing geometry")
        record = deepcopy(self.owner.record)
        record["collision_exclusions"] = self.pair_rows()
        machine_from_record(record)
        return record

    def apply_body(self):
        if self.owner.running:
            return
        try:
            if max(len(self.minimum.text), len(self.maximum.text)) > 256:
                raise ValueError("Body bounds exceed the bounded input size")
            frame, count = self.frames[self.frame.text]
            point = lambda field: vector([float(v.strip()) for v in field.text.split(",")]).tuple
            row = {
                "name": self.name_field.text.strip(),
                "frame": frame,
                "joint_count": count,
                "minimum_mm": point(self.minimum),
                "maximum_mm": point(self.maximum),
            }
            record = deepcopy(self.owner.record)
            rows = list(record.get("collision_bodies", []))
            index = next((i for i, b in enumerate(rows) if b["name"] == self.choice_names[self.choice.text]), None)
            if index is None:
                rows.append(row)
            else:
                rows[index] = row
            record["collision_bodies"] = rows
            record["collision_exclusions"] = self.pair_rows()
            machine_from_record(record)
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            self.note.text = "Body draft retained: " + str(exc)
            return
        self.owner._invalidate()
        self.owner.record = record
        self.body_drafts.pop(self.body_selection, None)
        self.set_profile(reset_drafts=False)
        self.choice.text = next(c for c, name in self.choice_names.items() if name == row["name"])
        self.owner.profile_note.text = (
            f"Edited local declaration · profile {profile_digest(record)[:12]} · save to retain geometry"
        )
        self.note.text = "Body applied locally. Save geometry to retain it; review the current joint route."

    def remove_body(self):
        if self.owner.running or self.choice.text == "New body":
            return
        name = self.choice_names[self.choice.text]
        record = deepcopy(self.owner.record)
        record["collision_bodies"] = [b for b in record.get("collision_bodies", []) if b["name"] != name]
        try:
            record["collision_exclusions"] = [p for p in self.pair_rows() if name not in p]
            machine_from_record(record)
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = str(exc)
            return
        self.owner._invalidate()
        self.owner.record = record
        self.body_drafts.pop(self.body_selection, None)
        self.set_profile(reset_drafts=False)
        self.note.text = f"Removed {name} and its excluded pairs locally. Save geometry to retain the change."

    def save_profile(self):
        if self.owner.running:
            return
        try:
            record = self.draft_profile()
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = str(exc)
            return
        from carveracontroller.machine.kinematic_profile_io import save_kinematic_profile

        generation = self.owner.generation

        def chosen(path):
            if self.owner.closed or generation != self.owner.generation:
                self.note.text = "Geometry changed while choosing a file; save the current declaration again."
                return
            self.owner._start(
                lambda cancelled: save_kinematic_profile(path, record, cancelled=cancelled),
                lambda receipt: setattr(
                    self.note, "text", f"Saved declared geometry · SHA256 {receipt[:12]} · no controller change"
                ),
                error_target=self.note,
            )

        self.owner.workspace.choose_profile_file(
            chosen, save=True, extension=".json", title="Save declared joint geometry"
        )

    def review(self):
        if self.owner.running:
            return
        try:
            record = self.draft_profile()
            machine = machine_from_record(record)
            bodies, excluded = bodies_from_record(record, machine)
            waypoints = self.owner._waypoints(machine)
            tolerance = self.tolerance.value()
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = "Clearance unavailable: " + str(exc)
            return
        self.clear_result()
        self.note.text = "Bounding continuous articulated motion…"

        def completed(result):
            self.show_result(result, record, waypoints)

        self.owner._start(
            lambda cancelled: review_joint_clearance(
                machine, waypoints, bodies, excluded, tolerance_mm=tolerance, cancelled=cancelled
            ),
            completed,
            error_target=self.note,
        )

    def show_result(self, result, record, waypoints):
        machine = machine_from_record(record)
        bodies, excluded = bodies_from_record(record, machine)
        self.result = result
        self.save_review_action.disabled = False
        self.plot.height = dp(200)
        self.review_inputs = (machine, bodies, waypoints, record)
        self.note.text = (
            f"{len(result.contacts)} possible contact intervals · {result.tested_pairs} pair/segments · {result.intervals} bounded intervals\nMotion bound ≤ {result.tolerance_mm:g} mm. Declared bounding bodies only; no physical clearance or geometry-completeness qualification.\nExcluded pairs: "
            + (", ".join(" / ".join(p) for p in excluded) or "none")
        )
        self.contact.values = tuple(f"{i + 1} · {c.first} / {c.second}" for i, c in enumerate(result.contacts)) or (
            "No contact in declared envelopes",
        )
        self.contact.text = self.contact.values[0]
        self.select_contact()

    def save_review(self):
        if self.owner.running or self.result is None or self.review_inputs is None:
            return
        from carveracontroller.machine.joint_clearance_archive import save_joint_review

        _machine, _bodies, waypoints, record = self.review_inputs
        result, generation = self.result, self.owner.generation

        def chosen(path):
            if self.owner.closed or generation != self.owner.generation or self.result is not result:
                self.note.text = "Review changed while choosing a file; review current inputs before saving."
                return
            self.owner._start(
                lambda cancelled: save_joint_review(path, record, waypoints, result, cancelled=cancelled),
                lambda digest: setattr(
                    self.note,
                    "text",
                    f"Saved clearance review · SHA256 {digest[:12]} · geometry and entered route retained",
                ),
                error_target=self.note,
            )

        self.owner.workspace.choose_profile_file(
            chosen, save=True, extension=".cvclearance", title="Save declared clearance review"
        )

    def load_review(self):
        if self.owner.running:
            return
        if self.body_drafts:
            self.note.text = "Apply or discard retained body drafts before loading another review."
            return
        from carveracontroller.machine.joint_clearance_archive import load_joint_review

        generation = self.owner.generation

        def chosen(path):
            if self.owner.closed or generation != self.owner.generation:
                self.note.text = "Inputs changed while choosing a review; choose again."
                return

            def loaded(archive):
                self.owner._invalidate()
                self.owner.record = archive.record
                self.owner.topology.text = "Imported geometry"
                self.owner._show_profile(f"Recomputed review · SHA256 {archive.sha256[:12]}")
                machine = machine_from_record(archive.record)
                names = [j.name for j in machine.tool_chain + machine.work_chain]
                self.owner.seeds.text = "\n".join(
                    " ".join(repr(state[n]) for n in names) for state in archive.waypoints
                )
                self.tolerance.text = repr(archive.report.tolerance_mm)
                self.show_result(archive.report, archive.record, archive.waypoints)
                self.note.text = "Loaded and recomputed saved review.\n" + self.note.text

            self.owner._start(
                lambda cancelled: load_joint_review(path, cancelled=cancelled), loaded, error_target=self.note
            )

        self.owner.workspace.choose_asset_file(chosen, suffixes=(".cvclearance",))

    def select_contact(self):
        if self.result is None or self.review_inputs is None:
            return
        machine, bodies, waypoints, _record = self.review_inputs
        if self.result.contacts:
            index = self.contact.values.index(self.contact.text)
            c = self.result.contacts[index]
            fraction = (
                c.witness_fraction if c.witness_fraction is not None else (c.lower_fraction + c.upper_fraction) / 2
            )
            start, end = waypoints[c.segment : c.segment + 2]
            state = {name: start[name] + fraction * (end[name] - start[name]) for name in start}
            self.details.text = (
                f"Segment {c.segment + 1} · earliest possible interval for this pair {100 * c.lower_fraction:.5g}–{100 * c.upper_fraction:.5g}%\n"
                + (
                    "Declared-box overlap at the displayed midpoint."
                    if c.witness_fraction is not None
                    else "Unresolved conservative interval; no overlap witness established."
                )
                + f"\nCombined motion enclosure {c.motion_bound_mm:.5g} mm\n"
                + " · ".join(f"{name} {value:.5g}" for name, value in state.items())
            )
            selected = (c.first, c.second)
        else:
            state = waypoints[0]
            selected = ()
            self.details.text = "No overlap over the entire entered route in these declared bounding bodies. Unmodeled bodies, registration, cutting stock and machine execution remain unqualified."
        self.plot.show(machine, bodies, state, selected)
