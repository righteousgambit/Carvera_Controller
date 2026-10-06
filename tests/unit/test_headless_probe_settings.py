import base64

import pytest

from carveracontroller.headless.probe_settings import (
    KEYS,
    READ_COMMANDS,
    ProbeSettingsReadRefused,
    parse_receipt,
    read_settings,
)
from carveracontroller.headless.wire_evidence import ReceiveWindow
from tests.unit import test_headless_link as owning_link

line = owning_link.line
server = owning_link.server


def receipt(key=KEYS[0], token="2.0000", *, raw=None):
    command = f"config-get sd {key}"
    body = raw if raw is not None else f"sd: {key} is set to {token}\r\nok\n".encode()
    window = ReceiveWindow()
    window.append(body)
    return {
        "command": command,
        "outcome": "controller_acknowledged",
        "connection_id": "one",
        "motion_completed": False,
        "wire_commands": [command, "M105"],
        "controller_receive_evidence": window.evidence("one", f"{command}\nM105\n".encode(), True),
    }


@pytest.mark.parametrize(
    "key,token,value",
    [
        (KEYS[0], "2.0000", 2),
        (KEYS[1], "-0.1250", -0.125),
        (KEYS[1], "0.0000", 0),
        (KEYS[1], "-0.0000", 0),
        (KEYS[1], "1e-4", 0.0001),
    ],
)
def test_original_numeric_tokens_survive_reported_sd_readback(key, token, value):
    assert parse_receipt(receipt(key, token), key, "one") == {
        "state": "reported",
        "value_mm": value,
        "original_numeric_token": token,
    }


@pytest.mark.parametrize("raw", [b"sd: zprobe.probe_tip_diameter is not in config\r\nok\n"])
def test_missing_setting_is_explicit_not_zero(raw):
    assert parse_receipt(receipt(raw=raw), KEYS[0], "one") == {
        "state": "missing",
        "value_mm": None,
        "original_numeric_token": None,
    }


@pytest.mark.parametrize(
    "line_text",
    [
        "cached: zprobe.probe_tip_diameter is set to 2",
        "sd: wlan.password is set to private",
        "sd: zprobe.probe_tip_diameter is set to nan",
        "sd: zprobe.probe_tip_diameter is set to 0",
        "sd: zprobe.probe_tip_diameter is set to 501",
        "sd: zprobe.probe_tip_diameter is set to 2 # extra",
        "sd: zprobe.probe_tip_diameter is set to 2\nsd: zprobe.probe_tip_diameter is set to 2",
        "sd: zprobe.probe_tip_diameter is set to 2\nERROR: write failed",
        "sd: zprobe.probe_tip_diameter is set to 2\nok T:ERROR",
        "sd: zprobe.probe_tip_diameter is set to 2\n<malformed>",
    ],
)
def test_rehashed_mixed_duplicate_error_or_unpinned_grammar_refuses(line_text):
    with pytest.raises(ProbeSettingsReadRefused):
        parse_receipt(receipt(raw=(line_text + "\nok\n").encode()), KEYS[0], "one")


@pytest.mark.parametrize(
    "change",
    ["hash", "size", "float-size", "planned", "identity", "physical", "original-absent", "partial", "over-budget"],
)
def test_original_window_binding_refuses_normalized_or_changed_custody(change):
    r = receipt()
    w = r["controller_receive_evidence"]
    if change == "hash":
        w["sha256"] = "0" * 64
    elif change == "size":
        w["byte_count"] += 1
    elif change == "float-size":
        w["byte_count"] = float(w["byte_count"])
    elif change == "planned":
        w["planned_command_bytes_base64"] = base64.b64encode(b"config-get sd wlan.password\nM105\n").decode()
    elif change == "identity":
        w["connection_id"] = "retired"
    elif change == "physical":
        w["physical_accuracy_verified"] = True
    elif change == "original-absent":
        w["original_bytes_retained"] = False
    elif change == "partial":
        r = receipt(raw=b"sd: zprobe.probe_tip_diameter is set to 2\nok")
    elif change == "over-budget":
        r = receipt(raw=b"\n" * 4097)
    with pytest.raises(ProbeSettingsReadRefused):
        parse_receipt(r, KEYS[0], "one")


class FakeLink:
    def __init__(self):
        self.connection = "one"
        self.calls = []
        self.receipts = [receipt(), receipt(KEYS[1], "-0.1250")]

    def snapshot(self):
        return {"connected": True, "connection_id": self.connection, "transfer_active": False, "unknown_outcome": False}

    def command(self, command, **kw):
        self.calls.append((command, kw))
        return self.receipts[len(self.calls) - 1]


def test_read_only_pair_keeps_original_receipts_and_never_claims_active_tlo():
    link = FakeLink()
    records = []
    result = read_settings(link, records)
    assert [x[0] for x in link.calls] == list(READ_COMMANDS)
    assert all(kw == {"read_only": True, "timeout": 10} for _, kw in link.calls)
    assert result["command_receipts"] == records and len(records) == 2
    assert all(
        result[key] is False
        for key in [
            "active_settings_verified",
            "persistence_verified",
            "firmware_identity_verified",
            "physical_accuracy_verified",
            "execution_authorized",
        ]
    )
    assert result["settings"][KEYS[1]]["original_numeric_token"] == "-0.1250"


def test_retired_connection_or_changed_second_window_preserves_first_and_no_retry():
    link = FakeLink()
    link.receipts[1]["controller_receive_evidence"]["sha256"] = "0" * 64
    records = []
    with pytest.raises(ProbeSettingsReadRefused):
        read_settings(link, records)
    assert len(link.calls) == 2 and len(records) == 2
    link = FakeLink()
    original = link.command

    def changed(*args, **kwargs):
        r = original(*args, **kwargs)
        link.connection = "other"
        return r

    link.command = changed
    records = []
    with pytest.raises(ProbeSettingsReadRefused):
        read_settings(link, records)
    assert len(link.calls) == 1 and len(records) == 1


def test_actual_link_fixed_key_queries_preserve_original_controller_windows(server):
    wire = []

    def handle(sock):
        for key, token in zip(KEYS, ["2.0000", "-0.1250"]):
            wire.extend([line(sock), line(sock)])
            sock.sendall(f"sd: {key} is set to {token}\r\nok T:0\n".encode())
        assert sock.recv(1) == b""

    link = server(handle)
    records = []
    result = read_settings(link, records)
    assert wire == [f"{command}\n".encode() for query in READ_COMMANDS for command in [query, "M105"]]
    assert len(records) == 2 and result["settings"][KEYS[1]]["value_mm"] == -0.125
    for record in records:
        assert base64.b64decode(record["controller_receive_evidence"]["original_bytes_base64"]).startswith(
            b"sd: zprobe."
        )


def test_readonly_whitelist_does_not_enable_generic_config_or_writes(server):
    def handle(sock):
        assert sock.recv(1) == b""

    link = server(handle)
    for command in ["config-get-all -e", "config-get sd wlan.password", "config-set sd zprobe.probe_tip_diameter 2"]:
        with pytest.raises(ValueError):
            link.command(command, read_only=True)


@pytest.mark.parametrize(
    "params,expected_error", [({}, "probe_settings_read_refused"), ({"key": "wifi.password"}, "ValueError")]
)
def test_private_rpc_fixed_reader_refuses_disconnected_or_arbitrary_parameters(params, expected_error):
    import json
    import select
    import subprocess
    import sys

    process = subprocess.Popen(
        [sys.executable, "-m", "carveracontroller.headless", "--host", "127.0.0.1", "--port", "2222"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 5)[0], "private ready deadline"
        assert json.loads(process.stdout.readline())["event"] == "ready"
        process.stdin.write(json.dumps({"id": "fixed-read", "method": "probe_profile_read", "params": params}) + "\n")
        process.stdin.flush()
        assert select.select([process.stdout], [], [], 5)[0], "private reply deadline"
        reply = json.loads(process.stdout.readline())
        assert reply["id"] == "fixed-read"
        assert reply["ok"] is False
        assert reply["error"] == expected_error
        if not params:
            assert reply["completed_command_receipts"] == []
        process.stdin.close()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
