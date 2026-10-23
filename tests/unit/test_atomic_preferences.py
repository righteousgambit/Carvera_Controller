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


def test_merge_uses_retained_file_instead_of_stale_unrelated_cache():
    from configparser import ConfigParser

    retained = b"[carvera]\ninvert_y=external\n[external_review]\nretained=preserve-me\npercent=50%\nmultiline=first\n second\n"
    baseline = b"[carvera]\ninvert_y=stale\n[unrelated_cache_only]\nnot_in_file=no\n"
    encoded = prefs.merge_preference_updates(retained, baseline, {"desktop_machine_profile_id": "imported"})
    parsed = ConfigParser(interpolation=None)
    parsed.read_string(encoded.decode())
    assert parsed.get("carvera", "invert_y") == "external"
    assert parsed.get("carvera", "desktop_machine_profile_id") == "imported"
    assert parsed.get("external_review", "retained") == "preserve-me"
    assert parsed.get("external_review", "percent") == "50%"
    assert parsed.get("external_review", "multiline") == "first\nsecond"
    assert not parsed.has_section("unrelated_cache_only")


def test_absent_preferences_are_explicitly_seeded():
    from configparser import ConfigParser

    encoded = prefs.merge_preference_updates(None, b"[ui]\nzoom=2\n", {"desktop_machine_profile_id": "imported"})
    parsed = ConfigParser(interpolation=None)
    parsed.read_string(encoded.decode())
    assert parsed.get("ui", "zoom") == "2"
    assert parsed.get("carvera", "desktop_machine_profile_id") == "imported"


@pytest.mark.parametrize("raw", [b"not an INI section", b"\xff", b"[ui]\nx=1\nx=2\n"])
def test_invalid_retained_preferences_are_not_silently_replaced(raw):
    from configparser import Error

    with pytest.raises((Error, UnicodeError)):
        prefs.merge_preference_updates(raw, b"[ui]\nx=valid\n", {"desktop_machine_profile_id": "imported"})
