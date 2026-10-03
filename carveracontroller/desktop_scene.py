"""Local component choices for visual setup; never communicates with hardware."""

import copy
import json
import math
import os
import tempfile
from pathlib import Path


class SceneSetupStore:
    """Versioned local preview state, isolated by stable machine profile ID."""

    MAX_BYTES = 1024 * 1024
    COMPONENTS = ("outer", "table", "spindle", "atc", "cutter", "fixture", "workholding", "stock")
    CHOICES = ("cutter", "fixture", "workholding", "stock")
    KEYS = {
        "work_offset_mm",
        "stock_size_mm",
        "stock_origin_mm",
        "workholding_offset_mm",
        "workholding_rotation_deg",
        "jaw_offset_mm",
        "choices",
        "visibility",
        "scope",
    }

    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/scene-setups.json")
        self.data = {}
        self.load_error = None
        try:
            self.data = self._read()
        except (ValueError, TypeError, OSError) as exc:
            self.load_error = str(exc)

    @staticmethod
    def _object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate scene setup key")
            result[key] = value
        return result

    @staticmethod
    def _identity(profile_id):
        if not isinstance(profile_id, str) or not profile_id.strip() or len(profile_id) > 160:
            raise ValueError("Scene setup requires a stable machine profile ID")

    @staticmethod
    def _number(value):
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1000:
            raise ValueError("Scene coordinates must be finite and within 1000 mm/degrees")
        return float(value)

    @classmethod
    def validate(cls, setup):
        if not isinstance(setup, dict) or set(setup) != cls.KEYS:
            raise ValueError("Unknown or missing scene setup fields")
        result = {}
        for key in ("work_offset_mm", "stock_size_mm", "stock_origin_mm", "workholding_offset_mm"):
            value = setup[key]
            if key == "stock_size_mm" and value is None:
                result[key] = None
                continue
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError("Scene coordinate vectors must have three values")
            result[key] = [cls._number(v) for v in value]
            if key == "stock_size_mm" and min(result[key]) <= 0:
                raise ValueError("Stock sizes must be greater than zero")
        for key in ("workholding_rotation_deg", "jaw_offset_mm"):
            result[key] = cls._number(setup[key])
        choices = setup["choices"]
        if not isinstance(choices, dict) or set(choices) != set(cls.CHOICES):
            raise ValueError("Unknown or missing component choices")
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 200
            or value in ("New stock…", "Import registered CAD…")
            for value in choices.values()
        ):
            raise ValueError("Invalid saved component choice")
        visibility = setup["visibility"]
        if not isinstance(visibility, dict) or set(visibility) != set(cls.COMPONENTS):
            raise ValueError("Unknown or missing component visibility")
        if any(type(value) is not bool for value in visibility.values()):
            raise ValueError("Component visibility must be boolean")
        if setup["scope"] not in ("machine", "workarea"):
            raise ValueError("Unknown scene framing")
        if visibility["outer"] != (setup["scope"] == "machine"):
            raise ValueError("Outer machine visibility and framing must agree")
        result.update(choices=dict(choices), visibility=dict(visibility), scope=setup["scope"])
        return result

    def _read(self):
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Scene setups exceed 1 MiB")
        try:
            raw = json.loads(self.path.read_text(), object_pairs_hook=self._object)
        except RecursionError as exc:
            raise ValueError("Scene setup JSON is nested too deeply") from exc
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "profiles"}:
            raise ValueError("Invalid scene setup document")
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("Unsupported scene setup schema")
        profiles = raw["profiles"]
        if not isinstance(profiles, dict) or len(profiles) > 100:
            raise ValueError("Scene setup profile limit is 100")
        for profile_id, setup in profiles.items():
            self._identity(profile_id)
            self.validate(setup)
        return {key: self.validate(value) for key, value in profiles.items()}

    def get(self, profile_id):
        self._identity(profile_id)
        return copy.deepcopy(self.data.get(profile_id))

    def save(self, profile_id, setup):
        self._identity(profile_id)
        validated = self.validate(setup)
        if self.load_error:
            raise ValueError(f"Repair scene setups before saving: {self.load_error}")
        # Read back before writing: preserve other profiles and refuse a newly corrupt file.
        updated = self._read()
        updated[profile_id] = validated
        if len(updated) > 100:
            raise ValueError("Scene setup profile limit is 100")
        raw = json.dumps({"schema_version": 1, "profiles": updated}, indent=2, allow_nan=False)
        if len(raw.encode()) > self.MAX_BYTES:
            raise ValueError("Scene setups exceed 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
        self.data = updated


def capture_scene_setup(workspace):
    """Capture only preview metadata; never derives or changes CNC offsets."""
    viewer = workspace.machine.gcode_viewer
    setup = viewer.machine_setup
    return SceneSetupStore.validate(
        {
            "work_offset_mm": setup.work_offset_mm,
            "stock_size_mm": setup.stock_size_mm,
            "stock_origin_mm": setup.stock_origin_mm,
            "workholding_offset_mm": viewer.workholding_offset_mm,
            "workholding_rotation_deg": viewer.workholding_rotation_deg,
            "jaw_offset_mm": viewer.jaw_offset_mm,
            "choices": {kind: choice.text for kind, choice in workspace.component_choices.items()},
            "visibility": {kind: check.active for kind, check in workspace.component_checks.items()},
            "scope": viewer.machine_view_scope,
        }
    )


def restore_scene_geometry(workspace, setup):
    """Restore validated local geometry after component choices have been loaded."""
    setup = SceneSetupStore.validate(setup)
    viewer = workspace.machine.gcode_viewer
    viewer.configure_workholding(
        setup["workholding_offset_mm"], setup["workholding_rotation_deg"], setup["jaw_offset_mm"]
    )
    viewer.configure_machine(
        work_offset_mm=setup["work_offset_mm"],
        stock_size_mm=setup["stock_size_mm"],
        stock_origin_mm=setup["stock_origin_mm"],
    )
    workspace.simulation_geometry = {"origin": setup["stock_origin_mm"], "offset": setup["work_offset_mm"]}
    if setup["stock_size_mm"] is not None:
        workspace.simulation_geometry["size"] = setup["stock_size_mm"]


class SceneLibrary:
    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/scene-library.json")
        self.data = {key: [] for key in ("fixtures", "vises", "stocks")}
        self.load_error = None
        try:
            self._load()
        except (ValueError, OSError, TypeError) as exc:
            self.load_error = str(exc)

    def _load(self):
        if self.path.exists():
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError("Scene library exceeds 1 MiB")
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError("Scene library must be an object")
            validated = {}
            for key in self.data:
                records = data.get(key, [])
                if not isinstance(records, list):
                    raise ValueError("Scene components must be lists")
                for record in records:
                    self.validate(key, record)
                validated[key] = records
            self.data = validated

    @staticmethod
    def validate(kind, record):
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("name"), str)
            or not record["name"].strip()
            or len(record["name"]) > 160
        ):
            raise ValueError("Enter a component name of up to 160 characters")
        if kind == "stocks":
            for key in ("size", "origin"):
                values = record.get(key)
                if (
                    not isinstance(values, (tuple, list))
                    or len(values) != 3
                    or not all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= 1000 for v in values)
                ):
                    raise ValueError("Stock coordinates must be finite and within 1000 mm")
            if min(record["size"]) <= 0:
                raise ValueError("Stock sizes must be greater than zero")
        elif not isinstance(record.get("path"), str) or not record["path"].strip() or len(record["path"]) > 2048:
            raise ValueError("Enter a registered machine CAD profile path")

    def save(self, kind, record):
        if self.load_error:
            raise ValueError(f"Repair the scene library before saving: {self.load_error}")
        if kind not in self.data:
            raise ValueError("Unknown component kind")
        self.validate(kind, record)
        updated = dict(self.data)
        updated[kind] = [r for r in self.data[kind] if r["name"] != record["name"]] + [record]
        raw = json.dumps(updated, indent=2)
        if len(raw.encode()) > 1024 * 1024:
            raise ValueError("Scene library exceeds 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as f:
            f.write(raw)
            name = f.name
        os.replace(name, self.path)
        self.data = updated


def build_scene_controls(workspace):
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.checkbox import CheckBox
    from kivy.uix.popup import Popup

    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Choice, Field, label

    viewer = workspace.machine.gcode_viewer
    page = workspace._page("Scene", scroll=True)
    page.add_widget(label("Scene & components", 20, height=34, bold=True))
    note = label("Draft visual setup • selections never change physical tooling or offsets.", 11, MUTED, 40)
    page.add_widget(note)
    library = SceneLibrary()
    if library.load_error:
        note.text = f"Scene library: {library.load_error}"
    workspace.scene_library = library
    setups = SceneSetupStore()
    workspace.scene_setup_store = setups
    suspended = False

    def save_setup():
        if suspended or not workspace.selected_machine_profile:
            return False
        try:
            setups.save(workspace.selected_machine_profile["id"], capture_scene_setup(workspace))
            return True
        except (ValueError, TypeError, OSError) as exc:
            note.text = f"Preview remains available • scene setup not saved: {exc}"
            return False

    workspace.save_scene_setup = save_setup
    scope = Choice(text="Full machine", values=("Full machine", "Work area"))
    workspace.scene_scope = scope
    page.add_widget(scope)
    choices, checks = {}, {}
    selected = {}
    workspace.component_choices = choices
    workspace.component_checks = checks

    def set_scope(_widget, value):
        if suspended:
            return
        viewer.set_machine_view_scope("machine" if value == "Full machine" else "workarea")
        checks["outer"].active = value == "Full machine"
        save_setup()

    scope.bind(text=set_scope)

    def toggle(kind, visible):
        if suspended:
            return
        if kind == "outer":
            for group in ("fixed", "carriage"):
                viewer.set_machine_group_visible(group, visible)
            viewer.machine_view_scope = "machine" if visible else "workarea"
            scope.text = "Full machine" if visible else "Work area"
            viewer.restore_default_view()
        elif kind == "cutter":
            viewer.set_cutter_visible(visible)
        else:
            viewer.set_machine_group_visible(kind, visible)
        save_setup()

    for kind, title, selection in (
        ("outer", "Outer machine", False),
        ("table", "Machine bed", False),
        ("spindle", "Spindle", False),
        ("atc", "ATC / slots", False),
        ("cutter", "Cutter / mill", True),
        ("fixture", "Fixture plate", True),
        ("workholding", "Vise", True),
        ("stock", "Stock", True),
    ):
        row = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(38))
        check = CheckBox(active=True, size_hint_x=None, width=dp(30))
        check.bind(active=lambda _w, value, kind=kind: toggle(kind, value))
        checks[kind] = check
        row.add_widget(check)
        row.add_widget(label(title, 12, height=38, size_hint_x=None, width=dp(110)))
        if selection:
            choice = Choice(
                text="Follow program"
                if kind == "cutter"
                else "Current model"
                if kind != "stock"
                else "No stock configured"
            )
            choices[kind] = choice
            selected[kind] = choice.text
            row.add_widget(choice)
        else:
            state = label("Visible", 11, MUTED, 38)
            check.bind(active=lambda _w, value, state=state: setattr(state, "text", "Visible" if value else "Hidden"))
            row.add_widget(state)
        page.add_widget(row)
    actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(8))
    actions.add_widget(Action("Vise placement…", workspace._workholding_setup))
    actions.add_widget(Action("Origin & stock setup…", workspace._machine_setup))
    actions.add_widget(Action("Tool library…", workspace._open_profiles))
    page.add_widget(actions)

    def refresh_options(*_args):
        tools = workspace.profile_store.data["tools"] if workspace.profile_store else []
        workspace.scene_tool_options = {f"T{t['number']} · {t['name']}": t for t in tools}
        choices["cutter"].values = ("Follow program", *workspace.scene_tool_options)
        for kind, records in (("fixture", "fixtures"), ("workholding", "vises")):
            choices[kind].values = (
                "Current model",
                *(r["name"] for r in library.data[records]),
                "Import registered CAD…",
            )
        choices["stock"].values = (
            "No stock configured",
            "Current stock",
            *(r["name"] for r in library.data["stocks"]),
            "New stock…",
        )

    for choice in choices.values():
        choice.bind(on_press=refresh_options)

    def import_component(kind):
        def loaded(path):
            try:
                profile = MachineProfile.load(path)
                if not profile.groups[kind].indices:
                    raise ValueError("Registered profile has no geometry for this component")
                record = {"name": Path(path).name.removesuffix(".gz").removesuffix(".json"), "path": path}
                library.save("fixtures" if kind == "fixture" else "vises", record)
                refresh_options()
                choices[kind].text = record["name"]
                viewer.select_machine_component(kind, profile)
                note.text = "Registered CAD loaded • confirm mounting coordinates physically."
            except (ValueError, OSError) as exc:
                note.text = str(exc)
                choices[kind].text = "Current model"

        workspace.choose_asset_file(loaded, suffixes=(".json.gz",))

    def new_stock():
        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        name = Field(text="Stock block", hint_text="Stock profile name")
        body.add_widget(name)
        body.add_widget(label("Dimensions and minimum corner in program coordinates · mm", 11, MUTED, 28))
        fields = []
        grid = AdaptiveGrid(max_cols=3, min_width=105, row_height=62, spacing=dp(8))
        for title, value in zip(
            ("Size X", "Size Y", "Size Z", "Minimum X", "Minimum Y", "Minimum Z"),
            (
                *(viewer.machine_setup.stock_size_mm or (127, 69.4182, 50.8762)),
                *(
                    viewer.machine_setup.stock_origin_mm
                    if viewer.machine_setup.stock_size_mm
                    else (-63.5, -34.7091, -50.8762)
                ),
            ),
        ):
            cell = BoxLayout(orientation="vertical")
            cell.add_widget(label(title, 11, MUTED, 24))
            field = Field(text=f"{value:g}")
            fields.append(field)
            cell.add_widget(field)
            grid.add_widget(cell)
        body.add_widget(grid)
        status = label("A saved stock volume is a draft reference, not stock removal simulation.", 11, MUTED, 38)
        body.add_widget(status)
        popup = Popup(
            title="Save stock profile", content=body, size_hint=(0.8, None), height=min(dp(440), workspace.height * 0.9)
        )

        def save():
            try:
                values = [float(f.text) for f in fields]
                record = {"name": name.text.strip(), "size": values[:3], "origin": values[3:]}
                library.save("stocks", record)
                refresh_options()
                if choices["stock"].text == record["name"]:
                    select("stock", record["name"])
                else:
                    choices["stock"].text = record["name"]
                popup.dismiss()
            except (ValueError, OSError) as exc:
                status.text = str(exc)

        row = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(36))
        row.add_widget(Action("Save & select", save, primary=True))
        row.add_widget(Action("Cancel", popup.dismiss))
        body.add_widget(row)
        popup.open()

    def select(kind, value, *, restoring=False):
        if suspended and not restoring:
            return
        try:
            if kind == "cutter":
                if value == "Follow program":
                    viewer.select_preview_tool(None)
                else:
                    tool = workspace.scene_tool_options[value]
                    workspace.apply_tool_profile(tool)
                    viewer.select_preview_tool(tool["number"])
            elif kind == "stock":
                if value == "New stock…":
                    choices[kind].text = selected[kind]
                    new_stock()
                    return
                if value == "Current stock":
                    selected[kind] = value
                    save_setup()
                    return
                record = next((r for r in library.data["stocks"] if r["name"] == value), None)
                viewer.configure_machine(
                    work_offset_mm=viewer.machine_setup.work_offset_mm,
                    stock_size_mm=record["size"] if record else None,
                    stock_origin_mm=record["origin"] if record else (0, 0, 0),
                )
            elif value == "Import registered CAD…":
                choices[kind].text = selected[kind]
                import_component(kind)
                return
            elif value == "Current model":
                viewer.machine_component_profiles.pop(kind, None)
                if viewer.machine_visible:
                    viewer._build_machine_scene()
                    viewer.restore_default_view()
            else:
                record = next(
                    r for r in library.data["fixtures" if kind == "fixture" else "vises"] if r["name"] == value
                )
                viewer.select_machine_component(kind, MachineProfile.load(record["path"]))
            selected[kind] = value
            note.text = (
                "Manual cutter preview • choose Follow program to restore program tool changes."
                if kind == "cutter" and value != "Follow program"
                else "Draft visual setup • selections never change physical tooling or offsets."
            )
            save_setup()
        except (ValueError, OSError, KeyError, StopIteration) as exc:
            note.text = f"Selection: {exc}"

    for kind, choice in choices.items():
        choice.bind(text=lambda _w, value, kind=kind: select(kind, value))
    refresh_options()

    def seed(profile):
        nonlocal suspended
        suspended = True
        was_visible = viewer.machine_visible
        # Visibility setters otherwise rebuild and refit the complete imported CAD
        # for every checkbox. Restore the scene as one local preview transaction.
        if was_visible:
            viewer.set_machine_visible(False)
        try:
            # Reset unsaved selections before switching profiles so another machine's
            # stock and visibility do not become this profile's initial setup.
            workspace.simulation_geometry = {}
            viewer.machine_component_profiles.clear()
            viewer.select_preview_tool(None)
            for kind, choice in choices.items():
                choice.text = (
                    "Follow program"
                    if kind == "cutter"
                    else "No stock configured"
                    if kind == "stock"
                    else "Current model"
                )
                selected[kind] = choice.text
            scope.text = "Full machine"
            for kind, check in checks.items():
                check.active = True
            path = profile.get("cad_path", "") if profile else ""
            if path and viewer.machine_profile and not library.load_error:
                for kind, records, title in (
                    ("fixture", "fixtures", "Saunders ¼-inch plate"),
                    ("workholding", "vises", "Gen3 Hobby Mod Vise"),
                ):
                    if viewer.machine_profile.groups[kind].indices:
                        if "saunders" not in path.lower():
                            title = f"{viewer.machine_profile.model} {kind}"
                        if not any(r["path"] == path for r in library.data[records]):
                            library.save(records, {"name": title, "path": path})
                        refresh_options()
                        choices[kind].text = next(r["name"] for r in library.data[records] if r["path"] == path)
                        select(kind, choices[kind].text, restoring=True)
            refresh_options()
            saved = setups.get(profile["id"]) if profile else None
            if saved:
                missing = []
                for kind, value in saved["choices"].items():
                    if value in choices[kind].values:
                        choices[kind].text = value
                        selected[kind] = value
                        if kind != "stock":
                            select(kind, value, restoring=True)
                    else:
                        missing.append(f"{kind}: {value}")
                # Restore numeric draft after named stock/component selections, which
                # may have changed in the shared library since this setup was saved.
                restore_scene_geometry(workspace, saved)
                if saved["stock_size_mm"] and missing and saved["choices"]["stock"] not in choices["stock"].values:
                    choices["stock"].text = "Current stock"
                    selected["stock"] = "Current stock"
                scope.text = "Full machine" if saved["scope"] == "machine" else "Work area"
                for kind, visible in saved["visibility"].items():
                    checks[kind].active = visible
                note.text = "Saved draft restored • confirm stock and workholding physically."
                if missing:
                    note.text += " Missing library choices: " + "; ".join(missing)
            elif setups.load_error:
                note.text = f"Scene setups not restored: {setups.load_error}"
            if not saved:
                viewer.configure_machine()
            viewer.set_machine_view_scope("machine" if scope.text == "Full machine" else "workarea")
            for kind, check in checks.items():
                if kind == "outer":
                    continue
                if kind == "cutter":
                    viewer.set_cutter_visible(check.active)
                else:
                    viewer.set_machine_group_visible(kind, check.active)
        except (ValueError, TypeError, OSError) as exc:
            note.text = f"Scene setup restoration: {exc}"
        finally:
            if was_visible:
                viewer.set_machine_visible(True)
            suspended = False

    workspace.seed_scene_choices = seed
