"""Named workspace presentation controls, isolated from machine configuration."""

from kivy.metrics import dp

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Choice, Field, Surface, label
from carveracontroller.desktop_cutaway_state import capture_cutaways, prepare_cutaways, restore_cutaways
from carveracontroller.desktop_view_state import capture_view, restore_view
from carveracontroller.machine.workspace_layouts import WorkspaceLayouts, validate_layout


class LayoutPanel(Surface):
    def __init__(self, workspace, store=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.store = store or WorkspaceLayouts()
        self.add_widget(label("Workspace layouts", 14, height=28, bold=True))
        self.choice = Choice(text="Select saved layout", values=tuple(r["name"] for r in self.store.records))
        self.add_widget(self.choice)
        self.name = Field(text="", hint_text="Layout name")
        self.add_widget(self.name)
        self.add_widget(label("Media column width · 25–75%", 11, MUTED, 24))
        self.share = Field(text="50", hint_text="Media column · 25–75%")
        self.add_widget(self.share)
        actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=34, spacing=dp(6))
        for title, callback in (
            ("Apply pane sizing", self.resize),
            ("Save current layout", self.save),
            ("Restore layout", self.restore),
            ("Delete layout", self.delete),
            ("Import layouts", lambda: self.exchange(False)),
            ("Export layouts", lambda: self.exchange(True)),
        ):
            actions.add_widget(Action(title, callback))
        self.add_widget(actions)
        self.note = label(
            self.store.load_error
            or "Save framing and setup-bound cutaways · no tools, offsets or machine commands change.",
            11,
            MUTED,
            58,
        )
        self.add_widget(self.note)

    def resize(self):
        try:
            share = float(self.share.text) / 100
            ws = self.workspace
            record = self.capture("Pane sizing")
            record["media_share"] = share
            validate_layout(record)
            self._set_share(share)
            self.note.text = f"Media column {share:.0%} · image aspect ratios retained"
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)

    def _set_share(self, share):
        from carveracontroller.desktop_pane_divider import set_media_share

        set_media_share(self.workspace, share)

    def capture(self, name):
        ws = self.workspace
        section = ws.active_section
        task, scroll = ws.navigation.task_context(section)
        return validate_layout(
            {
                "name": name,
                "media_share": getattr(ws, "workspace_media_share", 0.5),
                "camera_visible": ws.job_camera_splitter.parent is ws.preview_row,
                "section": section,
                "task": task,
                "scroll": min(1, max(0, float(scroll.scroll_y))) if scroll is not None else None,
                "view": capture_view(ws.machine.gcode_viewer),
                "camera_view": ws.camera_stage_view.capture_framing(),
                "cutaway_state": capture_cutaways(ws),
                "explosion_mm": ws.machine.gcode_viewer.explosion_mm
                if ws.machine.gcode_viewer.pose_mode == "Preview"
                else 0,
            }
        )

    def save(self):
        try:
            self.store.save(self.capture(self.name.text))
            self.choice.values = tuple(r["name"] for r in self.store.records)
            self.choice.text = self.name.text.strip()
            self.note.text = "Layout saved and read back · draft edits and machine state retained"
        except (ValueError, TypeError, OSError) as exc:
            self.note.text = str(exc)

    def restore(self):
        try:
            ws = self.workspace
            record = next((r for r in self.store.records if r["name"] == self.choice.text), None)
            if record is None:
                raise ValueError("Select a saved layout")
            record = validate_layout(record)
            point = {"kind": "section", "value": record["section"], "task": record["task"], "scroll": record["scroll"]}
            ws.navigation._validate_task(point)
            cutaways = prepare_cutaways(ws, record["cutaway_state"])
            if record["explosion_mm"] and ws.machine.gcode_viewer.pose_mode != "Preview":
                raise ValueError("Choose Preview before restoring an exploded inspection layout")
            self._set_share(record["media_share"])
            if (ws.job_camera_splitter.parent is ws.preview_row) != record["camera_visible"]:
                ws._toggle_job_camera()
            restore_view(ws.machine.gcode_viewer, record["view"])
            ws.camera_stage_view.restore_framing(record["camera_view"])
            restore_cutaways(ws, cutaways)
            ws.machine.gcode_viewer.set_explosion(record["explosion_mm"])
            ws.object_inspector.refresh_trigger()
            ws.model_caption.text = f"Machine & toolpath · {ws.machine.gcode_viewer.pose_mode}" + (
                " · exploded inspection" if record["explosion_mm"] else ""
            )
            ws.select(record["section"])
            if record["task"] is not None:
                ws.navigation._restore_task(point)
            self.name.text = record["name"]
            self.share.text = f"{record['media_share'] * 100:g}"
            self.note.text = "Layout restored · machine/camera framing and setup-bound section planes"
        except (ValueError, TypeError, AttributeError) as exc:
            self.note.text = str(exc)

    def exchange(self, exporting):
        def selected(path):
            try:
                if exporting:
                    digest = self.store.export_file(path)
                    self.note.text = f"Layouts exported and read back · SHA-256 {digest[:12]}"
                else:
                    count = self.store.import_file(path)
                    self.choice.values = tuple(r["name"] for r in self.store.records)
                    self.note.text = f"Imported {count} layouts · current presentation retained"
            except (ValueError, TypeError, OSError) as exc:
                self.note.text = str(exc)

        if exporting:
            self.workspace.choose_profile_file(
                selected, save=True, extension=".cvlayout", title="Export workspace layouts"
            )
        else:
            self.workspace.choose_asset_file(selected, suffixes=(".cvlayout", ".json"))

    def delete(self):
        try:
            self.store.delete(self.choice.text)
            self.choice.values = tuple(r["name"] for r in self.store.records)
            self.choice.text = "Select saved layout"
            self.note.text = "Saved layout deleted · current presentation retained"
        except (ValueError, OSError) as exc:
            self.note.text = str(exc)


def open_layouts(workspace):
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    panel = LayoutPanel(workspace, store=workspace.layout_panel.store)
    content = ScrollView(do_scroll_x=False)
    content.add_widget(panel)
    popup = Popup(title="Workspace layouts", content=content, size_hint=(0.82, 0.85))
    popup.bind(
        on_dismiss=lambda *_: setattr(
            workspace.layout_panel.choice, "values", tuple(r["name"] for r in panel.store.records)
        )
    )
    popup.open()
    return popup
