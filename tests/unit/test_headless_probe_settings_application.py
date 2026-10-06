import copy
import json
import select
import subprocess
import sys

import pytest

from carveracontroller.headless.link import OutcomeUnknown
from carveracontroller.headless.probe_settings import KEYS, ProbeSettingsReadRefused
from carveracontroller.headless.probe_settings_application import (
    VERSION,
    ProbeSettingsApplicationRefused,
    apply_settings,
    compile_application,
    strict_application_request,
)
from carveracontroller.headless.wire_evidence import ReceiveWindow
from tests.unit import test_headless_link as owning_link

server = owning_link.server
line = owning_link.line
STATUS = b"<Idle|MPos:-232,-195,-3|WPos:0,0,20|S:0,0,100|P:0,0,0,0>\n{S:0}\n"


def setting(token):
    return {"state": "reported", "value_mm": float(token), "original_numeric_token": token}


def request():
    return {
        "schema_version": VERSION,
        "connection_id": "one",
        "expected_settings": {KEYS[0]: setting("2.0000"), KEYS[1]: setting("-0.1250")},
        "settings": {KEYS[0]: "2.01", KEYS[1]: "0.0000"},
    }


def receipt(command, text, connection="one"):
    window = ReceiveWindow()
    window.append(text.encode())
    return {
        "command": command,
        "outcome": "controller_acknowledged",
        "connection_id": connection,
        "motion_completed": False,
        "wire_commands": [command, "M105"],
        "controller_receive_evidence": window.evidence(connection, (command + "\nM105\n").encode(), True),
    }


class FakeLink:
    def __init__(self):
        self.values = {KEYS[0]: "2.0000", KEYS[1]: "-0.1250"}
        self.calls = []
        self.change = None
        self.transform = None
        self.fail_write = None
        self.writes = 0

    def snapshot(self):
        value = {
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
            self.change(value)
        return value

    def command(self, command, **kw):
        self.calls.append((command, kw))
        parts = command.split()
        key = parts[2]
        if parts[0] == "config-set":
            self.writes += 1
            if self.fail_write == self.writes:
                raise OutcomeUnknown(
                    "synthetic acknowledgement loss", {"outcome": "unknown_outcome", "command": command}
                )
            self.values[key] = parts[3]
            result = receipt(command, f"sd: {key} has been set to {parts[3]}\r\nok T:0\n")
        elif key in self.values:
            result = receipt(command, f"sd: {key} is set to {self.values[key]}\r\nok T:0\n")
        else:
            result = receipt(command, f"sd: {key} is not in config\r\nok T:0\n")
        if self.transform:
            result = self.transform(result)
        return result


def test_fixed_pair_original_read_compare_write_readback_keeps_active_tlo_false():
    link, records = FakeLink(), []
    result = apply_settings(link, request(), records)
    assert [x[0] for x in link.calls] == [f"config-get sd {k}" for k in KEYS] + [
        f"config-set sd {k} {request()['settings'][k]}" for k in KEYS
    ] + [f"config-get sd {k}" for k in KEYS]
    assert all(kw == {"timeout": 10, "read_only": command.startswith("config-get")} for command, kw in link.calls)
    assert (
        len(records) == 6
        and len(result["before"]["command_receipts"]) == 2
        and len(result["after"]["command_receipts"]) == 2
    )
    assert result["after"]["settings"][KEYS[1]] == setting("0.0000")
    assert result["sd_readback_matches_requested"] is True
    for flag in [
        "active_settings_verified",
        "persistence_verified",
        "firmware_identity_verified",
        "physical_accuracy_verified",
        "execution_authorized",
        "automatic_rollback_performed",
    ]:
        assert result[flag] is False
    # Caller mutation cannot rewrite retained before/after identities.
    records.clear()
    assert len(result["command_receipts"]) == 6


@pytest.mark.parametrize("token", ["0", "-1", "501", "nan", "inf", "1e999", "2\nM3", " 2", "0x2", "2" * 20, 2, True])
def test_invalid_requested_tip_refuses_before_io(token):
    params, link = request(), FakeLink()
    params["settings"][KEYS[0]] = token
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, params, [])
    assert link.calls == []


@pytest.mark.parametrize(
    "kind", ["extra", "foreign-key", "wrong-version", "float-bool", "missing-implied-zero", "no-change"]
)
def test_closed_reviewed_baseline_requires_original_tokens_and_explicit_membership(kind):
    params = request()
    if kind == "extra":
        params["execution_authorized"] = True
    elif kind == "foreign-key":
        params["settings"]["wlan.password"] = "2"
    elif kind == "wrong-version":
        params["schema_version"] = "historical"
    elif kind == "float-bool":
        params["expected_settings"][KEYS[0]]["value_mm"] = True
    elif kind == "missing-implied-zero":
        params["expected_settings"][KEYS[1]] = {"state": "missing", "value_mm": 0, "original_numeric_token": None}
    else:
        params["settings"] = {k: params["expected_settings"][k]["original_numeric_token"] for k in KEYS}
    with pytest.raises(ProbeSettingsApplicationRefused):
        compile_application(params)


@pytest.mark.parametrize(
    "field,value",
    [
        ("connected", False),
        ("connection_id", "retired"),
        ("transfer_active", True),
        ("unknown_outcome", True),
        ("status_age_ms", 2001),
        ("status_age_ms", True),
        ("diagnostics_age_ms", None),
    ],
)
def test_changed_or_stale_connection_refuses_before_any_io(field, value):
    link = FakeLink()
    link.change = lambda s: s.update({field: value})
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, request(), [])
    assert link.calls == []


@pytest.mark.parametrize(
    "field,value",
    [("state", "Run"), ("is_playing", True), ("spindle_rpm", 1), ("spindle_target_rpm", 12000), ("spindle_rpm", False)],
)
def test_reported_machine_is_stopped_before_writes(field, value):
    link = FakeLink()
    link.change = lambda s: s["status"].update({field: value})
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, request(), [])
    assert link.calls == []


def test_changed_reviewed_sd_values_refuse_after_original_reads_before_write():
    link, records = FakeLink(), []
    link.values[KEYS[0]] = "2.0"
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, request(), records)
    assert len(records) == 2 and link.writes == 0


def test_missing_baseline_remains_explicit_and_zero_is_not_missing():
    link, params = FakeLink(), request()
    del link.values[KEYS[1]]
    params["expected_settings"][KEYS[1]] = {"state": "missing", "value_mm": None, "original_numeric_token": None}
    result = apply_settings(link, params, [])
    assert result["before"]["settings"][KEYS[1]]["state"] == "missing"
    assert result["after"]["settings"][KEYS[1]] == setting("0.0000")


def test_changed_state_after_first_write_preserves_receipt_without_second_write_or_rollback():
    link, records = FakeLink(), []
    link.change = lambda s: s["status"].update({"state": "Run"}) if link.writes else None
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, request(), records)
    assert len(records) == 3 and link.writes == 1
    assert records[-1]["command"].startswith("config-set")


@pytest.mark.parametrize("change", ["echo", "error", "hash", "float-count", "planned", "duplicate"])
def test_original_write_echo_custody_refuses_without_next_write(change):
    link, records = FakeLink(), []

    def transform(r):
        if not r["command"].startswith("config-set"):
            return r
        if change == "echo":
            return receipt(r["command"], f"sd: {KEYS[0]} has been set to 2.010\nok\n")
        if change == "error":
            return receipt(r["command"], f"sd: {KEYS[0]} not enough space to overwrite existing key/value\nok\n")
        if change == "duplicate":
            return receipt(
                r["command"], f"sd: {KEYS[0]} has been set to 2.01\nsd: {KEYS[0]} has been set to 2.01\nok\n"
            )
        w = r["controller_receive_evidence"]
        if change == "hash":
            w["sha256"] = "0" * 64
        elif change == "float-count":
            w["byte_count"] = float(w["byte_count"])
        else:
            w["planned_command_bytes_base64"] = ""
        return r

    link.transform = transform
    with pytest.raises(ProbeSettingsReadRefused):
        apply_settings(link, request(), records)
    assert len(records) == 3 and link.writes == 1


def test_lost_second_write_ack_does_not_retry_or_rollback_and_keeps_prior_receipts():
    link, records = FakeLink(), []
    link.fail_write = 2
    with pytest.raises(OutcomeUnknown) as error:
        apply_settings(link, request(), records)
    assert link.writes == 2 and len(records) == 3
    assert error.value.receipt["outcome"] == "unknown_outcome"
    assert len(link.calls) == 4


def test_original_readback_token_difference_refuses_even_if_numerically_equal():
    link, records = FakeLink(), []

    def transform(r):
        if len(link.calls) == 6:
            return receipt(r["command"], f"sd: {KEYS[1]} is set to 0\nok\n")
        return r

    link.transform = transform
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, request(), records)
    assert link.writes == 2 and len(records) == 6


def test_original_baseline_intent_cannot_be_replayed_after_success():
    link = FakeLink()
    apply_settings(link, request(), [])
    writes = link.writes
    with pytest.raises(ProbeSettingsApplicationRefused):
        apply_settings(link, request(), [])
    assert link.writes == writes


@pytest.mark.parametrize("changed", ["duplicate", "nonfinite", "oversize"])
def test_private_update_request_refuses_original_json_contradictions(changed):
    raw = json.dumps({"id": "reviewed", "method": "probe_profile_apply", "params": request()})
    if changed == "duplicate":
        raw = raw.replace('"schema_version":', '"schema_version":"foreign","schema_version":')
    elif changed == "nonfinite":
        raw = raw.replace('"value_mm": 2.0', '"value_mm": NaN')
    else:
        raw = " " * 8192 + raw
    with pytest.raises(ProbeSettingsApplicationRefused):
        strict_application_request((raw + "\n").encode())


def test_actual_link_original_socket_windows_preserve_fixed_six_command_sequence(server):
    observed = []
    values = {KEYS[0]: "2.0000", KEYS[1]: "-0.1250"}

    def handle(sock):
        sock.sendall(STATUS)
        for _ in range(6):
            command = line(sock).decode().strip()
            observed.append(command)
            assert line(sock) == b"M105\n"
            parts = command.split()
            if parts[0] == "config-set":
                values[parts[2]] = parts[3]
                answer = f"sd: {parts[2]} has been set to {parts[3]}"
            else:
                answer = f"sd: {parts[2]} is set to {values[parts[2]]}"
            sock.sendall(STATUS + answer.encode() + b"\r\nok T:0\n")
        assert sock.recv(1) == b""

    link = server(handle)
    with link._condition:
        assert link._condition.wait_for(lambda: link.snapshot()["diagnostics_age_ms"] is not None, timeout=3)
    params = request()
    params["connection_id"] = link.connection_id
    result = apply_settings(link, params, [])
    assert len(observed) == 6 and len(result["command_receipts"]) == 6
    assert result["active_settings_verified"] is False


def test_private_rpc_application_refuses_disconnected_target_with_no_write_receipts():
    process = subprocess.Popen(
        [sys.executable, "-m", "carveracontroller.headless", "--host", "127.0.0.1"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 5)[0], "private ready deadline"
        assert json.loads(process.stdout.readline())["event"] == "ready"
        process.stdin.write(json.dumps({"id": "reviewed", "method": "probe_profile_apply", "params": request()}) + "\n")
        process.stdin.flush()
        assert select.select([process.stdout], [], [], 5)[0], "private reply deadline"
        reply = json.loads(process.stdout.readline())
        assert reply["ok"] is False and reply["error"] == "probe_settings_application_refused"
        assert reply["completed_command_receipts"] == []
        process.stdin.close()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
