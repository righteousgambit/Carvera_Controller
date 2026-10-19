"""Explicit local job export/import; restoring a job never uploads or runs it."""

import copy
import hashlib
import io
import json
import logging
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.machine.job_packages import (
    JobPackage,
    ResidualStockExport,
    load_package,
    resolve_setup_assets,
    retained_camera_calibration,
    save_package,
)
from carveracontroller.machine.program_bytes import read_program_bytes, selected_preview_identity

logger = logging.getLogger(__name__)


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


def selected_program_preview(workspace):
    return selected_preview_identity(
        workspace.app.selected_local_filename,
        getattr(workspace.app, "selected_remote_filename", ""),
        getattr(workspace.machine, "_last_loaded_file_key", None),
        getattr(workspace.machine.gcode_viewer, "loaded_program_hash", None),
    )


def capture_job(workspace, *, include_program=True):
    """Capture selected program and local setup; no controller query or command."""
    if getattr(workspace, "historical_preview", None) is not None:
        raise ValueError("Restore the previous scene before exporting the current job setup")
    filename = workspace.app.selected_local_filename
    if not filename:
        raise ValueError("Choose a local program before exporting a job")
    path = Path(filename)
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
        program=read_program_bytes(path, expected_preview=selected_program_preview(workspace))
        if include_program
        else b"",
        program_name=path.name,
        machine=copy.deepcopy(workspace.selected_machine_profile or {}),
        tools=copy.deepcopy(list(tool_records.values())),
        toolsets=[copy.deepcopy(workspace.loaded_toolset)] if workspace.loaded_toolset else [],
        stock={
            "size_mm": list(setup.stock_size_mm) if setup.stock_size_mm else None,
            "origin_mm": list(setup.stock_origin_mm),
            "rotation_deg": getattr(setup, "stock_rotation_deg", 0),
            **({"tilt_deg": list(setup.stock_tilt_deg)} if any(getattr(setup, "stock_tilt_deg", (0, 0))) else {}),
            "work_offset_mm": list(setup.work_offset_mm),
            "alignment_confirmed": False,
        },
        fixtures=components,
        vise={
            "offset_mm": list(viewer.workholding_offset_mm),
            "rotation_deg": viewer.workholding_rotation_deg,
            "jaw_offset_mm": viewer.jaw_offset_mm,
        },
        material_recipes=copy.deepcopy(previous.material_recipes) if previous else [],
        inspection_plan=copy.deepcopy(previous.inspection_plan) if previous else {},
        photographs=copy.deepcopy(previous.photographs) if previous else [],
    )
    _assets(job.machine, job.assets)
    _assets(job.tools, job.assets)
    _assets(job.fixtures, job.assets)
    if getattr(setup, "stock_model", None) is not None:
        job.stock["stock_source"] = setup.stock_model.reference
        _assets(job.stock, job.assets)
    if previous:
        restored = workspace.restored_job
        job.assets.update(restored.asset_paths)
        for reference in job.photographs:
            if reference not in restored.asset_paths:
                raise ValueError("Restored photograph asset is unavailable")
            job.assets[reference] = restored.asset_paths[reference]
    simulation = getattr(workspace, "simulation_panel", None)
    if simulation and simulation.rest_stock is not None:
        from carveracontroller.machine.geometry_changes import capture_context, digest_context

        context = capture_context(viewer, workspace.operation_panel.program, verify_assets=False)
        identity = context["program"], digest_context(context)
        if simulation.rest_identity != identity:
            raise ValueError("Rest stock belongs to an older setup; reset or recompute it before exporting")
        job.residual_stock = ResidualStockExport(simulation.rest_stock, setup, context, identity)
    calibration = getattr(workspace, "camera_registration_panel", None)
    if calibration is not None:
        job.inspection_plan.pop("camera_registration", None)
        job.inspection_plan.pop("camera_calibration_path", None)
    job.camera_calibration = _camera_snapshot(calibration)
    return job


def export_job(workspace):
    def selected(path):
        if getattr(workspace, "_job_export_active", False):
            workspace.package_note.text = "Wait for the current export to finish before starting another."
            return
        try:
            job = capture_job(workspace, include_program=False)
            filename = workspace.app.selected_local_filename
            expected = selected_program_preview(workspace)
        except (OSError, ValueError) as exc:
            workspace.package_note.text = str(exc)
            return
        generation = getattr(workspace, "_job_export_generation", 0) + 1
        workspace._job_export_generation = generation
        workspace._job_export_active = True
        workspace.package_note.text = "Exporting program, setup and CAD assets…"

        def run():
            try:
                job.program = read_program_bytes(filename, expected_preview=expected)
                save_package(job, path)
                message = f"Saved self-contained job: {path}"
            except Exception as exc:
                logger.exception("Job export preparation failed")
                message = "Export failed: " + (str(exc) or type(exc).__name__)

            def finish(_dt):
                if workspace._job_export_generation == generation:
                    workspace._job_export_active = False
                    workspace.package_note.text = message

            Clock.schedule_once(finish, 0)

        try:
            threading.Thread(target=run, daemon=True, name="job-export-prepare").start()
        except Exception as exc:
            logger.exception("Could not start job export")
            workspace._job_export_active = False
            workspace.package_note.text = "Could not start export: " + (str(exc) or type(exc).__name__)

    workspace.choose_profile_file(selected, save=True, extension=".cvjob", title="Export complete job")


def import_job(workspace):
    from carveracontroller.addons.tool_visualization.profile_loading import prepare_tool_profiles
    from carveracontroller.desktop_job_import_review import (
        JobImportReview,
        import_blocker,
        import_busy,
        import_context,
        review_sections,
    )

    def selected(path):
        blocker = import_blocker(workspace)
        if blocker:
            workspace.package_note.text = blocker
            return
        previous_review = getattr(workspace, "_job_import_review", None)
        if previous_review is not None:
            previous_review.cancel()
        generation = getattr(workspace, "_job_import_generation", 0) + 1
        workspace._job_import_generation = generation
        owner = _import_owner(workspace)
        context = import_context(workspace)
        viewer = workspace.machine.gcode_viewer
        previous_cad = getattr(viewer, "machine_profile", None)
        cam_tools = copy.deepcopy(getattr(viewer, "tool_table", {}) or {})
        scale, units = context["render"]
        inventory = (
            copy.deepcopy({t["id"]: t for t in workspace.profile_store.data["tools"]})
            if workspace.profile_store
            else {}
        )
        destination = Path.home() / ".carvera" / "jobs" / str(uuid.uuid4())

        def start():
            workspace._job_import_active = True
            workspace.package_note.text = "Preparing archive, setup and cutter geometry for review…"
            try:
                threading.Thread(target=run, daemon=True, name="job-import-prepare").start()
            except RuntimeError as exc:
                workspace._job_import_active = False
                workspace.package_note.text = f"Could not start job import: {exc}. Select the archive again."

        def run():
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                loaded = load_package(path, destination=destination, inventory=inventory)
                setup = resolve_setup_assets(loaded)
                calibration = retained_camera_calibration(loaded)
                prepared = prepare_job_preview(loaded, setup, destination)
                program_lines = tuple(io.StringIO(loaded.package.program.decode("utf-8"), newline=None).readlines())
                program_hash = hashlib.sha256("".join(program_lines).encode("utf-8")).hexdigest()
                profile_cad = (
                    workspace._prepare_selected_profile_cad(prepared[2], previous_cad) if prepared[2] else None
                )
                prepared_tools = prepare_tool_profiles(prepared[1], {}, cam_tools, scale, units)
                sections = review_sections(context, loaded, setup, prepared, calibration, profile_cad)
                error = None
            except Exception as exc:
                logger.exception("Job import preparation failed")
                loaded = setup = calibration = prepared = profile_cad = prepared_tools = sections = None
                error = str(exc) or type(exc).__name__
            Clock.schedule_once(
                lambda _dt: review(
                    loaded,
                    setup,
                    calibration,
                    prepared,
                    profile_cad,
                    prepared_tools,
                    program_lines if error is None else None,
                    program_hash if error is None else None,
                    sections,
                    error,
                ),
                0,
            )

        def review(
            loaded,
            setup,
            calibration,
            prepared,
            profile_cad,
            prepared_tools,
            program_lines,
            program_hash,
            sections,
            error,
        ):
            workspace._job_import_active = False
            pending = getattr(workspace, "_job_import_pending", None)
            workspace._job_import_pending = None
            if pending is not None:
                pending()
                return
            if workspace._job_import_generation != generation:
                return
            tool_ids = {record["id"] for record in loaded.package.tools} if loaded is not None else None
            reviewed_context = copy.deepcopy(context)
            if tool_ids is not None:
                reviewed_context["inventory"] = [record for record in context["inventory"] if record["id"] in tool_ids]
            if _import_owner(workspace) != owner or import_context(workspace, tool_ids) != reviewed_context:
                workspace.package_note.text = (
                    "Import retained locally; setup, tooling, selection or connection changed. Import again to review."
                )
                return
            if error:
                workspace.package_note.text = "Import failed: " + error
                return
            if import_busy(workspace):
                workspace.package_note.text = (
                    "Assets retained; restoration deferred because machine or preview activity changed."
                )
                return

            def publish():
                try:
                    placement, definitions, profile, components, bank, program_path, residual = prepared
                    if profile:
                        workspace.apply_prepared_machine_profile(profile, profile_cad)
                    viewer = workspace.machine.gcode_viewer
                    viewer.configure_machine(
                        placement.work_offset_mm,
                        placement.stock_size_mm,
                        placement.stock_origin_mm,
                        stock_rotation_deg=placement.stock_rotation_deg,
                        stock_tilt_deg=placement.stock_tilt_deg,
                        stock_model=placement.stock_model,
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
                    viewer.publish_tool_profiles(prepared_tools)
                    viewer.select_preview_tool(None)
                    workspace.loaded_toolset = bank
                    workspace.loaded_tool_profiles = {}
                    _restore_tool_summaries(workspace, bank, definitions)
                    workspace.restored_job = loaded
                    workspace.machine.file_popup.local_rv.curr_selected_file = str(program_path)
                    workspace.pending_job_rest_stock = (str(program_path), residual) if residual is not None else None
                    workspace.camera_registration_panel.apply_calibration(calibration)
                    issues = []
                    if loaded.report.missing_inventory:
                        issues.append(f"{len(loaded.report.missing_inventory)} tools missing from local inventory")
                    if loaded.report.conflicting_inventory:
                        issues.append(f"{len(loaded.report.conflicting_inventory)} tool definitions conflict")
                    suffix = "\n" + "; ".join(issues) if issues else ""
                    token = object()
                    workspace._job_import_publication = token
                    expected_hash = program_hash

                    def loaded_program(success, message):
                        if (
                            workspace._job_import_generation != generation
                            or getattr(workspace, "_job_import_publication", None) is not token
                        ):
                            return
                        if workspace.app.selected_local_filename != str(program_path):
                            workspace.package_note.text = "Local setup applied · imported program preview superseded."
                            return
                        if success and viewer.loaded_program_hash == expected_hash:
                            workspace.package_note.text = "Restored local preview · physical setup unverified" + suffix
                        else:
                            workspace.package_note.text = (
                                "Local setup applied; program preview failed or was cancelled: "
                                + (message or "Program identity did not match")
                            )

                    workspace.package_note.text = (
                        "Local setup applied · program preview loading; physical setup unverified."
                    )
                    workspace.machine.view_local_file(program_lines=program_lines, on_loaded=loaded_program)
                    return True
                except Exception as exc:
                    logger.exception("Job preview publication failed")
                    workspace.package_note.text = "Assets retained; preview restoration failed: " + (
                        str(exc) or type(exc).__name__
                    )
                    return False

            JobImportReview(workspace, generation, reviewed_context, loaded, prepared, sections, publish)

        if getattr(workspace, "_job_import_active", False):
            workspace._job_import_pending = start
            workspace.package_note.text = "Latest job import queued · current preview retained."
        else:
            start()

    workspace.choose_asset_file(selected, suffixes=(".cvjob",))


def _restore_tool_summaries(workspace, bank, definitions):
    """Refresh imported declarations without selecting/saving a physical toolset."""
    refresh = getattr(workspace, "_restore_profile_status", None)
    if refresh is not None:
        refresh()
        status = getattr(workspace, "profile_status", None)
        if status is not None and bank:
            status.text += f" • {len(definitions)}/6 preview slots"
    summary = getattr(workspace, "tool_library_summary", None)
    if summary is not None:
        summary.text = (
            "\n".join(
                f"T{number}  {tool.description or tool.tool_type.value.replace('_', ' ')} • Ø{tool.diameter:g} mm"
                for number, tool in sorted(definitions.items())
            )
            or "No imported preview tools"
        )
        summary.height = dp(max(56, len(definitions) * 22))


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
    from carveracontroller.addons.machine_simulation.stock_model import StockModel, validate_residual_stock

    stock_model = StockModel.from_reference(stock["stock_source"]) if "stock_source" in stock else None
    placement = MachineSetup(
        tuple(stock.get("work_offset_mm", (-180, -120, -110))),
        tuple(stock["size_mm"]) if stock.get("size_mm") else None,
        tuple(stock.get("origin_mm", (0, 0, 0))),
        False,
        stock.get("rotation_deg", 0),
        stock_model,
        tuple(stock.get("tilt_deg", (0, 0))),
    )
    if stock_model is not None:
        stock_model.prepare_preview(placement, 1)
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
    residual_path = loaded.package.stock.get("residual_stock_path")
    residual = None
    if residual_path:
        from carveracontroller.addons.manufacturing_simulation import StockVolume
        from carveracontroller.machine.job_packages import retained_stock_asset

        raw = retained_stock_asset(loaded, "residual_stock_path", 64 * 1024 * 1024)
        residual = StockVolume.from_snapshot(json.loads(raw))
        validate_residual_stock(placement, residual)
        from carveracontroller.machine.residual_provenance import (
            MAX_CONTEXT_BYTES,
            RetainedResidual,
            decode_provenance,
        )

        context_path = loaded.package.stock.get("residual_context_path")
        context = None
        if context_path:
            payload = retained_stock_asset(loaded, "residual_context_path", MAX_CONTEXT_BYTES)
            context = decode_provenance(payload, loaded.package.program, raw)
        from carveracontroller.machine.simulation_preview import stock_geometry

        geometry = stock_geometry(residual) if context is not None else None
        residual = RetainedResidual(residual, context, geometry)
    return placement, definitions, profile, components, bank, program_path, residual


def restore_pending_residual(workspace):
    """Adopt a prepared grid only after its exact loaded interpretation matches."""
    pending = getattr(workspace, "pending_job_rest_stock", None)
    if (
        not pending
        or workspace.machine.loading_file
        or workspace.machine._last_loaded_file_key != pending[0]
        or not workspace.operation_panel.program
    ):
        return
    from carveracontroller.machine.geometry_changes import capture_context, digest_context
    from carveracontroller.machine.residual_provenance import match_provenance

    workspace.pending_job_rest_stock = None
    panel = workspace.simulation_panel
    try:
        viewer = workspace.machine.gcode_viewer
        retained = pending[1]
        context = capture_context(viewer, workspace.operation_panel.program, verify_assets=False)
        match_provenance(retained.context, context)
        if retained.geometry is None:
            raise ValueError("Residual geometry was not prepared; import again")
        viewer.set_rest_stock_geometry(retained.geometry)
        panel.rest_stock = retained.stock
        panel.rest_identity = context["program"], digest_context(context)
        panel.rest_context = context
        if panel.clearance_inputs is not None:
            panel._invalidate_clearance()
        panel.stock_source.text = "Continue rest stock"
        panel.note.text = "Restored context-matched residual stock · physical setup unverified"
    except ValueError as exc:
        panel.note.text = workspace.package_note.text = "Residual stock not applied: " + str(exc)


def capture_recording_job(workspace, *, include_camera=True):
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
    retained_tools = {
        tool["id"]: copy.deepcopy(tool) for tool in library.get("tools", []) if tool["id"] in selected_ids
    }
    # Individually loaded profiles have no toolset. Retain their source metadata
    # only while it still describes the exact active preview definition.
    from carveracontroller.machine.desktop_profiles import to_tool_definition

    for number, profile in getattr(workspace, "loaded_tool_profiles", {}).items():
        active = viewer.library_tool_table_mm.get(number)
        if active is None:
            continue
        expected = asdict(to_tool_definition(profile, number=number))
        actual = asdict(active)
        for key in ("geometry_sha256", "holder_geometry_sha256"):
            expected.pop(key)
            actual.pop(key)
        if expected == actual:
            retained = copy.deepcopy(profile)
            retained["number"] = number
            retained_tools[retained["id"]] = retained
    job = JobPackage(
        name=path.stem,
        program=b"",
        program_name=path.name,
        machine=copy.deepcopy(workspace.selected_machine_profile or {}),
        tools=list(retained_tools.values()),
        toolsets=[toolset] if toolset else [],
        stock={
            "size_mm": list(setup.stock_size_mm) if setup.stock_size_mm else None,
            "origin_mm": list(setup.stock_origin_mm),
            "rotation_deg": getattr(setup, "stock_rotation_deg", 0),
            **({"tilt_deg": list(setup.stock_tilt_deg)} if any(getattr(setup, "stock_tilt_deg", (0, 0))) else {}),
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
    if include_camera:
        job.camera_calibration = _camera_snapshot(workspace.camera_registration_panel)
    if getattr(setup, "stock_model", None) is not None:
        job.stock["stock_source"] = setup.stock_model.reference
    for value in (job.machine, job.tools, job.fixtures, job.inspection_plan, job.stock):
        _assets(value, job.assets)
    return job


def _camera_snapshot(panel):
    if panel is None or panel.registration is None:
        return None
    if hasattr(panel, "_input_identity") and panel.fit_identity != panel._input_identity():
        raise ValueError("Camera calibration inputs changed; refit before retaining setup")
    return panel.registration, tuple(panel.observations), getattr(panel, "reference", None), panel.reference_machine_y
