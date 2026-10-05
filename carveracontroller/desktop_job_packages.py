"""Explicit local job export/import; restoring a job never uploads or runs it."""

import copy
import json
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

from kivy.clock import Clock

from carveracontroller.machine.job_packages import (
    JobPackage,
    load_package,
    resolve_setup_assets,
    retained_camera_calibration,
    save_package,
)


def _assets(value, result):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_path") and isinstance(item, str) and item:
                result[item] = Path(item).expanduser()
            else:
                _assets(item, result)
    elif isinstance(value, list):
        for item in value:
            _assets(item, result)


def capture_job(workspace):
    """Capture selected program and local setup; no controller query or command."""
    if getattr(workspace, "historical_preview", None) is not None:
        raise ValueError("Restore the previous scene before exporting the current job setup")
    filename = workspace.app.selected_local_filename
    if not filename:
        raise ValueError("Choose a local program before exporting a job")
    path = Path(filename)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Job programs are limited to 64 MB")
    viewer = workspace.machine.gcode_viewer
    setup = viewer.machine_setup
    records = workspace.profile_store.data if workspace.profile_store else {}
    previous = getattr(getattr(workspace, "restored_job", None), "package", None)
    tool_records = {record["id"]: record for record in (previous.tools if previous else [])}
    tool_records.update({record["id"]: record for record in records.get("tools", [])})
    components = []
    for group, profile in viewer.machine_component_profiles.items():
        asset_path = getattr(profile, "asset_path", None)
        if not asset_path:
            raise ValueError(f"Selected {group} has no source asset path; choose a saved CAD profile first")
        components.append({"group": group, "cad_path": asset_path})
    job = JobPackage(
        name=path.stem,
        program=path.read_bytes(),
        program_name=path.name,
        machine=dict(workspace.selected_machine_profile or {}),
        tools=list(tool_records.values()),
        toolsets=[dict(workspace.loaded_toolset)] if workspace.loaded_toolset else [],
        stock={
            "size_mm": list(setup.stock_size_mm) if setup.stock_size_mm else None,
            "origin_mm": list(setup.stock_origin_mm),
            "rotation_deg": getattr(setup, "stock_rotation_deg", 0),
            "work_offset_mm": list(setup.work_offset_mm),
            "alignment_confirmed": False,
        },
        fixtures=components,
        vise={
            "offset_mm": list(viewer.workholding_offset_mm),
            "rotation_deg": viewer.workholding_rotation_deg,
            "jaw_offset_mm": viewer.jaw_offset_mm,
        },
        material_recipes=previous.material_recipes if previous else [],
        inspection_plan=copy.deepcopy(previous.inspection_plan) if previous else {},
        photographs=list(previous.photographs) if previous else [],
    )
    _assets(job.machine, job.assets)
    _assets(job.tools, job.assets)
    _assets(job.fixtures, job.assets)
    if previous:
        restored = workspace.restored_job
        job.assets.update(restored.asset_paths)
        for reference in job.photographs:
            if reference not in restored.asset_paths:
                raise ValueError("Restored photograph asset is unavailable")
            job.assets[reference] = restored.asset_paths[reference]
    simulation = getattr(workspace, "simulation_panel", None)
    if simulation and simulation.rest_stock is not None:
        if simulation.rest_identity != simulation._identity():
            raise ValueError("Rest stock belongs to an older setup; reset or recompute it before exporting")
        cache = Path.home() / ".carvera" / "jobs" / "export-assets"
        cache.mkdir(parents=True, exist_ok=True)
        snapshot_path = cache / (str(uuid.uuid4()) + ".cvstock")
        snapshot_path.write_text(json.dumps(simulation.rest_stock.snapshot()))
        job.stock["residual_stock_path"] = str(snapshot_path)
        job.assets[str(snapshot_path)] = snapshot_path
    calibration = getattr(workspace, "camera_registration_panel", None)
    if calibration is not None:
        job.inspection_plan.pop("camera_registration", None)
        job.inspection_plan.pop("camera_calibration_path", None)
    job.camera_calibration = _camera_snapshot(calibration)
    return job


def export_job(workspace):
    def selected(path):
        try:
            job = capture_job(workspace)
        except (OSError, ValueError) as exc:
            workspace.package_note.text = str(exc)
            return
        workspace.package_note.text = "Exporting program, setup and CAD assets…"

        def run():
            try:
                save_package(job, path)
                message = f"Saved self-contained job: {path}"
            except (OSError, ValueError) as exc:
                message = "Export failed: " + str(exc)
            Clock.schedule_once(lambda _dt: setattr(workspace.package_note, "text", message), 0)

        threading.Thread(target=run, daemon=True).start()

    workspace.choose_profile_file(selected, save=True, extension=".cvjob", title="Export complete job")


def import_job(workspace):
    def selected(path):
        if workspace.app.state not in ("Idle", "N/A") or workspace.app.playing:
            workspace.package_note.text = "Finish the active run or preview before restoring a job."
            return
        generation = getattr(workspace, "_job_import_generation", 0) + 1
        workspace._job_import_generation = generation
        owner = _import_owner(workspace)
        inventory = (
            copy.deepcopy({t["id"]: t for t in workspace.profile_store.data["tools"]})
            if workspace.profile_store
            else {}
        )
        destination = Path.home() / ".carvera" / "jobs" / str(uuid.uuid4())
        workspace.package_note.text = "Validating archive and installing local assets…"

        def run():
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                loaded = load_package(path, destination=destination, inventory=inventory)
                setup = resolve_setup_assets(loaded)
                calibration = retained_camera_calibration(loaded)
                prepared = prepare_job_preview(loaded, setup, destination)
                error = None
            except (OSError, ValueError, KeyError, TypeError) as exc:
                loaded, setup, calibration, prepared, error = None, None, None, None, str(exc)
            Clock.schedule_once(lambda _dt: restore(loaded, setup, calibration, prepared, error), 0)

        def restore(loaded, setup, calibration, prepared, error):
            if workspace._job_import_generation != generation:
                return
            if _import_owner(workspace) != owner:
                workspace.package_note.text = (
                    "Import retained locally; selection or connection changed. Import again to apply."
                )
                return
            if error:
                workspace.package_note.text = "Import failed: " + error
                return
            if workspace.app.state not in ("Idle", "N/A") or workspace.app.playing:
                workspace.package_note.text = "Assets installed; restoration deferred because machine activity changed."
                return
            try:
                placement, definitions, profile, components, bank, program_path, residual = prepared
                if profile:
                    workspace.apply_machine_profile(profile)
                viewer = workspace.machine.gcode_viewer
                viewer.configure_machine(
                    placement.work_offset_mm,
                    placement.stock_size_mm,
                    placement.stock_origin_mm,
                    stock_rotation_deg=placement.stock_rotation_deg,
                )
                # Imported coordinates remain unmeasured even though they are explicit.
                viewer.machine_setup = placement
                for group, cad in components:
                    viewer.select_machine_component(group, cad)
                vise = setup["vise"]
                if vise:
                    viewer.configure_workholding(
                        vise.get("offset_mm", (0, 0, 0)), vise.get("rotation_deg", 0), vise.get("jaw_offset_mm", 0)
                    )
                viewer.load_tool_profiles(definitions)
                workspace.loaded_toolset = bank
                workspace.restored_job = loaded
                workspace.machine.file_popup.local_rv.curr_selected_file = str(program_path)
                workspace.machine.view_local_file()
                workspace.pending_job_rest_stock = (str(program_path), residual) if residual is not None else None
                workspace.camera_registration_panel.apply_calibration(calibration)
                issues = []
                if loaded.report.missing_inventory:
                    issues.append(f"{len(loaded.report.missing_inventory)} tools missing from local inventory")
                if loaded.report.conflicting_inventory:
                    issues.append(f"{len(loaded.report.conflicting_inventory)} tool definitions conflict")
                workspace.package_note.text = "Restored local preview · physical setup unverified" + (
                    "\n" + "; ".join(issues) if issues else ""
                )
            except (OSError, ValueError, KeyError) as exc:
                workspace.package_note.text = "Assets installed; preview restoration failed: " + str(exc)

        threading.Thread(target=run, daemon=True).start()

    workspace.choose_asset_file(selected, suffixes=(".cvjob",))


def _import_owner(workspace):
    profile = getattr(workspace, "selected_machine_profile", None)
    return (
        getattr(workspace.machine.controller, "_connection_generation", None),
        profile.get("id") if profile else None,
        getattr(workspace.app, "selected_local_filename", None),
    )


def prepare_job_preview(loaded, setup, destination):
    """Prepare complete local definitions and disk-backed assets off the UI thread."""
    from carveracontroller.addons.machine_simulation.model import MachineSetup
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from carveracontroller.machine.desktop_profiles import to_tool_definition, validate_record

    stock = setup["stock"]
    placement = MachineSetup(
        tuple(stock.get("work_offset_mm", (-180, -120, -110))),
        tuple(stock["size_mm"]) if stock.get("size_mm") else None,
        tuple(stock.get("origin_mm", (0, 0, 0))),
        False,
        stock.get("rotation_deg", 0),
    )
    definitions = {t["number"]: to_tool_definition(t) for t in setup["tools"]}
    profile = validate_record("machines", setup["machine"]) if setup["machine"] else None
    components = [(record["group"], MachineProfile.load(record["cad_path"])) for record in setup["fixtures"]]
    if any(group not in ("fixture", "workholding") or not cad.groups[group].indices for group, cad in components):
        raise ValueError("Job component does not contain registered fixture/vise geometry")
    if setup["toolsets"]:
        bank = validate_record("toolsets", setup["toolsets"][0])
        tools = {t["id"]: t for t in setup["tools"]}
        definitions = {
            int(slot): to_tool_definition(tools[identifier], number=int(slot))
            for slot, identifier in bank["slots"].items()
        }
    else:
        bank = None
    program_path = destination / loaded.package.program_name
    program_path.write_bytes(loaded.package.program)
    residual_path = stock.get("residual_stock_path")
    residual = None
    if residual_path:
        from carveracontroller.addons.manufacturing_simulation import StockVolume

        with Path(residual_path).open("rb") as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("Retained rest stock exceeds the 64 MB budget")
        residual = StockVolume.from_snapshot(json.loads(raw))
    return placement, definitions, profile, components, bank, program_path, residual


def capture_recording_job(workspace):
    """Capture selected declarations on UI thread; defer program/CAD reads to worker."""
    if getattr(workspace, "historical_preview", None) is not None:
        raise ValueError("Restore the previous scene before capturing a new setup")
    path = Path(workspace.app.selected_local_filename)
    viewer = workspace.machine.gcode_viewer
    setup = viewer.machine_setup
    library = workspace.profile_store.data if workspace.profile_store else {}
    toolset = copy.deepcopy(workspace.loaded_toolset)
    selected_ids = set(toolset.get("slots", {}).values()) if toolset else set()
    assembly = viewer.assembly_preview_binding
    if assembly:
        selected_ids.add(assembly["profile_id"])
    components = []
    for group, profile in viewer.machine_component_profiles.items():
        asset = getattr(profile, "asset_path", None)
        if not asset:
            raise ValueError(f"Selected {group} has no retained CAD source")
        components.append({"group": group, "cad_path": str(asset)})
    definitions = []
    for definition in viewer.library_tool_table_mm.values():
        item = asdict(definition)
        item["tool_type"] = definition.tool_type.value
        definitions.append(item)
    job = JobPackage(
        name=path.stem,
        program=b"",
        program_name=path.name,
        machine=copy.deepcopy(workspace.selected_machine_profile or {}),
        tools=[tool for tool in library.get("tools", []) if tool["id"] in selected_ids],
        toolsets=[toolset] if toolset else [],
        stock={
            "size_mm": list(setup.stock_size_mm) if setup.stock_size_mm else None,
            "origin_mm": list(setup.stock_origin_mm),
            "rotation_deg": getattr(setup, "stock_rotation_deg", 0),
            "work_offset_mm": list(setup.work_offset_mm),
            "alignment_confirmed": setup.alignment_confirmed,
        },
        fixtures=components,
        vise={
            "offset_mm": list(viewer.workholding_offset_mm),
            "rotation_deg": viewer.workholding_rotation_deg,
            "jaw_offset_mm": viewer.jaw_offset_mm,
        },
        inspection_plan={
            "scope": "declared_setup_assets_at_recording_start",
            "tool_definitions_mm": definitions,
            "assembly_binding": {
                k: copy.deepcopy(assembly[k])
                for k in ("assembly_id", "revision_id", "profile_id", "design_fingerprint", "number", "name")
            }
            if assembly
            else None,
        },
    )
    job.camera_calibration = _camera_snapshot(workspace.camera_registration_panel)
    for value in (job.machine, job.tools, job.fixtures, job.inspection_plan):
        _assets(value, job.assets)
    return job


def _camera_snapshot(panel):
    if panel is None or panel.registration is None:
        return None
    if hasattr(panel, "_input_identity") and panel.fit_identity != panel._input_identity():
        raise ValueError("Camera calibration inputs changed; refit before retaining setup")
    return panel.registration, tuple(panel.observations), getattr(panel, "reference", None), panel.reference_machine_y
