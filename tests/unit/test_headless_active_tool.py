import copy
import json

import pytest

from carveracontroller.headless.active_tool import (
    COMMANDS,
    FALSE,
    ActiveToolReadRefused,
    interpret,
    parse_receipt,
    read_active_tool,
)
from carveracontroller.headless.wire_evidence import ReceiveWindow
from tests.unit import test_headless_link as owning_link

server = owning_link.server
from tests.unit.test_headless_runtime import runtime

TOOL = b"tool:1 ref:-115.340 cur:-85.340 offset:29.999\r\nok T:0\n"
DETAIL = b"current tool offset [-85.340] , reference tool offset [-115.340]\nno one-off tool setter position offsets configured\nusing default Tool setter position: X[-100.000] Y[-200.000] Z[-300.000]\nok\n"


def receipt(command, raw):
    window = ReceiveWindow()
    window.append(raw)
    return {
        "command": command,
        "wire_commands": [command],
        "outcome": "controller_acknowledged",
        "motion_completed": False,
        "connection_id": "one",
        "controller_receive_evidence": window.evidence("one", (command + "\n").encode(), True),
    }


class Link:
    def __init__(self):
        self.calls = []
        self.change = None
        self.transform = None

    def snapshot(self):
        result = {
            "connected": True,
            "connection_id": "one",
            "transfer_active": False,
            "unknown_outcome": False,
            "status_age_ms": 0,
            "diagnostics_age_ms": 0,
            "status": {"state": "Idle", "is_playing": False, "spindle_rpm": 0, "spindle_target_rpm": 0},
            "diagnostics": {"spindle_enabled": False},
        }
        if self.change:
            self.change(result)
        return result

    def command(self, command, **options):
        self.calls.append((command, options))
        result = receipt(command, DETAIL if command == "M493.4" else TOOL)
        if self.transform:
            self.transform(result, len(self.calls))
        return result


def test_fixed_read_preserves_original_tokens_without_inventing_static_table_or_offset_formula():
    link, receipts = Link(), []
    value = read_active_tool(link, receipts)
    assert [x[0] for x in link.calls] == list(COMMANDS)
    assert all(x[1] == {"read_only": True, "timeout": 10} for x in link.calls)
    assert value["reported"]["offset_mm_token"] == "29.999"
    assert value["setter"]["oneoff_mm_tokens"] is None
    assert len(value["command_receipts"]) == 3 and all(value[k] is False for k in FALSE)


@pytest.mark.parametrize(
    "raw",
    [
        TOOL.replace(b"tool:1", b"tool:1.0"),
        TOOL.replace(b"29.999", b"nan"),
        TOOL.replace(b"29.999", b"2.9999e1"),
        TOOL + TOOL,
        TOOL + b"ERROR:1\n",
        TOOL + b"{ERROR:1}\n",
        TOOL[:-1],
        TOOL.replace(b"ok T:0\n", b""),
        TOOL + b"unknown\n",
        b"\n" * 4097,
    ],
)
def test_changed_mixed_duplicate_partial_unknown_original_grammar_refuses(raw):
    with pytest.raises(ValueError):
        parse_receipt(receipt("M499.1", raw), "M499.1", "one")


@pytest.mark.parametrize("fault", ["connection", "planned", "hash", "float-count", "flags", "absent", "budget"])
def test_rehashed_window_contradictions_refuse(fault):
    value = receipt("M499.1", TOOL)
    window = value["controller_receive_evidence"]
    if fault == "connection":
        value["connection_id"] = "other"
    if fault == "planned":
        window["planned_command_bytes_base64"] = "TTQ5My4zXG4="
    if fault == "hash":
        window["sha256"] = "0" * 64
    if fault == "float-count":
        window["byte_count"] = float(window["byte_count"])
    if fault == "flags":
        window["execution_authorized"] = True
    if fault == "absent":
        window["original_bytes_retained"] = False
    if fault == "budget":
        window["budget_bytes"] = 4096
    with pytest.raises(ActiveToolReadRefused):
        parse_receipt(value, "M499.1", "one")


@pytest.mark.parametrize(
    "fault",
    ["connected", "transfer_active", "unknown_outcome", "status_age_ms", "diagnostics_age_ms", "running", "spindle"],
)
def test_unsettled_controller_refuses_before_read(fault):
    link = Link()

    def change(v):
        if fault == "connected":
            v[fault] = False
        elif fault in ("transfer_active", "unknown_outcome"):
            v[fault] = True
        elif fault.endswith("age_ms"):
            v[fault] = 5001
        elif fault == "running":
            v["status"]["state"] = "Run"
        else:
            v["diagnostics"]["spindle_enabled"] = True

    link.change = change
    with pytest.raises(ActiveToolReadRefused):
        read_active_tool(link, [])
    assert not link.calls


def test_changed_tool_during_fixed_reads_retains_three_originals_and_refuses():
    link, records = Link(), []

    def transform(value, count):
        if count == 3:
            value.update(receipt("M499.1", TOOL.replace(b"tool:1", b"tool:2")))

    link.transform = transform
    with pytest.raises(ActiveToolReadRefused):
        read_active_tool(link, records)
    assert len(records) == 3


def test_configured_oneoff_and_setter_have_explicit_original_tokens():
    raw = DETAIL.replace(
        b"no one-off tool setter position offsets configured",
        b"one-off tool setter position offsets: X[0.000] Y[-0.000] Z[1.250]",
    ).replace(b"using default Tool setter position", b"Tool setter position (MCS)")
    result = interpret(raw, "M493.4")
    assert result["setter_kind"] == "configured" and result["oneoff_mm_tokens"] == ["0.000", "-0.000", "1.250"]


@pytest.mark.parametrize("params", [None, {"command": "M493.3 Z9"}])
def test_private_read_rpc_has_no_arbitrary_command_parameters(params):
    request = {"id": "one", "method": "active_tool_read"}
    if params is not None:
        request["params"] = params
    value = runtime((json.dumps(request) + "\n").encode())[-1]
    assert value["ok"] is False
    assert value["error"] == ("active_tool_read_refused" if params is None else "ValueError")


def test_actual_socket_reader_sends_only_fixed_commands_and_retains_windows(server):
    import base64

    from tests.unit.test_headless_link import line

    status = b"<Idle|MPos:-232,-195,-3|WPos:0,0,20|S:0,0,100|P:0,0,0,0>\n{S:0}\n"
    commands = []

    def handle(sock):
        sock.sendall(status)
        for expected in COMMANDS:
            command = line(sock).decode().strip()
            commands.append(command)
            assert command == expected
            sock.sendall(status + (DETAIL if command == "M493.4" else TOOL))
        assert sock.recv(1) == b""

    link = server(handle)
    with link._condition:
        assert link._condition.wait_for(lambda: link.snapshot()["diagnostics_age_ms"] is not None, timeout=3)
    result = read_active_tool(link, [])
    assert commands == list(COMMANDS)
    for record in result["command_receipts"]:
        assert b"tool" in base64.b64decode(record["controller_receive_evidence"]["original_bytes_base64"])
    assert result["active_offsets_authenticated"] is False
