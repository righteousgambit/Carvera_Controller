import json
import subprocess
import sys


def runtime(payload):
    process = subprocess.run(
        [sys.executable, "-m", "carveracontroller.headless", "--host", "127.0.0.1", "--port", "2222"],
        input=payload,
        capture_output=True,
        timeout=5,
        check=True,
    )
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_private_rpc_reports_real_disconnected_state_without_loading_kivy():
    messages = runtime(b'{"id":"one","method":"snapshot"}\n')
    assert messages[0]["runtime_version"] == "carvera.headless.v1"
    assert messages[0]["connection_owned"] is False
    assert messages[1]["id"] == "one"
    assert messages[1]["result"]["status"] is None
    assert messages[1]["result"]["connected"] is False


def test_duplicate_request_identity_terminates_without_replaying():
    messages = runtime(b'{"id":"one","method":"snapshot"}\n' * 2)
    assert len([value for value in messages if value.get("id") == "one"]) == 1
    assert messages[-1] == {"event": "protocol_error", "error": "invalid_request"}


def test_unknown_method_is_not_an_arbitrary_shell_entrypoint():
    messages = runtime(b'{"id":"one","method":"shell","params":{"command":"whoami"}}\n')
    assert messages[-1] == {"id": "one", "ok": False, "error": "invalid_method"}


def test_probe_compilation_keeps_stdout_a_json_only_protocol():
    messages = runtime(
        b'{"id":"one","method":"compile","params":{"operation":"probe.operation","parameters":{"variant":"single_axis.WorkpieceTop","values":{"Z":5,"D":3,"I":0,"S":0}}}}\n'
    )
    assert messages[1]["ok"] is True
    assert "Z-5.0" in messages[1]["result"]["commands"][2]
