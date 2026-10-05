"""Workbench inspection records; entered receipts remain explicitly declared."""

import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Field, QuantityField, label
from carveracontroller.desktop_inspection_receipts import InspectionReceiptPanel
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore, sample_result, summary


def inspection_store(workspace):
    if not hasattr(workspace, "surface_inspection_store"):
        workspace.surface_inspection_store = SurfaceInspectionStore()
    return workspace.surface_inspection_store


def run_inspection_job(workspace, work, done):
    """Serialize local file work away from the event loop, including first load."""
    if getattr(workspace, "inspection_busy", False):
        done(None, "Another inspection save/load is running")
        return
    workspace.inspection_busy = True
    cached = getattr(workspace, "surface_inspection_store", None)

    def worker():
        store, result, error = cached, None, None
        try:
            store = store or SurfaceInspectionStore()
            result = work(store)
        except (ValueError, OSError, TypeError, KeyError, StopIteration, RecursionError, OverflowError) as exc:
            error = str(exc)

        def deliver(_dt):
            workspace.inspection_busy = False
            if store is not None:
                workspace.surface_inspection_store = store
            done(result, error)

        Clock.schedule_once(deliver, 0)

    threading.Thread(target=worker, name="surface-inspection-storage", daemon=True).start()


def open_surface_inspections(workspace, identity=None):
    if not hasattr(workspace, "surface_inspection_store"):
        status = content_label("Loading retained inspection records…")
        loading = Popup(title="Surface inspection records", content=status, size_hint=(0.6, 0.3))
        closed = {"value": False}
        loading.bind(on_dismiss=lambda *_: closed.update(value=True))
        loading.open()

        def loaded(_result, error):
            if closed["value"]:
                return
            if error:
                status.text = error
                return
            loading.dismiss()
            open_surface_inspections(workspace, identity)

        run_inspection_job(workspace, lambda store: None, loaded)
        return None
    review = SurfaceInspectionReview(workspace, identity)
    workspace.surface_inspection_review = review
    review.popup.open()
    return review


class SurfaceInspectionReview:
    def __init__(self, workspace, identity=None):
        self.workspace = workspace
        self.busy = False
        self.closed = False
        self.store = inspection_store(workspace)
        self.choices = {f"{f['part']} · {f['name']} · {f['id'][:8]}": f["id"] for f in self.store.features}
        selected = next(
            (k for k, v in self.choices.items() if v == identity), next(iter(self.choices), "No inspection features")
        )
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        self.selector = Choice(text=selected, values=tuple(self.choices) or (selected,))
        self.selector.size_hint_y = None
        self.selector.height = dp(42)
        body.add_widget(self.selector)
        exports = AdaptiveGrid(max_cols=2, min_width=170, row_height=38, spacing=dp(8))
        self.export_format = Choice(text="Portable JSON", values=("Portable JSON", "CSV", "HTML report"))
        self.export_scope = Choice(text="Selected feature", values=("Selected feature", "All features"))
        exports.add_widget(self.export_format)
        exports.add_widget(self.export_scope)
        body.add_widget(exports)
        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        scroll.add_widget(form)
        body.add_widget(scroll)
        self.report = content_label("")
        form.add_widget(self.report)
        self.receipts = InspectionReceiptPanel()
        form.add_widget(self.receipts)
        form.add_widget(label("Record a measurement receipt", 15, height=30, bold=True))
        self.kind = Choice(text="Compensated ball center", values=("Compensated ball center", "Raw trigger"))
        self.kind.size_hint_y = None
        self.kind.height = dp(40)
        form.add_widget(self.kind)
        self.positions = []
        grid = AdaptiveGrid(max_cols=3, min_width=160, row_height=76, spacing=dp(8))
        for axis in "XYZ":
            cell = BoxLayout(orientation="vertical")
            cell.add_widget(label(f"{axis} · nominal frame", 12, height=24))
            field = QuantityField(text="", kind="length", minimum=-1000000, maximum=1000000)
            self.positions.append(field)
            cell.add_widget(field)
            grid.add_widget(cell)
        form.add_widget(grid)
        self.references = {}
        for key, title in (
            ("source_ref", "Source receipt / record identifier (required)"),
            ("registration_ref", "Coordinate registration reference"),
            ("calibration_ref", "Probe compensation / calibration reference"),
            ("observed_at", "Source observation time (leave blank if unknown)"),
        ):
            form.add_widget(label(title, 12, height=24))
            field = Field(hint_text=title)
            field.size_hint_y = None
            field.height = dp(40)
            self.references[key] = field
            form.add_widget(field)
        form.add_widget(
            content_label(
                "Entered coordinates and references are declared evidence. Raw triggers or missing registration/compensation references are retained but remain unevaluated. Within-limit comparisons do not establish measurement accuracy or certification."
            )
        )
        self.note = content_label("")
        form.add_widget(self.note)
        buttons = AdaptiveGrid(max_cols=3, min_width=140, row_height=38, spacing=dp(8))
        self.record_button = Action("Retain receipt", self.record, primary=True)
        buttons.add_widget(self.record_button)
        self.batch_button = Action("Paste measurement table…", self.open_batch)
        buttons.add_widget(self.batch_button)
        self.export_button = Action("Export…", self.export)
        buttons.add_widget(self.export_button)
        buttons.add_widget(Action("Import bundle…", self.import_bundle))
        buttons.add_widget(Action("Reload records", self.reload))
        buttons.add_widget(Action("Close", self.popup_close))
        body.add_widget(buttons)
        self.popup = Popup(title="Surface inspection records", content=body, size_hint=(0.78, 0.86))
        self.popup.bind(on_dismiss=self.mark_closed)
        self.selector.bind(text=self.selection_changed)
        self.refresh()

    def selection_changed(self, *_):
        for field in (*self.positions, *self.references.values()):
            field.text = ""
        self.note.text = ""
        self.refresh()

    def refresh(self):
        self.record_button.disabled = self.busy or self.selector.text not in self.choices or bool(self.store.error)
        self.batch_button.disabled = self.record_button.disabled
        self.export_button.disabled = self.busy or bool(self.store.error) or not self.choices
        if self.store.error:
            self.receipts.show(None)
            self.report.text = "Inspection file needs repair: " + self.store.error
            return
        if self.selector.text not in self.choices:
            self.receipts.show(None)
            self.report.text = "Pick a surface in Scene, choose Measure surface, then save an inspection feature."
            return
        f = self.store.get(self.choices[self.selector.text])
        s = summary(f)
        lower, upper = f["limits_mm"]
        lines = [
            f"{f['part']} · {f['name']}",
            f"Retained nominal {f['nominal_sha256'][:16]} · fixed setup declaration",
            "Normal limits: " + ("not specified" if lower is None else f"{lower:+.4f} to {upper:+.4f} mm"),
            f"{s['recorded']} receipts · {s['evaluated']} evaluated · {s['unevaluated']} unevaluated · {s['outside']} outside declared limits",
        ]
        point = f["plan"]["reference"]["component_point_mm"]
        lines.insert(2, "Nominal surface: " + ", ".join(f"{v:.4f}" for v in point) + " mm · component machine frame")
        if s["mean_mm"] is not None:
            lines.append(f"Mean normal deviation {s['mean_mm']:+.5f} mm")
            lines.append(f"Repeat range {s['range_mm']:.5f} mm")
        if s["sample_stdev_mm"] is not None:
            lines.append(f"Sample standard deviation {s['sample_stdev_mm']:.5f} mm")
        if f["samples"]:
            latest = sample_result(f, f["samples"][-1])
            lines.append("Latest receipt comparison: " + latest["state"].replace("_", " "))
        self.receipts.show(f)
        self.report.text = "\n".join(lines)

    def open_batch(self):
        if self.batch_button.disabled or self.closed:
            return
        from carveracontroller.desktop_inspection_batch import InspectionBatchDialog

        if getattr(self, "batch_dialog", None) is not None and not self.batch_dialog.closed:
            return
        self.batch_dialog = InspectionBatchDialog(self)

    def record(self):
        if self.busy:
            return
        try:
            feature_id = self.choices[self.selector.text]
            position = tuple(p.value() for p in self.positions)
            kind = "raw_trigger" if self.kind.text == "Raw trigger" else "compensated_ball_center"
            references = {k: field.text for k, field in self.references.items()}
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.note.text = str(exc)
            return
        self.busy = True
        self.note.text = "Saving receipt…"
        self.refresh()

        def saved(identity, error):
            self.busy = False
            self.note.text = error or f"Retained receipt {identity} · local record only"
            self.refresh()

        run_inspection_job(
            self.workspace, lambda store: store.record(feature_id, position, kind=kind, **references), saved
        )

    def popup_close(self):
        self.popup.dismiss()

    def mark_closed(self, *_):
        self.closed = True
        dialog = getattr(self, "batch_dialog", None)
        if dialog is not None and not dialog.closed:
            dialog.dismiss()

    def export(self):
        if self.busy or self.store.error:
            return
        from carveracontroller.machine.surface_inspection_exchange import export_file

        format_name, scope = self.export_format.text, self.export_scope.text
        selected = self.choices.get(self.selector.text)
        if scope == "Selected feature" and selected is None:
            return
        extension = {"Portable JSON": ".cvinspect", "CSV": ".csv", "HTML report": ".html"}[format_name]

        def save(path):
            self.busy = True
            self.note.text = "Exporting inspection records…"
            self.refresh()

            def work(store):
                features = [store.get(selected)] if scope == "Selected feature" else store.features
                return export_file(features, path, format_name)

            def saved(receipt, error):
                self.busy = False
                if error:
                    self.note.text = error
                else:
                    self.workspace.last_inspection_export = receipt
                    self.note.text = f"Saved and read back {receipt['features']} features / {receipt['receipts']} receipts · SHA-256 {receipt['sha256']}"
                self.refresh()

            run_inspection_job(self.workspace, work, saved)

        self.workspace.choose_profile_file(
            save, save=True, extension=extension, title=f"Export inspection {format_name}"
        )

    def import_bundle(self):
        if self.busy:
            return
        from carveracontroller.machine.surface_inspection_exchange import import_file, preview_import

        def selected(path):
            self.busy = True
            self.note.text = "Reviewing inspection bundle…"
            self.refresh()

            def reviewed(receipt, error):
                self.busy = False
                self.refresh()
                if self.closed:
                    return
                if error:
                    self.note.text = error
                    return
                body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
                body.add_widget(
                    content_label(
                        f"Add {receipt['features_added']} features and {receipt['receipts_added']} receipts. Existing identical identities are retained; conflicts are rejected.\nSource SHA-256 {receipt['source_sha256']}\nThis restores inspection records, not machine setup or offsets."
                    )
                )
                actions = AdaptiveGrid(max_cols=2, min_width=140, row_height=38, spacing=dp(8))
                popup = Popup(title="Review inspection import", content=body, size_hint=(0.65, 0.4))
                pending = {"value": True}
                popup.bind(on_dismiss=lambda *_: pending.update(value=False))

                def apply():
                    if self.closed or self.busy or not pending["value"]:
                        return
                    popup.dismiss()
                    self.busy = True
                    self.refresh()

                    def imported(result, error):
                        self.busy = False
                        if error:
                            self.note.text = error
                            self.refresh()
                            return
                        self.workspace.last_inspection_import = result
                        self.note.text = f"Imported {result['features_added']} features / {result['receipts_added']} receipts · SHA-256 {result['source_sha256']}"
                        self.choices = {
                            f"{f['part']} · {f['name']} · {f['id'][:8]}": f["id"] for f in self.store.features
                        }
                        self.selector.values = tuple(self.choices) or ("No inspection features",)
                        if self.selector.text not in self.choices:
                            self.selector.text = self.selector.values[0]
                        self.refresh()

                    run_inspection_job(
                        self.workspace, lambda store: import_file(store, path, receipt["source_sha256"]), imported
                    )

                actions.add_widget(Action("Import reviewed records", apply, primary=True))
                actions.add_widget(Action("Cancel", popup.dismiss))
                body.add_widget(actions)
                self.import_review_popup = popup
                self.apply_import = apply
                popup.open()

            run_inspection_job(self.workspace, lambda store: preview_import(store, path), reviewed)

        self.workspace.choose_profile_file(selected, extension=".cvinspect", title="Import portable inspection bundle")

    def reload(self):
        if self.busy:
            return
        self.busy = True
        self.refresh()
        self.note.text = "Reloading records…"
        selected = self.choices.get(self.selector.text)

        def loaded(store, error):
            self.busy = False
            if error:
                self.note.text = error
                self.refresh()
                return
            self.store = store
            self.workspace.surface_inspection_store = store
            self.choices = {f"{f['part']} · {f['name']} · {f['id'][:8]}": f["id"] for f in store.features}
            self.selector.values = tuple(self.choices) or ("No inspection features",)
            self.selector.text = next((k for k, v in self.choices.items() if v == selected), self.selector.values[0])
            self.selection_changed()
            self.note.text = "Reloaded retained records · entry fields cleared"

        run_inspection_job(self.workspace, lambda store: SurfaceInspectionStore(store.path), loaded)
