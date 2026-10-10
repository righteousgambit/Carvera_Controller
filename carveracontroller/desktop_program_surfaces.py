"""Compact, source-linked triangle-surface review; no controller writes."""

from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, DANGER, Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice
from carveracontroller.machine.program_surface_clearance import contact_triangles, occupancy_witness


class SurfaceContactPlot(Widget):
    """Equal-scale XY/XZ projections of two retained triangles."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=0, **kwargs)
        self.geometry = ()
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *_):
        self.canvas.clear()
        if not self.geometry:
            return
        points = [p for triangle in self.geometry for p in triangle]
        for pane, vertical in enumerate((1, 2)):
            width, height = max(1, self.width / 2 - dp(24)), max(1, self.height - dp(24))
            lo = (min(p[0] for p in points), min(p[vertical] for p in points))
            hi = (max(p[0] for p in points), max(p[vertical] for p in points))
            scale = min(width / max(1e-6, hi[0] - lo[0]), height / max(1e-6, hi[1] - lo[1]))
            x = self.x + pane * self.width / 2 + dp(12) + (width - (hi[0] - lo[0]) * scale) / 2
            y = self.y + dp(12) + (height - (hi[1] - lo[1]) * scale) / 2
            for index, triangle in enumerate(self.geometry):
                path = []
                for p in (*triangle, triangle[0]):
                    path.extend((x + (p[0] - lo[0]) * scale, y + (p[vertical] - lo[1]) * scale))
                with self.canvas:
                    Color(*(DANGER if index else ACCENT))
                    Line(points=path, width=dp(1.3))


class SurfaceClearanceControls(PlanningCard):
    def __init__(self, parent):
        super().__init__("CAD surfaces & solids")
        self.review = parent
        self.result = self.selected = None
        self.page = 0
        self.rows = ()
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=42, spacing=dp(6))
        self.whole = Action("Review program surfaces", lambda: parent.review(False, surfaces=True))
        self.operation = Action("Review operation surfaces", lambda: parent.review(True, surfaces=True))
        for action in (self.whole, self.operation):
            action.bind(width=lambda button, width: setattr(button, "text_size", (max(10, width - dp(12)), None)))
            actions.add_widget(action)
        self.content.add_widget(actions)
        files = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.save_action = Action("Save surface review…", self.save_review, disabled=True)
        self.load_action = Action("Open surface review…", self.load_review)
        files.add_widget(self.save_action)
        files.add_widget(self.load_action)
        self.content.add_widget(files)
        self.exchange_status = flowing_text("Reopen prepared triangles and solid intervals as a detached review.", 35)
        self.content.add_widget(self.exchange_status)
        self.note = flowing_text(
            "Refine body candidates against all imported CAD and stock triangles. Validated closed meshes also resolve solid containment.",
            45,
        )
        self.content.add_widget(self.note)
        self.choice = planning_choice(self.content, "Contact, solid interval or remaining gap", ("No surface review",))
        self.choice.bind(text=lambda *_: self.select())
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous results", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next results", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        self.source = Action("Inspect source", self.inspect_source, disabled=True)
        self.content.add_widget(self.source)
        self.detail = flowing_text("", 0)
        self.content.add_widget(self.detail)
        self.plot = SurfaceContactPlot()
        self.content.add_widget(self.plot)
        self.scope = PlanningCard("Surface coverage & limits")
        self.scope_note = flowing_text("Surface reviews retain prepared triangles; body reviews retain envelopes.", 35)
        self.scope.content.add_widget(self.scope_note)
        self.content.add_widget(self.scope)

    def clear(self):
        self.result = self.selected = None
        self.rows = ()
        self.page = 0
        self.choice.values = ("No surface review",)
        self.choice.text = self.choice.values[0]
        self.previous.disabled = self.next.disabled = self.source.disabled = True
        self.save_action.disabled = True
        self.plot.geometry = ()
        self.plot.height = 0
        self.plot.draw()
        self.detail.text = ""
        self.note.text = "Review current CAD surfaces; no retained surface result."
        self.scope_note.text = "Surface reviews retain prepared triangles; body reviews retain envelopes."

    def show(self, result):
        self.result = result
        self.save_action.disabled = self.review.retained_inputs is None
        self.rows = (
            tuple(("contact", c) for c in result.contacts)
            + tuple((c.interval.state, c) for c in result.occupancy)
            + tuple(("gap", g) for g in result.gaps)
        )
        self.note.text = self.summary(result)
        self.scope_note.text = (
            f"{result.nodes} surface nodes · {result.triangle_pairs} triangle pairs\n"
            f"Solid work: {result.solid_counts[0]} steps · {result.solid_counts[1]} pairs · {result.solid_counts[2]} rays · {result.solid_counts[3]} queries\n"
            + result.qualification
        )
        self.page = 0
        self.refresh()

    def summary(self, result):
        return (
            f"{len(result.contacts)} possible triangle contacts · {len(result.gaps)} remaining pair gaps\n"
            f"{sum(c.interval.state == 'contained' for c in result.occupancy)} contained · {sum(c.interval.state == 'separated' for c in result.occupancy)} separated solid intervals\n"
            f"{result.refined_pairs} refined body pairs · {result.triangles} triangles\n"
            "Closed-solid containment requires valid complete meshes; rotating tool envelopes remain open."
        )

    def refresh(self):
        start = self.page * 64
        self.choice.values = tuple(
            f"{start + i + 1} · L{row.line} T{row.tool} · {kind} · {row.first} / {row.second}"
            for i, (kind, row) in enumerate(self.rows[start : start + 64])
        ) or ("No broad-phase pair to refine",)
        self.previous.disabled = self.page == 0
        self.next.disabled = start + 64 >= len(self.rows)
        self.choice.text = self.choice.values[0]
        self.select()

    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.rows) - 1) // 64), self.page + delta))
        self.refresh()

    def select(self):
        if self.result is None or not self.rows or self.choice.text not in self.choice.values:
            return
        kind, row = self.rows[self.page * 64 + self.choice.values.index(self.choice.text)]
        self.selected = row
        self.source.disabled = False
        self.plot.geometry = contact_triangles(self.result, row) if kind == "contact" else ()
        self.plot.height = dp(200) if self.plot.geometry else 0
        self.plot.draw()
        if kind == "contact":
            self.detail.text = (
                f"Retained faces {row.contact.first_triangle} / {row.contact.second_triangle}\n"
                f"Source parameter [{float(row.source_lower_ratio):.6g}, {float(row.source_upper_ratio):.6g}]\n"
                "Nominal chord pose at interval midpoint · XY left / XZ right. Enclosed curve contact has no exact surface witness."
            )
        elif kind in ("contained", "separated"):
            interval = row.interval
            left, right = ("[" if interval.lower_closed else "("), ("]" if interval.upper_closed else ")")
            self.detail.text = (
                f"Closed-solid {interval.state} · source parameter {left}{float(row.source_lower_ratio):.6g}, {float(row.source_upper_ratio):.6g}{right}\n"
                "Open endpoints retain possible surface contacts.\n"
            )
            witness = occupancy_witness(self.result, row)
            if witness is not None:
                body = row.first if interval.contained_side == "first" else row.second
                self.detail.text += (
                    f"Contained shell: {body} · face {interval.witness_triangle}\n"
                    f"Nominal chord witness (world mm): X{witness[0]:.6g} Y{witness[1]:.6g} Z{witness[2]:.6g}. "
                    "This is declared geometry, with no measured physical registration."
                )
            else:
                self.detail.text += (
                    "Separation applies to admitted solids in this interval, including declared cavities."
                )
        else:
            self.detail.text = row.reason.replace("_", " ")

    def inspect_source(self):
        if self.result is None or self.selected is None:
            return
        panel = self.review.card.owner.workspace.operation_panel
        if panel.program is None or panel.program.file_hash != self.result.body_review.program_hash:
            self.note.text = "Loaded source differs; surface source navigation withheld."
            return
        self.note.text = self.summary(self.result)
        panel.inspect_line(self.selected.line, seek=True)

    def save_review(self):
        owner = self.review.card.owner
        if owner.running or self.result is None or self.review.retained_inputs is None:
            return
        from carveracontroller.machine.program_surface_archive import save_surface_review

        result, inputs, generation = self.result, self.review.retained_inputs, owner.generation

        def chosen(path):
            if owner.closed or owner.generation != generation or self.result is not result:
                self.exchange_status.text = "Review changed while choosing a file; save the current result again."
                return
            owner._start(
                lambda cancelled: save_surface_review(path, inputs[0], inputs[1], result, cancelled=cancelled),
                lambda digest: setattr(
                    self.exchange_status,
                    "text",
                    f"Saved and recomputed surface review · SHA256 {digest[:12]}\n"
                    "Exact parser input, prepared triangles, rational intervals, witnesses and coverage gaps retained.",
                ),
                error_target=self.exchange_status,
            )

        owner.workspace.choose_profile_file(
            chosen, save=True, extension=".cvsurfacereview", title="Save CAD surface and solid review"
        )

    def load_review(self):
        owner = self.review.card.owner
        if owner.running:
            return
        from carveracontroller.machine.program_surface_archive import load_surface_review

        generation = owner.generation

        def chosen(path):
            if owner.closed or owner.generation != generation:
                self.exchange_status.text = "Inputs changed while choosing a review; choose again."
                return

            def loaded(archive):
                self.review.retained_inputs = (archive.source, dict(archive.work_offsets))
                self.review.show_result(archive.report.body_review)
                self.show(archive.report)
                self.exchange_status.text = (
                    f"Opened and recomputed detached surface review · SHA256 {archive.sha256[:12]}\n"
                    "Prepared geometry and scene identities retained; original CAD provenance and physical registration unverified. "
                    "Current program, scene, tools and datums preserved."
                )

            owner._start(
                lambda cancelled: load_surface_review(path, cancelled=cancelled),
                loaded,
                error_target=self.exchange_status,
            )

        owner.workspace.choose_asset_file(chosen, suffixes=(".cvsurfacereview",))
