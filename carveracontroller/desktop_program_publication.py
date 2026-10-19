"""Publish a complete local program; retain the prior program model on failure."""

import copy
import logging
import time
from dataclasses import asdict

from carveracontroller.CNC import CNC
from carveracontroller.desktop_program_preparation import PreparedProgramPreview
from carveracontroller.machine.job_program_validation import PreviewParserInputs
from carveracontroller.machine.program_render_preparation import MARGIN_KEYS

logger = logging.getLogger(__name__)
_MISSING = object()
ROOT_FIELDS = (
    "lines",
    "selected_file_line_count",
    "upcoming_tool",
    "file_has_ocodes",
    "used_tools",
    "tool_change_markers",
    "tool_table",
    "document_unit",
    "_loading_program_hash",
    "_last_loaded_file_key",
    "gcode_cannot_visualise",
    "gcode_viewer_distance",
    "file_just_loaded",
    "gcode_playing",
    "load_canceled",
    "loading_file",
    "path_show_rapid",
    "path_show_feed",
    "path_speed_bits",
    "path_z_bits",
    "path_hidden_tools",
)
APP_FIELDS = (
    "selected_local_filename",
    "selected_remote_filename",
    "total_pages",
    "curr_page",
    "loading_page",
    "has_4axis",
)


def _capture(obj, fields):
    return {key: getattr(obj, key, _MISSING) for key in fields}


def _restore(obj, values):
    for key, value in values.items():
        if value is _MISSING:
            if hasattr(obj, key):
                delattr(obj, key)
        else:
            setattr(obj, key, value)


def publish_program_preview(machine, app, filepath, prepared, *, on_loaded=None):
    if not isinstance(prepared, PreparedProgramPreview) or str(filepath) != prepared.manifest.local_path:
        raise ValueError("Program preparation does not match the selected local path")
    current_inputs = PreviewParserInputs.declarations(CNC.vars, inch=CNC.inch, accuracy=CNC.accuracy)
    if current_inputs != asdict(prepared.program.inputs):
        raise ValueError("Renderer inputs changed after program preparation; prepare again")
    if prepared.manifest.parsed_lines_sha256 != prepared.program.source_hash:
        raise ValueError("Prepared program and manifest identities differ")
    if machine.loading_file:
        raise ValueError("Another program preview is still loading")
    if machine.gcode_viewer.library_tool_table_mm != prepared.tool_profiles[0]:
        raise ValueError("Prepared cutter definitions are not the current local preview tools")
    viewer = machine.gcode_viewer
    previous = viewer.capture_program_display()
    root_values, app_values = _capture(machine, ROOT_FIELDS), _capture(app, APP_FIELDS)
    viewer_values = _capture(viewer, ("tool_table", "tool_unit_scale", "dynamic_display"))
    parser_values = dict(vars(machine.cnc))
    margins = {key: CNC.vars.get(key, _MISSING) for key in MARGIN_KEYS}
    rows = list(machine.gcode_rv.data)
    row_count = machine.gcode_rv.data_length
    coord = getattr(machine, "coord_popup", None)
    coord_live_config = coord.config if coord is not None else None
    coord_config = copy.deepcopy(coord_live_config)
    resume = (coord.cbx_startline.active, coord.txt_startline.text) if coord is not None else None
    controls = []
    manager = getattr(machine, "cmd_manager", None)
    for control, fields in (
        (getattr(manager, "transition", None), ("direction",)),
        (manager, ("current",)),
        (machine.gcode_rv, ("scroll_y",)),
        (getattr(machine, "gcode_play_slider", None), ("value",)),
    ):
        if control is not None:
            controls.append((control, _capture(control, fields)))
    playbar = getattr(machine, "wpb_play", None)
    if playbar is not None:
        controls.append((playbar, {"tool_markers": list(playbar.tool_markers)}))
    machine.program_preview_generation += 1  # Never rewind cancellation generations during recovery.
    try:
        machine.loading_file = True
        if manager is not None:
            manager.transition.direction = "right"
            manager.current = "gcode_cmd_page"
        machine.load_canceled = False
        machine.lines = list(prepared.program.lines)
        machine.selected_file_line_count = len(machine.lines)
        machine.cnc.__dict__.update(prepared.program.parser_state)
        machine.cnc.coordinates = []
        CNC.vars.update(prepared.program.margins)
        machine.upcoming_tool = prepared.program.upcoming_tool
        machine.file_has_ocodes = prepared.program.file_has_ocodes
        machine.used_tools = list(prepared.program.used_tools)
        machine.tool_change_markers = list(prepared.program.tool_change_markers)
        machine.tool_table = prepared.tool_table
        machine.document_unit = prepared.document_unit
        machine._loading_program_hash = prepared.program.source_hash
        machine.gcode_cannot_visualise = False
        machine.gcode_playing = False
        viewer.tool_table = prepared.tool_table
        viewer.tool_unit_scale = prepared.tool_unit_scale
        viewer.dynamic_display = False
        app.selected_local_filename, app.selected_remote_filename = str(filepath), ""
        page_size = machine.program_source_page_size()
        app.total_pages = (len(machine.lines) + page_size - 1) // page_size
        machine.init_path_visibility()
        viewer.publish_prepared_program(prepared.manager, prepared.tool_profiles[2:4])
        machine.gcode_viewer_distance = viewer.get_total_distance()
        machine.load_page(1)
        machine.load_end(0)
        if viewer.loaded_program_hash != prepared.program.source_hash:
            raise ValueError("Prepared program renderer did not publish its expected identity")
        # The final observer consumes the retained manifest, not the staging file.
        machine.controller.publish_prepared_program_source(prepared.manifest)
        machine.heartbeat_time = time.time()
    except Exception:
        _restore(machine, root_values)
        _restore(app, app_values)
        _restore(viewer, viewer_values)
        machine.cnc.__dict__.clear()
        machine.cnc.__dict__.update(parser_values)
        for key, value in margins.items():
            if value is _MISSING:
                CNC.vars.pop(key, None)
            else:
                CNC.vars[key] = value
        machine.gcode_rv.data, machine.gcode_rv.data_length = rows, row_count
        try:
            if coord is not None:
                # CoordPopup, the execution setup and workspace share this map.
                # Preserve its identity rather than splitting UI and execution state.
                coord_live_config.clear()
                coord_live_config.update(coord_config)
                coord.config = coord_live_config
                coord.load_config()
                coord.cbx_startline.active, coord.txt_startline.text = resume
            viewer.restore_program_display(previous)
            machine._push_path_visibility()
        except Exception:
            viewer.meshmanager = previous["manager"]
            viewer.set_loaded_program_identity(None)
            logger.exception("Previous program display recovery failed; retained model is available")
        for control, values in controls:
            try:
                _restore(control, values)
            except Exception:
                viewer.set_loaded_program_identity(None)
                logger.exception("Previous program control recovery failed; identity withheld")
        raise
    finally:
        machine.loading_file = False
    if on_loaded is not None:
        try:
            on_loaded(True, "")
        except Exception:
            logger.exception("Program was committed; completion observer failed")
    return True
