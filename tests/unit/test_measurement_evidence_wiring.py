"""Exercise production Machine callbacks without starting or moving a machine."""

import ast
import logging
from pathlib import Path
from types import SimpleNamespace

from carveracontroller.machine.console_watcher import ConsoleWatcher
from carveracontroller.machine.probe_evidence import ProbeEvidenceStore
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_history import ToolHistory


def machine_callbacks(tmp_path):
    source = ast.parse(Path("carveracontroller/main.py").read_text())
    wanted = {
        "console_watcher",
        "_watch_console_line",
        "_on_probe_result",
        "_on_tlo_report",
        "probe_evidence",
        "_measurement_context",
        "_measurement_declarations_snapshot",
        "_available_sensor_text",
        "_current_sensor_report",
        "_status_measurement_available",
        "_sensor_measurement_command",
    }
    original = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "Makera")
    selected = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace = {
        "ConsoleWatcher": ConsoleWatcher,
        "CNC": SimpleNamespace(vars={"tool": 1}),
        "logger": logging.getLogger("measurement-wiring"),
        "tr": SimpleNamespace(_=lambda text: text),
    }
    cls = ast.ClassDef(name="Callbacks", bases=[], keywords=[], body=selected, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, "production-machine-callbacks", "exec"), namespace)
    machine = namespace["Callbacks"]()
    machine.controller = SimpleNamespace(
        connection_address="local-test",
        run_evidence=SimpleNamespace(latest={"tool": 1}),
        sensor_context_snapshot=lambda: {
            "tool": 1,
            "wcs": "G54",
            "spindle_temperature": 30.5,
            "program": {"sha256": "abc"},
            "field_presence": {},
        },
    )
    machine._probe_evidence = ProbeEvidenceStore(tmp_path / "measurements.jsonl")
    machine.tool_custody = ToolCustodyStore(tmp_path / "custody.json")
    machine.tool_history = ToolHistory()
    machine.usage_counters = SimpleNamespace(count_probe_cycle=lambda: None)
    machine.measurement_declarations = {"probe_identity": "TP06", "seat_revision": "seat-1", "phase": "before_cut"}
    return machine


def test_submitted_command_and_actual_console_callback_persist_probe_session(tmp_path):
    machine = machine_callbacks(tmp_path)
    machine._sensor_measurement_command("M461 X10 F60")
    for line in ("Distance Point 2 X surfaces: 10.020", "#151 = 12.5", "Center Point is: 12.5, 3.0"):
        machine._watch_console_line(line)
    event = machine.probe_evidence.events()[0]
    assert event["result_kind"] == "probe"
    assert event["result"]["x_diameter"] == 10.02
    assert event["context"]["spindle_temperature"] == 30.5
    assert event["context"]["program_sha256"] == "abc"
    assert event["context"]["probe_identity"] == "TP06"
    assert event["context"]["work_offsets"] is None
    assert event["reported_variables"][0]["raw"] == "#151 = 12.5"
    assert not event["raw_hits_available"]
    assert "issued-step" in event["context"]["position_basis"]


def test_setter_callback_keeps_custody_receipt_raw_samples_and_end_context(tmp_path):
    machine = machine_callbacks(tmp_path)
    machine._sensor_measurement_command("M491 R2")
    machine._watch_console_line("TLO value from measurement 1: 1.020")
    machine.measurement_declarations["phase"] = "after_cut"
    machine._watch_console_line("TLO value from measurement 2: 1.021")
    machine._watch_console_line("Max delta: 0.001")
    event = machine.probe_evidence.events()[0]
    assert event["result_kind"] == "setter"
    assert event["result"]["measurements"] == [1.02, 1.021]
    assert event["result"]["custody_receipt_id"] == machine.tool_custody.events[0]["id"]
    assert event["context"]["phase"] == "before_cut"
    assert event["end_context"]["phase"] == "after_cut"


def test_unavailable_sensor_ui_assignments_never_render_cached_values(tmp_path):
    machine = machine_callbacks(tmp_path)
    machine.controller.sensor_context_snapshot = lambda: {
        "arrival_age_s": 0.1,
        "spindle_temperature": 42.5,
        "probe_voltage": 3.91,
    }
    source = ast.parse(Path("carveracontroller/main.py").read_text())
    cnc = SimpleNamespace(
        vars={
            "spindletemp": 42.5,
            "wpvoltage": 3.91,
            "spindle_temperature_available": False,
            "probe_voltage_available": False,
        }
    )
    machine.spindle_drop_down = SimpleNamespace(status_temp=SimpleNamespace(value="cached"))
    machine.tool_drop_down = SimpleNamespace(status_wpvoltage=SimpleNamespace(value="cached"))
    machine.tool_data_view = SimpleNamespace(minr_text="cached")
    assignments = [
        node
        for node in ast.walk(source)
        if isinstance(node, ast.Assign)
        and any(word in ast.unparse(node) for word in ("status_temp.value", "status_wpvoltage.value"))
    ]
    # Execute the actual production assignment expressions with availability false.
    namespace = {"self": machine, "CNC": cnc}
    function_globals = machine._available_sensor_text.__func__.__globals__
    function_globals["CNC"] = cnc
    for node in assignments:
        exec(
            compile(
                ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "actual-ui-assignment", "exec"
            ),
            namespace,
        )
    assert machine.spindle_drop_down.status_temp.value == "Unknown"
    assert machine.tool_drop_down.status_wpvoltage.value == "Unknown"
    for key in ("spindle_temperature_available", "probe_voltage_available"):
        cnc.vars[key] = True
    for node in assignments:
        exec(
            compile(
                ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "actual-ui-assignment", "exec"
            ),
            namespace,
        )
    assert machine.spindle_drop_down.status_temp.value == "42.5°C"
    assert machine.tool_drop_down.status_wpvoltage.value == "3.91v"
    # Every alternating WP top-bar branch uses the same availability helper.
    voltage_lines = [
        ast.unparse(node)
        for node in ast.walk(source)
        if isinstance(node, ast.Assign) and "wpvoltage" in ast.unparse(node)
    ]
    assert len(voltage_lines) == 4
    assert all("_available_sensor_text" in line for line in voltage_lines)


def test_zero_sensor_and_invalid_spindle_tool_status_semantics(tmp_path):
    machine = machine_callbacks(tmp_path)
    cnc = machine._available_sensor_text.__func__.__globals__["CNC"]
    context = {"arrival_age_s": 0.1, "spindle_temperature": 0.0}
    machine.controller.sensor_context_snapshot = lambda: context
    cnc.vars.update(spindletemp=0.0, spindle_temperature_available=False)
    assert machine._available_sensor_text("spindletemp", "spindle_temperature_available", 1, "°C") == "Unknown"
    cnc.vars["spindle_temperature_available"] = True
    assert machine._available_sensor_text("spindletemp", "spindle_temperature_available", 1, "°C") == "0.0°C"
    cnc.vars["spindletemp"] = float("nan")
    context["spindle_temperature"] = float("nan")
    assert machine._available_sensor_text("spindletemp", "spindle_temperature_available", 1, "°C") == "Unknown"
    context.update(
        {
            "raw_fields": {"S": [1000, 1000]},
            "field_validity": {"spindle_status": False, "tool_status": False},
            "tool": 1,
            "tlo": 1.0,
        }
    )
    assert not machine._status_measurement_available("spindle_status")
    assert not machine._status_measurement_available("tool_status")
    context["field_validity"] = {}
    assert machine._status_measurement_available("spindle_status")
    assert machine._status_measurement_available("tool_status")


def test_legacy_sensor_widgets_withhold_stale_missing_or_reacquiring_reports(tmp_path):
    machine = machine_callbacks(tmp_path)
    cnc = machine._available_sensor_text.__func__.__globals__["CNC"]
    cnc.vars.update(spindletemp=99, spindle_temperature_available=True, wpvoltage=9, probe_voltage_available=True)
    context = {
        "arrival_age_s": 0.1,
        "spindle_temperature": 30,
        "probe_voltage": 3.3,
        "raw_fields": {"S": [1000, 1000]},
        "tool": 1,
        "tlo": 30,
    }
    machine.controller.sensor_context_snapshot = lambda: context
    assert machine._available_sensor_text("spindletemp", "spindle_temperature_available", 1) == "30.0"
    assert machine._status_measurement_available("spindle_status")
    for age in (None, -1, 0.81, float("nan"), True):
        context["arrival_age_s"] = age
        assert machine._available_sensor_text("spindletemp", "spindle_temperature_available", 1) == "Unknown"
        assert not machine._status_measurement_available("spindle_status")
        assert not machine._status_measurement_available("tool_status")
    context["arrival_age_s"] = 0.1
    machine.controller.status_reacquisition_pending = True
    assert not machine._status_measurement_available("spindle_status")
    machine.controller.status_reacquisition_pending = False
    context.pop("probe_voltage")
    assert machine._available_sensor_text("wpvoltage", "probe_voltage_available", 2) == "Unknown"
