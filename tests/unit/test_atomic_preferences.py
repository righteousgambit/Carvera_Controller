"""Preference commit never truncates the prior file on preparation failure."""

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from carveracontroller.machine import atomic_preferences as prefs


def test_atomic_replace_retains_mode_and_checks_revision(tmp_path):
    path = tmp_path / "config.ini"
    path.write_bytes(b"old")
    path.chmod(0o640)
    prefs.replace_preferences(path, b"old", b"new")
    assert path.read_bytes() == b"new"
    assert path.stat().st_mode & 0o777 == 0o640
    with pytest.raises(ValueError, match="changed"):
        prefs.replace_preferences(path, b"old", b"other")
    assert path.read_bytes() == b"new"
    assert not list(tmp_path.glob(".carvera-preferences-*"))


@pytest.mark.parametrize("fault", ["fsync", "replace"])
def test_write_failure_preserves_old_file(tmp_path, monkeypatch, fault):
    path = tmp_path / "config.ini"
    path.write_bytes(b"old")
    monkeypatch.setattr(os, fault, Mock(side_effect=OSError("injected write fault")))
    with pytest.raises(OSError):
        prefs.replace_preferences(path, b"old", b"new")
    assert path.read_bytes() == b"old"
    assert not list(tmp_path.glob(".carvera-preferences-*"))


def test_intervening_write_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "config.ini"
    path.write_bytes(b"old")
    original = os.fsync

    def change(fd):
        original(fd)
        path.write_bytes(b"external")

    monkeypatch.setattr(os, "fsync", change)
    with pytest.raises(ValueError, match="changed"):
        prefs.replace_preferences(path, b"old", b"new")
    assert path.read_bytes() == b"external"


def test_linked_target_is_rejected_and_new_file_is_supported(tmp_path):
    target = tmp_path / "real"
    target.write_bytes(b"retained")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        prefs.replace_preferences(link, b"retained", b"new")
    assert target.read_bytes() == b"retained"
    new = tmp_path / "new.ini"
    prefs.replace_preferences(new, None, b"new")
    assert new.read_bytes() == b"new"
