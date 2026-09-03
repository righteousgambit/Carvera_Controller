"""Every setting name a probing .kv references must exist in Python.

The .kv files address settings by attribute name, resolved at runtime with
``getattr(SomeParameterDefinitions, key, None)``. Nothing connects the two at
import time, so renaming a definition silently breaks the screen that uses it
and the failure only appears when a user opens that panel.
"""

import glob
import os
import re

import pytest

_OPS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "carveracontroller", "addons", "probing", "operations")
_SETTING_CALL = re.compile(r"(?:get_setting|setting_changed)\(\s*'([A-Za-z_][A-Za-z0-9_]*)'")


def _kv_files():
    return sorted(glob.glob(os.path.join(_OPS_DIR, "*", "*.kv")))


def _definitions_for(kv_path):
    """Import the ParameterDefinitions class living beside a .kv file.

    Discovered rather than derived from the folder name: the naming is not
    uniform (SingleAxis holds SingleAxisProbeParameterDefinitions).
    """
    import importlib

    folder_path = os.path.dirname(kv_path)
    folder = os.path.basename(folder_path)
    candidates = sorted(glob.glob(os.path.join(folder_path, "*ParameterDefinitions.py")))
    if not candidates:
        pytest.skip(f"no ParameterDefinitions module in {folder}")

    stem = os.path.splitext(os.path.basename(candidates[0]))[0]
    module = importlib.import_module(f"carveracontroller.addons.probing.operations.{folder}.{stem}")
    return getattr(module, stem)


def test_there_are_kv_files_to_check():
    assert _kv_files(), "no probing .kv files found; the glob is wrong"


@pytest.mark.parametrize("kv_path", _kv_files(), ids=lambda p: os.path.basename(p))
def test_every_referenced_setting_exists(kv_path):
    with open(kv_path) as handle:
        referenced = set(_SETTING_CALL.findall(handle.read()))
    if not referenced:
        pytest.skip("no settings referenced")

    definitions = _definitions_for(kv_path)
    missing = sorted(name for name in referenced if getattr(definitions, name, None) is None)

    assert not missing, f"{os.path.basename(kv_path)} references settings that do not exist: {missing}"
