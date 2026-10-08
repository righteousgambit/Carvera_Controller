"""Focused cross-feature plane review with explicit receipt provenance."""

import json

from kivy.metrics import dp

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, QuantityField, Surface
from carveracontroller.desktop_inspection_receipts import InspectionDeviationPlot
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.inspection_plane import plane_review


class InspectionPlaneReview(Surface):
    def __init__(self, owner):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(8), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.owner = owner
        self.result = None
        self.index = None
        self.exclusion_page = 0
        self.generation = 0
        self.policy = Choice(
            text="Latest per feature",
            values=("Latest per feature", "Earliest per feature"),
        )
        self.add_widget(self.policy)
        controls = AdaptiveGrid(max_cols=2, min_width=180, row_height=40, spacing=dp(6))
        self.review_button = Action("Review compatible plane", self.review, primary=True)
        self.export_button = Action("Export plane report…", self.export, disabled=True)
        controls.add_widget(self.review_button)
        controls.add_widget(self.export_button)
        self.add_widget(controls)
        self.add_widget(content_label("Residual range limit · optional · mm or in"))
        self.limit = QuantityField(
            text="", optional=True, kind="length", minimum=0, maximum=1000000, hint_text="No comparison limit"
        )
        self.add_widget(self.limit)
        self.status = content_label(
            "Choose a retained feature as the plane anchor, then review. One receipt per feature; no fallback past a raw or incomplete latest receipt."
        )
        self.add_widget(self.status)
        self.plot = InspectionDeviationPlot(self.select, size_hint_y=None, height=dp(150))
        self.add_widget(self.plot)
        pages = AdaptiveGrid(max_cols=2, min_width=140, row_height=34)
        self.previous = Action("Previous fitted receipt", lambda: self.select(self.index - 1), disabled=True)
        self.next = Action("Next fitted receipt", lambda: self.select(self.index + 1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.add_widget(pages)
        self.details = content_label("")
        self.add_widget(self.details)
        self.exclusions = content_label("")
        self.add_widget(self.exclusions)
        exclusion_pages = AdaptiveGrid(max_cols=2, min_width=140, row_height=34)
        self.exclusion_previous = Action("Previous exclusions", lambda: self.turn_exclusions(-1), disabled=True)
        self.exclusion_next = Action("Next exclusions", lambda: self.turn_exclusions(1), disabled=True)
        exclusion_pages.add_widget(self.exclusion_previous)
        exclusion_pages.add_widget(self.exclusion_next)
        self.exclusion_pages = exclusion_pages
        self.add_widget(
            content_label(
                "Least-squares height plane using retained nominal normals for radius projection. Sample residual range is not minimum-zone flatness. Three points leave zero residual degrees of freedom. References and mounting remain declared; no uncertainty, physical conformance or machine offset is inferred."
            )
        )
        self.policy.bind(text=lambda *_: self.invalidate())
        self.limit.bind(text=lambda *_: self.render())

    def invalidate(self):
        self.generation += 1
        self.result = None
        self.index = None
        self.exclusion_page = 0
        self.exclusion_previous.disabled = self.exclusion_next.disabled = True
        if self.exclusion_pages.parent:
            self.remove_widget(self.exclusion_pages)
        self.plot.show([], (None, None), None)
        self.details.text = self.exclusions.text = ""
        self.status.text = "Plane review needs recalculation for this selection and receipt policy."
        self.export_button.disabled = True
        self.previous.disabled = self.next.disabled = True

    def review(self):
        owner = self.owner
        if owner.busy or owner.closed or owner.store.error:
            return
        anchor = owner.choices.get(owner.selector.text)
        if anchor is None:
            self.status.text = "Select a retained feature first."
            return
        from carveracontroller.desktop_surface_inspection import run_inspection_job

        self.invalidate()
        generation = self.generation
        policy = "latest" if self.policy.text.startswith("Latest") else "earliest"
        owner.busy = True
        owner.refresh()
        self.status.text = "Reviewing retained plane receipts…"

        def done(result, error):
            owner.busy = False
            owner.refresh()
            if owner.closed or generation != self.generation or anchor != owner.choices.get(owner.selector.text):
                return
            self.result = result
            self.index = 0 if result and result["samples"] else None
            self.status.text = error or ""
            if result:
                self.render()

        run_inspection_job(owner.workspace, lambda store: plane_review(store.features, anchor, policy), done)

    def select(self, index):
        if self.result and self.result["samples"]:
            self.index = min(len(self.result["samples"]) - 1, max(0, index))
            self.render()

    def render(self):
        if self.result is None:
            return
        result, fit = self.result, self.result["fit"]
        lines = [
            f"{result['part']} · {result['component']} · {result['policy']} retained receipt per feature",
            f"{len(result['samples'])} selected compensated receipts · {len(result['excluded'])} excluded · {result['other_group_features']} features in other nominal/setup groups",
            f"Input snapshot SHA-256 {result['input_sha256']}",
        ]
        if fit:
            lines += [
                f"Tilt {fit['tilt_deg']:.6g}° · anchor normal offset {fit['nominal_normal_offset_mm']:+.6g} mm",
                f"Sample residual range {fit['residual_range_mm']:.6g} mm · RMS {fit['residual_rms_mm']:.6g} mm · {fit['degrees_of_freedom']} residual degrees of freedom",
                "Fitted normal: " + ", ".join(f"{v:.6g}" for v in fit["normal"]),
                "Plot: signed residual per selected feature; select a point for exact receipt details.",
            ]
            if self.limit.text.strip():
                try:
                    limit = self.limit.value()
                    lines.append(
                        f"Residual range {'within' if fit['residual_range_mm'] <= limit else 'outside'} entered limit {limit:g} mm · numerical comparison"
                    )
                except ValueError as error:
                    lines.append(str(error))
            else:
                lines.append("Residual range limit not entered.")
        else:
            lines.append(result["reason"])
        self.status.text = "\n".join(lines)
        plot_rows = [
            (
                row["receipt"],
                {"deviation_mm": row.get("residual_mm"), "state": "untoleranced" if fit else "unevaluated"},
            )
            for row in result["samples"]
        ]
        self.plot.show(plot_rows, (None, None), self.index)
        self.previous.disabled = self.index is None or self.index == 0
        self.next.disabled = self.index is None or self.index == len(result["samples"]) - 1
        self.export_button.disabled = self.owner.busy
        if self.index is not None:
            row = result["samples"][self.index]
            sample = row["receipt"]
            contact = ", ".join(f"{v:.6g}" for v in row["contact_mm"])
            residual = f"{row['residual_mm']:.6g} mm" if "residual_mm" in row else "Unknown"
            self.details.text = (
                f"Selected feature {self.index + 1}/{len(result['samples'])}: {row['feature_name']}\n"
                f"Feature {row['feature_id']} · nominal {row['nominal_sha256']}\n"
                f"Receipt {sample['id']} · source {sample['source_ref']}\n"
                f"Observation time: {sample['observed_at'] or 'Unknown'} · local record time {sample['recorded_at']}\n"
                f"Registration {sample['registration_ref']} · compensation {sample['calibration_ref']}\n"
                f"Projected contact: {contact} mm\nSigned fitted residual: {residual}"
            )

        start = self.exclusion_page * 20
        excluded = result["excluded"][start : start + 20]
        self.exclusions.text = (
            (
                f"Excluded selected receipts {start + 1}–{start + len(excluded)}/{len(result['excluded'])}:\n"
                + "\n".join(
                    f"{row['feature_name']} · {row['receipt_id'] or 'No receipt'} · {row['reason']}" for row in excluded
                )
            )
            if excluded
            else "No selected receipts excluded."
        )
        self.exclusion_previous.disabled = self.exclusion_page == 0
        self.exclusion_next.disabled = start + 20 >= len(result["excluded"])
        if len(result["excluded"]) > 20 and self.exclusion_pages.parent is None:
            self.add_widget(self.exclusion_pages, index=1)
        elif len(result["excluded"]) <= 20 and self.exclusion_pages.parent:
            self.remove_widget(self.exclusion_pages)

    def turn_exclusions(self, delta):
        if self.result:
            maximum = max(0, (len(self.result["excluded"]) - 1) // 20)
            self.exclusion_page = min(maximum, max(0, self.exclusion_page + delta))
            self.render()

    def export(self):
        if self.result is None or self.owner.busy or self.owner.closed:
            return
        from carveracontroller.desktop_surface_inspection import run_inspection_job
        from carveracontroller.machine.inspection_plane import export_plane_report

        # Snapshot binds the chooser and write to the reviewed input, even if selection changes.
        try:
            limit = self.limit.value() if self.limit.text.strip() else None
        except ValueError as error:
            self.details.text = str(error)
            return
        snapshot = json.loads(json.dumps(self.result, allow_nan=False))
        generation = self.generation

        def chosen(path):
            if self.owner.closed or generation != self.generation:
                return
            self.owner.busy = True
            self.owner.refresh()

            def done(receipt, error):
                self.owner.busy = False
                self.owner.refresh()
                if not self.owner.closed and generation == self.generation:
                    self.details.text = error or f"Plane report saved and read back · SHA-256 {receipt['sha256']}"

            run_inspection_job(self.owner.workspace, lambda _store: export_plane_report(snapshot, path, limit), done)

        self.owner.workspace.choose_profile_file(
            chosen, save=True, extension=".cvplane", title="Export retained plane review"
        )
