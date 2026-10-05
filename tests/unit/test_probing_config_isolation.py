"""Probe settings honor the same isolated home as controller test/build runs."""

import json
import os
import subprocess
import sys


def test_probe_config_uses_explicit_kivy_home_without_touching_operator_home(tmp_path):
    operator = tmp_path / "operator"
    isolated = tmp_path / "isolated"
    operator.mkdir()
    environment = dict(os.environ, HOME=str(operator), KIVY_HOME=str(isolated))
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from carveracontroller.addons.probing.operations.ConfigUtils import ConfigUtils; "
            "ConfigUtils.save_config({'D': '4.25'}, 'probe.json'); "
            "assert ConfigUtils.load_config('probe.json') == {'D': '4.25'}",
        ],
        env=environment,
        check=True,
        capture_output=True,
    )
    assert json.loads((isolated / "probe.json").read_text()) == {"D": "4.25"}
    assert not (operator / ".kivy").exists()
    assert not list(operator.rglob("probe.json"))


def test_probe_config_retains_default_home_when_override_absent(tmp_path):
    environment = dict(os.environ, HOME=str(tmp_path))
    environment.pop("KIVY_HOME", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from carveracontroller.addons.probing.operations.ConfigUtils import ConfigUtils; "
            "print(ConfigUtils.CONFIG_DIR)",
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip().rstrip("/") == str(tmp_path / ".kivy")
