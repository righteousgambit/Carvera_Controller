"""Detached all-move machine clearance with source-linked evidence navigation."""

from __future__ import annotations

from typing import Any

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.calculation_progress import CalculationProgress, calculation_status
from carveracontroller.machine.contact_pose_material import prepare_contact_material
from carveracontroller.machine.contact_pose_view import prepare_contact_pose_view
from carveracontroller.machine.program_surface_clearance import (
    contact_triangles,
    group_member_contact,
    occupancy_witness,
    rotating_witness,
)
from carveracontroller.machine.stock_generated_clearance import (
    GeneratedMachineClearance,
    locate_generated_cad_contacts,
    locate_generated_first_contacts,
    review_generated_finish,
)


class GeneratedMachineControls(PlanningCard):
    def __init__(self, generated):
        super().__init__("Whole-path machine clearance")
        from carveracontroller.desktop_program_surfaces import SurfaceContactPlot

        self.generated = generated
        self.result: GeneratedMachineClearance | None = None
        self.rows: tuple[tuple[str, Any], ...] = ()
        self.machine_rows: tuple[tuple[str, Any], ...] = ()
        self.first_study = None
        self.cad_study = None
        self.pose_stage = self.selected_pose_row = None
        self.member_visible = False
        self.generation = self.page = 0
        self.progress = self.progress_event = None
        self.progress_target = None
        self.content.add_widget(
            flowing_text(
                "Review every generated move against the retained moving machine, workholding and ATC. Keeps the generated stock comparisons and loaded program separate.",
                45,
            )
        )
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.review = Action("Review whole path", self.calculate, disabled=True)
        self.cancel_button = Action("Cancel review", lambda: self.owner.cancel(), disabled=True)
        actions.add_widget(self.review)
        actions.add_widget(self.cancel_button)
        self.content.add_widget(actions)
        self.status = flowing_text("Generate a retained finishing comparison first.", 40)
        self.content.add_widget(self.status)
        self.first_button = Action("Locate first contacts", self.locate_first, disabled=True)
        contacts = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.first_button.text = "Rotating entry"
        self.cad_button = Action("CAD contact poses", self.locate_cad, disabled=True)
        contacts.add_widget(self.first_button)
        contacts.add_widget(self.cad_button)
        self.content.add_widget(contacts)
        self.first_status = flowing_text(
            "Earliest contact study uses the complete retained rotating-pair timeline.", 40
        )
        self.content.add_widget(self.first_status)
        self.cad_status = flowing_text("Locate CAD contact poses after the complete machine review.", 40)
        self.content.add_widget(self.cad_status)
        self.result_view = planning_choice(
            self.content, "Evidence view", ("Whole path records", "First contacts by pair", "CAD first contacts")
        )
        self.result_view.bind(text=self.change_view)
        self.choice = planning_choice(self.content, "All machine results · 64 per page", ("No machine review",))
        self.choice.bind(text=self.select)
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous results", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next results", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        self.pair = planning_field(self.content, "Original triangle pair · zero based", "0")
        self.pair.bind(text=self.select)
        self.pair_container = self.pair.parent
        self.pair_height = self.pair_container.height
        self.detail = flowing_text("No machine result selected.", 45)
        self.content.add_widget(self.detail)
        self.plot = SurfaceContactPlot()
        self.content.add_widget(self.plot)
        pose_actions = AdaptiveGrid(max_cols=3, min_width=145, row_height=36, spacing=dp(6))
        self.pose_button = Action("View complete pose", self.view_pose, disabled=True)
        self.pose_return = Action("Return to program", self.close_pose, disabled=True)
        self.pose_fit = Action("Fit contact view", self.fit_pose, disabled=True)
        for action in (self.pose_button, self.pose_return, self.pose_fit):
            pose_actions.add_widget(action)
        self.content.add_widget(pose_actions)
        self.pose_material = planning_choice(self.content, "Stock at contact time", ("Machine only",))
        self.pose_material.disabled = True
        self.pose_material.bind(text=self.change_pose_material)
        self.pose_bodies = planning_choice(self.content, "Contact view visibility", ("No contact pose view",))
        self.pose_bodies.disabled = True
        self.pose_bodies.bind(text=self.show_pose_bodies)
        self.pose_status = flowing_text("Select a CAD contact to view the complete retained assembly on the left.", 40)
        self.content.add_widget(self.pose_status)
        scope = PlanningCard("Whole-path identity & coverage")
        self.scope = flowing_text("No retained generated machine review.", 45)
        scope.content.add_widget(self.scope)
        self.first_scope = flowing_text("No first-contact study.", 40)
        scope.content.add_widget(self.first_scope)
        self.cad_scope = flowing_text("No CAD first-contact study.", 40)
        scope.content.add_widget(self.cad_scope)
        self.pose_scope = flowing_text("No detached contact-pose display.", 40)
        scope.content.add_widget(self.pose_scope)
        self.content.add_widget(scope)

    @property
    def owner(self):
        return self.generated.owner

    def clear(self):
        self.close_pose()
        self.generation += 1
        self.result = None
        self.rows = ()
        self.machine_rows = ()
        self.first_study = None
        self.cad_study = None
        self.first_status.text = "Locate first contacts after the complete machine review."
        self.first_scope.text = "No first-contact study."
        self.cad_scope.text = "No CAD first-contact study."
        self.pose_scope.text = "No detached contact-pose display."
        self.pose_material.values = ("Machine only",)
        self.pose_material.text = "Machine only"
        self.cad_status.text = "Locate CAD contact poses after the complete machine review."
        self.page = 0
        self.status.text = "Generate or review the current complete finishing path."
        self.scope.text = "No retained generated machine review."
        self.render_page()

    def stop_progress(self):
        if self.progress_event is not None:
            self.progress_event.cancel()
            self.progress_event = None
        if self.progress is not None:
            self.progress.finish("stopped")

    def tick(self, *_):
        if not self.owner.running or self.owner.closed:
            self.stop_progress()
        elif self.progress is not None:
            target = self.progress_target or self.status
            target.text = calculation_status(
                self.progress.snapshot(), cancelling=self.owner.cancel_event.is_set()
            ).replace("segments", "work items")

    def set_busy(self, busy):
        if not busy:
            self.stop_progress()
        self.review.disabled = busy or self.generated.result is None
        self.first_button.disabled = busy or self.result is None
        self.cad_button.disabled = busy or self.result is None
        self.result_view.disabled = busy
        self.cancel_button.disabled = not busy
        self.choice.disabled = busy
        self.pair.disabled = busy or not self.member_visible
        self.previous.disabled = busy or self.page == 0
        self.next.disabled = busy or (self.page + 1) * 64 >= len(self.rows)
        self.pose_button.disabled = busy or self.selected_pose_row is None or self.pose_stage is not None
        self.pose_material.disabled = busy or self.selected_pose_row is None

    def change_pose_material(self, *_):
        self.generation += 1
        if self.pose_stage is not None:
            self.close_pose()
            self.view_pose()

    def close_pose(self):
        if self.pose_stage is not None:
            self.pose_stage.close()

    def fit_pose(self):
        if self.pose_stage is not None:
            self.pose_stage.canvas.fit()

    def show_pose_bodies(self, *_):
        if self.pose_stage is None:
            return
        canvas = self.pose_stage.canvas
        value = self.pose_bodies.text
        if value == "All declared bodies":
            canvas.set_bodies(tuple(b.name for b in canvas.scene.bodies))
        elif value in ("Contacting bodies", "Original contact surfaces"):
            canvas.set_bodies(canvas.scene.pair, value == "Original contact surfaces")
        elif value == "Stock and target":
            canvas.set_bodies(tuple(b.name for b in canvas.scene.bodies if b.kind in ("remaining", "target")))
        elif value in self.pose_bodies.values:
            canvas.set_bodies((canvas.scene.bodies[self.pose_bodies.values.index(value) - 3].name,))

    def view_pose(self):
        source, row = self.result, self.selected_pose_row
        if self.owner.running or self.owner.closed or source is None or row is None or self.pose_stage is not None:
            return
        generation = self.generation
        material_state = self.pose_material.text
        parent = self.generated.target.sections.surfaces.result
        try:
            member = int(self.pair.text) if row.group is not None else 0
        except ValueError:
            self.pose_status.text = "Select an original retained face pair before viewing its pose."
            return
        self.pose_status.text = "Preparing all retained bodies and original CAD faces…"

        def current():
            return (
                not self.owner.closed
                and self.generation == generation
                and self.result is source
                and self.selected_pose_row is row
                and self.pose_material.text == material_state
                and self.generated.result is source.plan
                and self.generated.target.sections.surfaces.result is parent
            )

        def work(cancelled):
            scene = prepare_contact_pose_view(source.scene, row, member, cancelled=cancelled)
            material = (
                None
                if material_state == "Machine only"
                else prepare_contact_material(source, scene, material_state, cancelled=cancelled)
            )
            return scene if material is None else material.view, material

        def complete(delivery):
            scene, material = delivery
            if not current():
                self.pose_status.text = "Contact, generated path or retained parent changed; pose view withheld."
                return
            from carveracontroller.desktop_contact_pose import ContactPoseStage

            def closed():
                self.pose_stage = None
                self.pose_bodies.disabled = self.pose_return.disabled = self.pose_fit.disabled = True
                self.pose_status.text = "Program view restored. The contact review remains retained."
                self.set_busy(self.owner.running)

            self.pose_stage = ContactPoseStage(
                self.owner.workspace, scene, lambda text: setattr(self.pose_status, "text", text), current, closed
            )
            self.pose_stage.material = material
            self.pose_bodies.values = (
                ("All declared bodies", "Contacting bodies", "Original contact surfaces")
                + tuple(
                    f"{i + 1}. {b.name}{' · envelope only' if b.envelope_only else ''}"
                    for i, b in enumerate(scene.bodies)
                )
                + (("Stock and target",) if material is not None else ())
            )
            self.pose_bodies.text = "All declared bodies"
            self.pose_bodies.disabled = self.pose_return.disabled = self.pose_fit.disabled = False
            self.pose_button.disabled = True
            self.pose_scope.text = (
                f"{len(scene.bodies)} displayed bodies · {sum(len(b.triangles) for b in scene.bodies if not b.envelope_only and b.kind == 'cad')} original machine CAD faces\n"
                f"Envelope only: {', '.join(b.name for b in scene.bodies if b.envelope_only) or 'none'}.\n{scene.qualification}"
                + (
                    f"\n{material.state}: {material.remaining_mm3:g} mm³ remaining / {material.removed_mm3:g} mm³ removed through move {scene.pose.segment_index + 1} at t={scene.pose.sample}.\nGrid resolution {material.resolution_mm:g} mm · {material.cell_work} cell-work.\n{material.qualification}"
                    if material is not None
                    else f"\nSelected stock {source.replaced_initial_stock}: choose a retained stock state to show material at this contact time."
                )
            )

        self.owner._start(
            work,
            complete,
            error_target=self.pose_status,
        )

    def calculate(self):
        plan = self.generated.result
        parent = self.generated.target.sections.surfaces.result
        if self.owner.running or plan is None or parent is None:
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("Whole generated machine path")
        self.progress_target = self.status
        observation = self.progress
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)

        def work(cancelled):
            def progress(phase, done, total):
                if observation.snapshot()["phase"] != phase:
                    observation.phase(phase, total)
                observation.advance(done)

            result = review_generated_finish(plan, parent, cancelled=cancelled, progress=progress)
            scene = result.scene
            rows = (
                tuple(("group", r) for r in scene.groups)
                + tuple(("solid", r) for r in scene.occupancy)
                + tuple(("rotating", r) for r in scene.rotating)
                + tuple(("gap", r) for r in scene.gaps)
            )
            return result, rows

        def complete(delivery):
            if (
                self.generation != generation
                or self.generated.result is not plan
                or self.generated.target.sections.surfaces.result is not parent
            ):
                self.status.text = "Generated path, target or machine review changed; complete result withheld."
                return
            self.result, self.rows = delivery
            self.pose_material.values = ("Machine only",) + tuple(plan.states)
            self.pose_material.text = next(iter(plan.states))
            self.machine_rows = self.rows
            self.first_study = None
            self.cad_study = None
            self.first_status.text = "Locate first contacts for this retained machine review."
            self.first_scope.text = "No first-contact study."
            self.cad_scope.text = "No CAD first-contact study."
            self.cad_status.text = "Locate CAD contact poses for this retained machine review."
            self.result_view.text = "Whole path records"
            scene = self.result.scene
            self.page = 0
            self.status.text = f"Complete: {len(plan.moves)} moves · T{plan.tool} · {len(self.result.included_bodies)} bodies\n{scene.refined_pairs} CAD pairs / {scene.rigid_reused_pairs} verified geometric queries reused\n{len(scene.groups)} contact groups · {len(scene.occupancy)} solid intervals · {len(scene.rotating)} rotating records · {len(scene.gaps)} geometry gaps / {len(plan.declaration_gaps)} assembly notes. Inspect evidence before machining."
            self.scope.text = (
                f"Proposal SHA256 {self.result.proposal_sha256}\nTarget SHA256 {plan.analysis.target.source_sha256}\nSelected initial stock replaced: {self.result.replaced_initial_stock}\nIncluded: {', '.join(self.result.included_bodies)}\nBroad: {scene.body_review.tested_pairs} pair memberships / {scene.body_review.intervals} unique intervals\nCAD: {scene.nodes} nodes / {scene.triangle_pairs} face pairs · unique groups/members {scene.group_counts}\n{len(plan.states)} independent stock-state comparisons remain attached; no current physical stock claim.\n"
                + "\n".join(plan.declaration_gaps)
                + "\n"
                + self.result.qualification
            )
            self.render_page()

        self.owner._start(work, complete, error_target=self.status)

    def locate_first(self):
        source = self.result
        if self.owner.running or source is None:
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("First rotating contact by pair")
        self.progress_target = self.first_status
        observation = self.progress
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)

        def work(cancelled):
            def progress(done, total):
                if observation.snapshot()["phase"] != "Complete rotating pair timelines":
                    observation.phase("Complete rotating pair timelines", total)
                observation.advance(done)

            return locate_generated_first_contacts(source, cancelled=cancelled, progress=progress)

        def complete(study):
            if (
                self.generation != generation
                or self.result is not source
                or self.generated.result is not source.plan
                or self.generated.target.sections.surfaces.result is not source.parent
            ):
                self.first_status.text = "Generated path, target or machine changed; first-contact study withheld."
                return
            self.first_study = study
            self.first_status.text = f"Complete: {len(study.pairs)} rotating pairs · {study.prefix_queries} exact prefix queries\n{sum(r.state == 'bounded_contact' for r in study.pairs)} entry brackets · {sum(r.state == 'initial_overlap' for r in study.pairs)} starting overlaps · {sum(not r.earliest_proven for r in study.pairs)} unavailable earliest claims\nDeclared geometry · {study.geometry_gaps} parent gaps. Coverage details below."
            self.first_scope.text = study.qualification
            self.result_view.text = "First contacts by pair"
            self.change_view()

        self.owner._start(work, complete, error_target=self.first_status)

    def locate_cad(self):
        source = self.result
        if self.owner.running or source is None:
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("CAD contact poses")
        self.progress_target = self.cad_status
        observation = self.progress
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)

        def work(cancelled):
            def progress(done, total):
                if observation.snapshot()["phase"] != "Complete CAD timelines":
                    observation.phase("Complete CAD timelines", total)
                observation.advance(done)

            return locate_generated_cad_contacts(source, cancelled=cancelled, progress=progress)

        def complete(study):
            if (
                self.generation != generation
                or self.result is not source
                or self.generated.result is not source.plan
                or self.generated.target.sections.surfaces.result is not source.parent
            ):
                self.cad_status.text = "Generated path, target or machine changed; CAD contact study withheld."
                return
            self.cad_study = study
            self.cad_status.text = f"Complete: {len(study.pairs)} CAD pairs · {study.timeline_rows} retained records\n{sum(r.pose is not None for r in study.pairs)} entry/containment poses · {sum(not r.earliest_proven for r in study.pairs)} unavailable earliest claims\n{study.original_group_members} original grouped face pairs retained. Coverage details below."
            self.cad_scope.text = study.qualification
            self.result_view.text = "CAD first contacts"
            self.change_view()

        self.owner._start(work, complete, error_target=self.cad_status)

    def change_view(self, *_):
        if self.result_view.text == "CAD first contacts" and self.cad_study is not None:
            self.rows = tuple(("cad_first", r) for r in self.cad_study.pairs)
            self.page = 0
            self.render_page()
            return
        self.rows = (
            tuple(("first", r) for r in self.first_study.pairs)
            if self.result_view.text == "First contacts by pair" and self.first_study is not None
            else self.machine_rows
        )
        self.page = 0
        self.render_page()

    def render_page(self):
        start = self.page * 64
        labels = {
            "initial_overlap": "Starting overlap",
            "bounded_contact": "Entry bracket",
            "separated": "Separated timeline",
            "unavailable": "Earliest unavailable",
            "surface_entry": "CAD entry",
            "contained": "Initial containment",
        }
        self.choice.values = tuple(
            f"{start + i + 1}. {labels[r.state] + ' · T' + str(r.tool) if kind in ('first', 'cad_first') else kind + ' · move ' + str(r.segment_index + 1)}"
            for i, (kind, r) in enumerate(self.rows[start : start + 64])
        ) or ("No machine results",)
        self.choice.text = self.choice.values[0]
        self.select()
        self.set_busy(self.owner.running)

    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.rows) - 1) // 64), self.page + delta))
        self.pair.text = "0"
        self.render_page()

    def select(self, *_):
        self.close_pose()
        self.selected_pose_row = None
        self.pose_button.disabled = True
        self.plot.geometry = ()
        self.plot.height = 0
        token = self.choice.text.partition(".")[0]
        index = int(token) - 1 if token.isdecimal() else -1
        if self.result is None or not 0 <= index < len(self.rows):
            self.show_members(False)
            self.detail.text = "No machine result selected."
            self.plot.draw()
            return
        kind, row = self.rows[index]
        self.show_members(kind == "group" or (kind == "cad_first" and row.group is not None))
        scene = self.result.scene
        if kind == "cad_first":
            self.selected_pose_row = row if row.pose is not None else None
            self.pose_button.disabled = self.owner.running or self.selected_pose_row is None
            self.detail.text = f"T{row.tool} · {row.first} / {row.second}\n{row.state.replace('_', ' ')} · {'earliest in retained geometry' if row.earliest_proven else 'earliest volume contact unavailable'}\n{row.reason}"
            if row.segment_index is None:
                self.plot.draw()
                return
            self.generated.page = row.segment_index // 64
            self.generated.render_page()
            self.generated.moves.text = self.generated.moves.values[row.segment_index % 64]
            if row.pose is not None:
                self.detail.text += f"\nMove {row.segment_index + 1} · t={row.pose.sample} ({100 * float(row.pose.sample):.6f}%)\nNominal XYZ mm {tuple(round(float(v), 6) for v in row.pose.joints_mm)}\n{len(row.pose.bodies)} declared body placements retained."
                for name in (row.first, row.second):
                    body = next(b for b in row.pose.bodies if b.name == name)
                    self.detail.text += f"\n{name} origin {tuple(round(float(v), 6) for v in body.translation_mm)} mm"
            if row.surface is not None:
                try:
                    contact = row.surface
                    if row.group is not None:
                        from dataclasses import replace

                        member = int(self.pair.text)
                        selected = group_member_contact(row.group, member)
                        contact = replace(
                            row.surface, contact=replace(selected.contact, lower=row.lower, upper=row.upper)
                        )
                        self.detail.text += f"\nOriginal pair {member + 1}/{len(row.group.group.triangle_pairs)}"
                    self.plot.geometry = contact_triangles(scene, contact)
                    self.plot.primary_count = 1
                    self.detail.text += f"\nOriginal faces {contact.contact.first_triangle} / {contact.contact.second_triangle}\nNominal entry surfaces · outward allowance retained."
                except ValueError as exc:
                    self.detail.text += "\n" + str(exc)
            elif row.occupancy is not None:
                point = occupancy_witness(scene, row.occupancy)
                if point is not None:
                    self.plot.geometry = ((point, point, point),)
                    self.plot.primary_count = 1
                    self.detail.text += f"\nContained {row.occupancy.interval.contained_side} body · original face {row.occupancy.interval.witness_triangle}\nNominal world witness {point}"
            self.plot.height = dp(180) if self.plot.geometry else 0
            self.plot.draw()
            return
        if kind == "first":
            claim = (
                "whole modeled timeline separated"
                if row.state == "separated"
                else "bounded in declared geometry"
                if row.earliest_proven
                else "unavailable"
            )
            self.detail.text = (
                f"T{row.tool} · {row.first} / {row.second}\n{row.state.replace('_', ' ')} · {claim}\n{row.reason}"
            )
            if row.segment_index is None:
                self.plot.draw()
                return
            self.detail.text += f"\nMove {row.segment_index + 1} · exact entry bracket [{row.lower}, {row.upper}]"
            if row.lower is not None and row.upper is not None:
                self.detail.text += f"\n{100 * float(row.lower):.6f}–{100 * float(row.upper):.6f}% of this move · width {float(row.upper - row.lower):.3g}"
            self.generated.page = row.segment_index // 64
            self.generated.render_page()
            self.generated.moves.text = self.generated.moves.values[row.segment_index % 64]
            if row.witness is not None:
                self.plot.geometry, point = rotating_witness(scene, row.witness)
                if not self.plot.geometry and point is not None:
                    self.plot.geometry = ((point, point, point),)
                self.plot.primary_count = max(1, len(self.plot.geometry) - 1)
                self.detail.text += f"\nSection {row.witness.result.section_index + 1} · original face {row.witness.result.witness_triangle}\nWitness t={row.witness.result.sample} · world {point}\nBracket applies to padded declared geometry; no physical clearance claim."
            self.plot.height = dp(180) if self.plot.geometry else 0
            self.plot.draw()
            return
        move = self.result.plan.moves[row.segment_index]
        self.generated.page = row.segment_index // 64
        self.generated.render_page()
        self.generated.moves.text = self.generated.moves.values[row.segment_index % 64]
        names = f"{row.first} / {row.second}"
        self.detail.text = f"Move {row.segment_index + 1}: {move.kind} · layer {move.layer} · T{row.tool}\n{names}\n"
        if kind == "group":
            try:
                member = int(self.pair.text)
                if not 0 <= member < len(row.group.triangle_pairs):
                    raise ValueError("Triangle pair index outside the complete contact group")
                self.plot.geometry = contact_triangles(scene, group_member_contact(row, member))
                self.plot.primary_count = 1
                self.detail.text += f"Exact contact interval [{row.group.lower}, {row.group.upper}]\nPair {member + 1}/{len(row.group.triangle_pairs)} · original faces {row.group.triangle_pairs[member]}\nNominal midpoint; XY left / XZ right."
            except ValueError as exc:
                self.detail.text += str(exc)
        elif kind == "solid":
            self.detail.text += f"Closed solid {row.interval.state} · [{row.interval.lower}, {row.interval.upper}]"
            witness = occupancy_witness(scene, row)
            if witness is not None:
                self.plot.geometry = ((witness, witness, witness),)
                self.plot.primary_count = 1
        elif kind == "rotating":
            self.plot.geometry, witness = rotating_witness(scene, row)
            self.plot.primary_count = max(1, len(self.plot.geometry) - 1)
            self.detail.text += f"Section {row.result.section_index + 1} · {row.result.state}\nOriginal face {row.result.witness_triangle} · world witness {witness}\nExistence witness, not certified earliest contact. {row.result.reason}"
        else:
            self.detail.text += row.reason
        self.plot.height = dp(180) if self.plot.geometry else 0
        self.plot.draw()

    def show_members(self, visible):
        self.member_visible = visible
        self.pair.disabled = self.owner.running or not visible
        self.pair_container.height = self.pair_height if visible else 0
        self.pair_container.opacity = int(visible)
