"""Paste, review and atomically retain a measurement table."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, DesktopScrollView, Field
from carveracontroller.desktop_inspection_receipts import InspectionReceiptPanel
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_planning import PlanningCard
from carveracontroller.machine.inspection_batch import apply_batch, batch_feature, review_batch


class InspectionBatchDialog:
    def __init__(self, owner):
        self.owner = owner
        self.identity = owner.choices.get(owner.selector.text)
        self.closed = False
        self.busy = False
        self.reviewed = None
        self.generation = 0
        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        scroll = DesktopScrollView(do_scroll_x=False)
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        form.bind(minimum_height=form.setter("height"))
        scroll.add_widget(form)
        body.add_widget(scroll)
        feature = owner.store.get(self.identity)
        form.add_widget(
            content_label(
                f"{feature['part']} · {feature['name']}\nPaste a table in the retained nominal component machine frame. Unsuffixed coordinates use mm; explicit units and fractions are accepted."
            )
        )
        self.entry = PlanningCard("Measurement table & coordinate kind")
        form.add_widget(self.entry)
        self.entry.toggle()
        controls = AdaptiveGrid(max_cols=2, min_width=150, row_height=40, spacing=dp(8))
        self.separator = Choice(text="TSV", values=("TSV", "CSV"))
        self.kind = Choice(text=owner.kind.text, values=("Compensated ball center", "Raw trigger"))
        controls.add_widget(self.separator)
        controls.add_widget(self.kind)
        self.entry.content.add_widget(controls)
        self.entry.content.add_widget(
            content_label(
                "Required headers: x, y, z, source_ref\nOptional: kind, registration_ref, calibration_ref, observed_at\nReferences are per row. Blank registration or compensation remains unevaluated. Optional kind uses compensated_ball_center or raw_trigger; otherwise the selected kind applies."
            )
        )
        self.table = Field(
            multiline=True, height=dp(130), hint_text="x\ty\tz\tsource_ref\nPaste measurement rows here…"
        )
        self.entry.content.add_widget(self.table)
        self.note = content_label("Nothing retained. Review the table before saving.")
        form.add_widget(self.note)
        self.preview = InspectionReceiptPanel()
        form.add_widget(self.preview)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=40, spacing=dp(8))
        self.review_button = Action("Review table", self.prepare, primary=True)
        self.apply_button = Action("Retain reviewed batch", self.apply, disabled=True)
        self.close_button = Action("Close", self.dismiss)
        for button in (self.review_button, self.apply_button, self.close_button):
            actions.add_widget(button)
        body.add_widget(actions)
        self.popup = Popup(title="Batch measurement entry", content=body, size_hint=(0.8, 0.88))
        self.popup.bind(on_dismiss=self.invalidate_closed)
        self.table.bind(text=self.changed)
        self.separator.bind(text=self.changed)
        self.kind.bind(text=self.changed)
        self.popup.open()

    def changed(self, *_):
        self.generation += 1
        self.reviewed = None
        self.apply_button.disabled = True
        self.preview.show(None)
        self.note.text = "Table changed · review again. Nothing retained."

    def invalidate_closed(self, *_):
        self.closed = True
        self.generation += 1
        self.reviewed = None

    def dismiss(self):
        self.popup.dismiss()

    def available(self):
        return not self.closed and not self.owner.closed and not self.busy

    def prepare(self):
        if not self.available():
            return
        from carveracontroller.desktop_surface_inspection import run_inspection_job

        self.busy = True
        self.reviewed = None
        self.apply_button.disabled = True
        self.review_button.disabled = True
        self.preview.show(None)
        self.note.text = "Validating table and comparing declared coordinates…"
        generation = self.generation
        content, separator = self.table.text, self.separator.text
        kind = "raw_trigger" if self.kind.text == "Raw trigger" else "compensated_ball_center"

        def work(store):
            feature = store.get(self.identity)
            reviewed = review_batch(feature, content, separator=separator, default_kind=kind)
            return reviewed, batch_feature(feature, reviewed)

        def prepared(result, error):
            self.busy = False
            self.review_button.disabled = False
            if self.closed or self.owner.closed or generation != self.generation:
                return
            if error:
                self.note.text = error
                return
            self.reviewed, feature = result
            if self.entry.expanded:
                self.entry.toggle()
            self.preview.show(feature, draft=True)
            if not self.preview.expanded:
                self.preview.toggle()
            self.note.text = f"{self.reviewed.count} proposed receipts · nothing retained. Review all entries using filters and pages. Input SHA-256 {self.reviewed.input_sha256}\nRecord time will be assigned on retention. Entered references and accuracy remain unverified."
            self.apply_button.text = f"Retain {self.reviewed.count} reviewed receipts"
            self.apply_button.disabled = False

        run_inspection_job(self.owner.workspace, work, prepared)

    def apply(self):
        if not self.available() or self.reviewed is None:
            return
        from carveracontroller.desktop_surface_inspection import run_inspection_job

        reviewed = self.reviewed
        self.busy = True
        self.apply_button.disabled = True
        self.review_button.disabled = True
        self.table.disabled = self.separator.disabled = self.kind.disabled = True
        self.note.text = "Retaining the reviewed batch atomically…"

        def saved(result, error):
            self.busy = False
            self.reviewed = None
            self.review_button.disabled = False
            self.table.disabled = self.separator.disabled = self.kind.disabled = False
            if not self.owner.closed:
                self.owner.note.text = (
                    error or f"Retained {len(result)} reviewed receipts · local operator-entered records"
                )
                if not error and hasattr(self.owner, "plane"):
                    self.owner.plane.invalidate()
                self.owner.refresh()
            if self.closed or self.owner.closed:
                return
            self.note.text = (
                error
                or f"Retained {len(result)} receipts. Each has its own identity; record time is the retention time."
            )
            if not error:
                self.preview.show(
                    {
                        **self.owner.store.get(self.identity),
                        "samples": [
                            sample
                            for sample in self.owner.store.get(self.identity)["samples"]
                            if sample["id"] in set(result)
                        ],
                    }
                )

        run_inspection_job(self.owner.workspace, lambda store: apply_batch(store, reviewed), saved)
