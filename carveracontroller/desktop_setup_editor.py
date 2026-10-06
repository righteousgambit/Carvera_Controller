"""Reviewed, local-only stock and workholding editing transactions."""

import copy

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    AMBER,
    DANGER,
    MUTED,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    QuantityField,
    Surface,
    label,
)
from carveracontroller.desktop_scene import SceneSetupStore, capture_scene_setup
from carveracontroller.desktop_stock_drawing import StockDrawing
from carveracontroller.desktop_view_state import capture_view, restore_view
from carveracontroller.desktop_workholding_drawing import WorkholdingDrawing


class SetupEditor:
    def __init__(self, workspace, kind):
        self.workspace, self.kind = workspace, kind
        self.viewer = workspace.machine.gcode_viewer
        from carveracontroller.machine.component_loads import ComponentLoads

        if not hasattr(workspace, "setup_editor_loads"):
            workspace.setup_editor_loads = ComponentLoads(
                lambda callback: Clock.schedule_once(lambda _dt: callback(), 0)
            )
        self.loads = workspace.setup_editor_loads
        self.lane = "fixture" if kind == "stock" else "workholding"
        self.preparing = False
        self.last_apply_result = None
        profile = workspace.selected_machine_profile
        self.key = (profile.get("id") if profile else None, kind)
        if not hasattr(workspace, "setup_drafts"):
            workspace.setup_drafts = {}
        draft = workspace.setup_drafts.get(self.key)
        self.model_identity = draft["model_identity"] if draft else self._model_identity()
        self.read_error = ""
        try:
            self.saved_scene = copy.deepcopy(draft["saved_scene"] if draft else self._read_saved_scene())
        except (ValueError, OSError) as exc:
            self.saved_scene = None
            self.read_error = str(exc)
        self.baseline = copy.deepcopy(draft["baseline"] if draft else capture_scene_setup(workspace))
        self.fields = {}
        self.titles = {}
        self._building = True
        self.selected_dimension = ("stock_size_mm" if kind == "stock" else "workholding_offset_mm", 0)
        self.drawing = (
            StockDrawing()
            if kind == "stock"
            else WorkholdingDrawing(
                self.viewer.machine_component_profiles.get("workholding", self.viewer.machine_profile)
            )
        )
        self.body = Surface(orientation="vertical", padding=dp(14), spacing=dp(10))
        self.intro = label(
            "Local preview setup · editing sends no machine commands.\nReview the changes before applying; confirm actual mounting and stock separately.",
            12,
            MUTED,
            52,
        )
        self.intro.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0], None)))
        self.intro.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(30), size[1])))
        self.body.add_widget(self.intro)
        if self.drawing:
            self.drawing_card = Surface(
                orientation="vertical", padding=dp(6), spacing=dp(4), size_hint_y=None, height=dp(210)
            )
            self.drawing_status = label("", 11, MUTED, 44)
            self.drawing_status.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0], None)))
            self.drawing_status.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(44), size[1])))
            self.drawing_status.bind(height=lambda *_: self._fit_drawing_card())
            self.drawing_card.add_widget(self.drawing)
            self.drawing_card.add_widget(self.drawing_status)
            self.body.add_widget(self.drawing_card)
        self.form = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.form.bind(minimum_height=self.form.setter("height"))
        scroll = DesktopScrollView(do_scroll_x=False)
        self.scroll = scroll
        scroll.add_widget(self.form)
        self.body.add_widget(scroll)
        if kind == "stock":
            groups = (
                ("Stock dimensions", "stock_size_mm", self.baseline["stock_size_mm"] or (127, 69.4182, 50.8762)),
                (
                    "Stock corner before rotation · program coordinates",
                    "stock_origin_mm",
                    self.baseline["stock_origin_mm"],
                ),
                ("Program origin · machine coordinates", "work_offset_mm", self.baseline["work_offset_mm"]),
            )
        else:
            groups = (
                (
                    "Vise placement · plate-centered CAD",
                    "workholding_offset_mm",
                    self.baseline["workholding_offset_mm"],
                ),
            )
        for title, group, values in groups:
            card = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None)
            card.add_widget(label(title, 13, height=24))
            grid = AdaptiveGrid(max_cols=3, min_width=170, row_height=82, spacing=dp(8))
            card.add_widget(grid)
            grid.bind(height=lambda _grid, height, card=card: setattr(card, "height", height + dp(50)))
            card.height = grid.height + dp(50)
            self.form.add_widget(card)
            for index, value in enumerate(values):
                self._field(
                    grid,
                    (group, index),
                    f"{title} · {'XYZ'[index]}",
                    value,
                    minimum=0 if group == "stock_size_mm" else -1000,
                )
        if kind == "stock":
            grid = AdaptiveGrid(max_cols=1, min_width=170, row_height=82, spacing=dp(8))
            self.form.add_widget(grid)
            self._field(
                grid,
                ("stock_rotation_deg", None),
                "Stock rotation about center Z",
                self.baseline["stock_rotation_deg"],
                angle=True,
            )
        if kind == "workholding":
            grid = AdaptiveGrid(max_cols=2, min_width=170, row_height=82, spacing=dp(8))
            self.form.add_widget(grid)
            self._field(
                grid,
                ("workholding_rotation_deg", None),
                "Rotation about Z",
                self.baseline["workholding_rotation_deg"],
                angle=True,
            )
            self._field(grid, ("jaw_offset_mm", None), "Movable jaw shift · CAD Y", self.baseline["jaw_offset_mm"])
            self.form.add_widget(
                label("Jaw shift follows CAD Y before rotation; it is not a measured clamping gap.", 11, AMBER, 48)
            )
        self.initial = self.raw()
        if draft:
            for key, value in draft["fields"].items():
                self.fields[key].text = value
        self.summary = label("", 12, MUTED, 56)
        self.summary.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0], None)))
        self.summary.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(24), size[1])))
        self.body.add_widget(self.summary)
        self.note = label("", 12, AMBER, 52)
        self.note.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0], None)))
        self.note.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(24), size[1])))
        self.body.add_widget(self.note)
        row = AdaptiveGrid(max_cols=4, min_width=120, row_height=36, spacing=dp(8))
        self.apply_button = Action("Apply to preview", self.apply, primary=True)
        for button in (
            self.apply_button,
            Action("Reload current setup", self.reload),
            Action("Keep draft & close", self.keep),
            Action("Cancel edits", self.cancel),
        ):
            row.add_widget(button)
        self.body.add_widget(row)
        self.popup = Popup(
            title="Stock & program origin" if kind == "stock" else "Mod Vise placement",
            content=self.body,
            size_hint=(0.84, 0.88),
            auto_dismiss=False,
        )
        self.popup.bind(on_dismiss=lambda *_: self.stash())
        self.popup.bind(on_dismiss=lambda *_: self.cancel_preparation())
        if self.drawing:
            self.popup.bind(on_dismiss=lambda *_: self.drawing.dispose())
            self.body.bind(height=lambda *_: self._position_drawing())
        self._building = False
        self.drawing.bind(on_dimension_selected=lambda _drawing, key: self._select_drawn_dimension(key))
        self.refresh()

    def _position_drawing(self):
        # Keep the illustration pinned on large desktops. Small windows need
        # the form's full remaining height; make the illustration scroll with it.
        parent = self.form if self.body.height < dp(650) else self.body
        if self.drawing_card.parent is not parent:
            self.drawing_card.parent.remove_widget(self.drawing_card)
            if parent is self.form:
                parent.add_widget(self.drawing_card, index=len(parent.children))
            else:
                parent.add_widget(self.drawing_card, index=parent.children.index(self.scroll) + 1)
        if self.summary.parent is not parent:
            self.summary.parent.remove_widget(self.summary)
            parent.add_widget(self.summary, index=0 if parent is self.form else parent.children.index(self.note) + 1)

    def _field(self, parent, key, title, value, minimum=-1000, angle=False):
        cell = BoxLayout(orientation="vertical", spacing=dp(3))
        caption = f"{'XYZ'[key[1]]} · mm" if key[1] is not None else title
        cell.add_widget(label(caption, 11, MUTED, 22))
        field = QuantityField(text=f"{value:.12g}", kind="angle" if angle else "length", minimum=minimum, maximum=1000)
        self.fields[key], self.titles[key] = field, title
        field.bind(text=lambda *_: self.refresh())
        if self.drawing:
            field.bind(focus=lambda _field, focused, key=key: self._focus_dimension(key, focused))
        cell.add_widget(field)
        parent.add_widget(cell)

    def _focus_dimension(self, key, focused):
        if focused:
            self.selected_dimension = key
            self.refresh()

    def _select_drawn_dimension(self, key):
        if self.drawing.disposed or key not in self.fields:
            return
        for field_key, field in self.fields.items():
            field.focus = field_key == key
        self.selected_dimension = key
        self.scroll.scroll_to(self.fields[key], animate=False)
        self.refresh()

    def _selected_change(self, candidate):
        group, axis = self.selected_dimension
        old, new = self.baseline[group], candidate[group]
        if axis is not None:
            old = old[axis] if old is not None else None
            new = new[axis] if new is not None else None
        if old == new:
            return ""
        unit = "°" if group.endswith("_deg") else " mm"
        if old is None:
            return f"Previous: not configured · Draft: {new:g}{unit}"
        return f"Previous: {old:g}{unit} · Draft: {new:g}{unit} · Change: {new - old:+g}{unit}"

    def _refresh_drawing(self, candidate=None, error=None):
        if not self.drawing:
            return
        if error:
            self.drawing.setup = None
            self.drawing.trigger()
            self.drawing.opacity = 0
            self.drawing_card.height = dp(62)
            self.drawing_status.color = DANGER
            self.drawing_status.text = f"Draft drawing unavailable: {error}"
            self._fit_drawing_card()
            return
        self.drawing.opacity = (
            int(candidate["stock_size_mm"] is not None) if self.kind == "stock" else int(bool(self.drawing.envelopes))
        )
        self.drawing_card.height = dp(210)
        self.drawing_status.color = MUTED
        if self.kind == "stock":
            self.drawing.update_setup(candidate, self.selected_dimension, self.baseline)
        else:
            self.drawing.update_setup(candidate, self.selected_dimension)
        group, axis = self.selected_dimension
        values = candidate[group]
        value = (values[axis] if axis is not None else values) if values is not None else None
        state = "Draft" if self.raw() != self.initial else "Current setup"
        change = self._selected_change(candidate)
        comparison = f"\n{change}" if change else ""
        if self.kind == "workholding":
            if group == "workholding_offset_mm":
                detail = f"Vise {'XYZ'[axis]} translation: {value:g} mm in plate-centered CAD"
            elif group == "workholding_rotation_deg":
                detail = f"Rotation about source CAD pivot Z: {value:g}°"
            else:
                detail = f"Movable component CAD Y shift: {value:g} mm before rotation"
            geometry_note = (
                "Click a placement line, rotation arc or jaw marker to edit. CAD component envelopes · cross: source pivot; circle: placed pivot · not a measured clamping gap."
                if self.drawing.envelopes
                else "No workholding CAD loaded. Select a vise model in Scene to illustrate this placement."
            )
            if group == "jaw_offset_mm" and self.drawing.envelopes:
                geometry_note += " Dashed envelope: jaw at zero shift."
            self.drawing_status.text = f"{state} · {detail}{comparison}\n{geometry_note}"
            self._fit_drawing_card()
            return
        if group == "stock_size_mm":
            detail = f"Stock {'XYZ'[axis]}: {value:g} mm" if value is not None else "Stock dimensions not configured"
        elif group == "stock_rotation_deg":
            detail = f"Stock Z rotation: {value:g}° about the stock center in program coordinates"
        elif group == "stock_origin_mm":
            detail = f"Unrotated corner {'XYZ'[axis]}: {value:g} mm in program coordinates"
        else:
            detail = f"Program zero {'XYZ'[axis]}: {value:g} mm in declared machine coordinates"
        geometry_note = (
            "Click a dimension line to edit its value. Circle marks the unrotated stock corner · stock-frame XY/XZ projections; mounting is unmeasured."
            if candidate["stock_size_mm"] is not None
            else "No stock configured. Edit a stock dimension to create a local stock draft."
        )
        if group == "stock_origin_mm" and candidate["stock_size_mm"] is not None:
            geometry_note = "Cross: program zero · circle: draft unrotated corner · dashed: previous corner. Click an axis ray to edit. Stock rotation and measured mounting are not shown in these program-frame projections."
        if group == "work_offset_mm" and candidate["stock_size_mm"] is not None:
            geometry_note = "Cross: machine zero · circle: draft program zero · solid: draft stock · dashed: previous stock/zero. XY includes stock rotation; XZ is its projected envelope. Click an axis ray to edit. Declared preview transform only; controller WCS and measured mounting are not verified."
        if group == "stock_rotation_deg" and candidate["stock_size_mm"] is not None:
            geometry_note = "Solid: draft XY rotation around stock center · dashed: zero rotation. Click the angle ray to edit. XZ remains an unrotated stock-frame projection; mounting is unmeasured."
        self.drawing_status.text = f"{state} · {detail}{comparison}\n{geometry_note}"
        self._fit_drawing_card()

    def _fit_drawing_card(self):
        if self.drawing:
            self.drawing_card.height = self.drawing_status.height + dp(16) + (dp(150) if self.drawing.opacity else 0)

    def raw(self):
        return {key: field.text for key, field in self.fields.items()}

    def stash(self):
        if self.raw() != self.initial:
            self.workspace.setup_drafts[self.key] = {
                "baseline": copy.deepcopy(self.baseline),
                "fields": self.raw(),
                "model_identity": self.model_identity,
                "saved_scene": copy.deepcopy(self.saved_scene),
            }
        else:
            self.workspace.setup_drafts.pop(self.key, None)

    def candidate(self):
        candidate = copy.deepcopy(self.baseline)
        for (group, index), field in self.fields.items():
            # Display formatting must not silently round an untouched setup.
            if field.text == self.initial[group, index]:
                continue
            try:
                value = field.value()
            except ValueError as exc:
                raise ValueError(f"{self.titles[group, index]}: {exc}") from exc
            if index is None:
                candidate[group] = value
            else:
                if candidate[group] is None:
                    candidate[group] = [127, 69.4182, 50.8762]
                candidate[group][index] = value
        if self.kind == "stock" and any(
            candidate[group] != self.baseline[group]
            for group in ("stock_size_mm", "stock_origin_mm", "stock_rotation_deg")
        ):
            candidate["choices"]["stock"] = "Current stock"
        return SceneSetupStore.validate(candidate)

    def current_matches(self):
        profile = self.workspace.selected_machine_profile
        return (
            (profile.get("id") if profile else None) == self.key[0]
            and capture_scene_setup(self.workspace) == self.baseline
            and self._model_identity() == self.model_identity
        )

    def _model_identity(self):
        return (
            id(self.viewer.machine_profile),
            tuple(sorted((key, id(value)) for key, value in self.viewer.machine_component_profiles.items())),
        )

    def _read_saved_scene(self):
        return self.workspace.scene_setup_store.read_current(self.key[0]) if self.key[0] else None

    def refresh(self):
        if self._building:
            return
        try:
            candidate = self.candidate()
            self._refresh_drawing(candidate)
            changes = []
            for key, title in self.titles.items():
                group, index = key
                old = self.baseline[group]
                new = candidate[group]
                if index is not None:
                    old = old[index] if old is not None else None
                    new = new[index] if new is not None else None
                if old != new:
                    unit = "°" if group.endswith("_deg") else " mm"
                    changes.append(f"{title}: {f'{old:g}' if old is not None else 'not configured'} to {new:g}{unit}")
            self.summary.text = "\n".join(changes) or "No geometry changes."
            self.apply_button.disabled = candidate == self.baseline
            self.note.text = (
                "Apply saves this machine’s scene setup."
                if self.key[0]
                else "Choose a machine profile to retain this setup across app restarts."
            )
        except ValueError as exc:
            self._refresh_drawing(error=str(exc))
            self.summary.text = str(exc)
            self.apply_button.disabled = True
            self.note.text = "Correct the highlighted values; the active preview is unchanged."
        if not self.current_matches():
            self.apply_button.disabled = True
            self.note.text = "The active setup changed. Reload current setup before applying this draft."
        if self.read_error:
            self.apply_button.disabled = True
            self.note.text = f"Scene file unavailable: {self.read_error}. Repair it, then reload current setup."
        if self.preparing:
            self.apply_button.disabled = True
            self.apply_button.text = "Preparing preview…"
            self.note.text = (
                "Preparing CAD in the background · active scene unchanged · Cancel or Keep draft remains available."
            )
        else:
            self.apply_button.text = "Apply to preview"

    def reload(self):
        self.cancel_preparation()
        profile = self.workspace.selected_machine_profile
        if (profile.get("id") if profile else None) != self.key[0]:
            self.note.text = "Machine profile changed. Cancel and reopen this editor for the selected machine."
            return
        try:
            saved_scene = self._read_saved_scene()
        except (ValueError, OSError) as exc:
            self.read_error = str(exc)
            self.refresh()
            return
        if saved_scene != self.saved_scene and saved_scene != capture_scene_setup(self.workspace):
            self.note.text = "Saved scene changed outside this editor. Reload the machine profile before editing."
            return
        self.saved_scene = copy.deepcopy(saved_scene)
        self.read_error = ""
        self.workspace.setup_drafts.pop(self.key, None)
        self.baseline = capture_scene_setup(self.workspace)
        self.model_identity = self._model_identity()
        self._building = True
        for (group, index), field in self.fields.items():
            values = self.baseline[group]
            if index is not None:
                values = (values or (127, 69.4182, 50.8762))[index]
            field.text = f"{values:g}"
        self.initial = self.raw()
        self._building = False
        self.refresh()

    def keep(self):
        self.cancel_preparation()
        self.popup.dismiss()

    def cancel(self):
        self.cancel_preparation()
        self.workspace.setup_drafts.pop(self.key, None)
        self.initial = self.raw()
        self.popup.dismiss()

    def cancel_preparation(self):
        if self.preparing:
            self.loads.invalidate(self.lane)
            self.preparing = False
            self.last_apply_result = False
            self.apply_button.text = "Apply to preview"

    def apply(self):
        """Accept an apply request; last_apply_result records its eventual outcome."""
        if self.preparing or self.loads.closed:
            return False
        self.last_apply_result = False
        if self.read_error:
            self.refresh()
            return False
        if not self.current_matches():
            self.refresh()
            return False
        try:
            candidate = self.candidate()
        except ValueError:
            self.refresh()
            return False
        profiles = [self.viewer.machine_profile, *self.viewer.machine_component_profiles.values()]
        profiles = tuple(dict.fromkeys(profile for profile in profiles if profile is not None))
        if not profiles:
            return self._apply_candidate(candidate)
        raw = self.raw()
        scale = self.viewer.move_scale_by_positon or 1
        placement = (
            candidate["workholding_offset_mm"],
            candidate["workholding_rotation_deg"],
            candidate["jaw_offset_mm"],
        )
        self.preparing = True
        self.last_apply_result = None
        self.refresh()

        def work():
            for profile in profiles:
                profile.prepare_render_buffers(candidate["work_offset_mm"], scale, placement)

        def finish(_result, error):
            self.preparing = False
            self.last_apply_result = False
            self.refresh()
            if not self.popup._is_open or getattr(self.workspace, "_profile_load_closed", False):
                return
            if raw != self.raw() or not self.current_matches() or scale != (self.viewer.move_scale_by_positon or 1):
                self.note.text = "Draft or active setup changed during preparation · review and apply again."
                return
            if error is not None:
                self.note.text = "Not applied; CAD preparation failed: " + error
                return
            self.last_apply_result = self._apply_candidate(candidate)

        if not self.loads.submit(self.lane, work, finish):
            self.preparing = False
            self.last_apply_result = False
            self.refresh()
            return False
        return True

    def _apply_candidate(self, candidate):
        viewer, ws = self.viewer, self.workspace
        old_setup = viewer.machine_setup
        old_rest = viewer._rest_stock_geometry
        old_geometry = copy.deepcopy(getattr(ws, "simulation_geometry", {}))
        view = capture_view(viewer)
        ws.scene_edit_in_progress = True
        try:
            self._configure(candidate)
            if self.key[0]:
                ws.scene_setup_store.save(self.key[0], candidate, expected=self.saved_scene)
        except (ValueError, OSError) as exc:
            ws.component_choices["stock"].text = self.baseline["choices"]["stock"]
            viewer.machine_setup = old_setup
            viewer.workholding_offset_mm = tuple(self.baseline["workholding_offset_mm"])
            viewer.workholding_rotation_deg = self.baseline["workholding_rotation_deg"]
            viewer.jaw_offset_mm = self.baseline["jaw_offset_mm"]
            ws.simulation_geometry = old_geometry
            self.note.text = f"Not applied; prior preview restored: {exc}"
            try:
                viewer.set_rest_stock_geometry(old_rest)
                viewer._machine_pose = viewer._machine_pose_for((0, 0, 0))
                if viewer.machine_visible:
                    viewer._build_machine_scene()
                restore_view(viewer, view)
            except (ValueError, OSError) as redraw_error:
                viewer._rest_stock_geometry = old_rest
                self.note.text = f"Not applied; prior geometry restored, redraw unavailable: {redraw_error}"
            return False
        finally:
            ws.scene_edit_in_progress = False
        ws.setup_drafts.pop(self.key, None)
        self.initial = self.raw()
        ws.object_inspector.refresh_trigger()
        self.popup.dismiss()
        self.last_apply_result = True
        return True

    def _configure(self, setup):
        ws, viewer = self.workspace, self.viewer
        if self.kind == "stock":
            ws.component_choices["stock"].text = setup["choices"]["stock"]
            viewer.configure_machine(
                work_offset_mm=setup["work_offset_mm"],
                stock_size_mm=setup["stock_size_mm"],
                stock_origin_mm=setup["stock_origin_mm"],
                stock_rotation_deg=setup["stock_rotation_deg"],
            )
            ws.simulation_geometry = {
                "size": setup["stock_size_mm"],
                "origin": setup["stock_origin_mm"],
                "offset": setup["work_offset_mm"],
                "rotation_deg": setup["stock_rotation_deg"],
            }
        else:
            viewer.configure_workholding(
                setup["workholding_offset_mm"], setup["workholding_rotation_deg"], setup["jaw_offset_mm"]
            )


def open_setup_editor(workspace, kind):
    previous = getattr(workspace, "setup_editor", None)
    if previous and previous.popup._is_open:
        if previous.kind == kind:
            return previous
        previous.keep()
    if workspace.machine.keyboard_jog_control:
        workspace.machine.toggle_keyboard_jog_control(disable=True)
    editor = SetupEditor(workspace, kind)
    workspace.setup_editor = editor
    editor.popup.open()
    return editor
