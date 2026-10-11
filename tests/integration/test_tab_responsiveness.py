"""Workbench navigation keeps immutable CAD out of the UI's hashing path."""

import hashlib
import json
import os
import time
from unittest.mock import Mock

import pytest

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.desktop_bookmarks import capture_bookmark_context, capture_navigation_context
from tests.integration.conftest import pump_frames
from tests.unit.test_machine_profile import profile_data


def test_tab_history_uses_precomputed_geometry_without_weakening_invalidation(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    original = viewer.machine_profile, ws.selected_machine_profile
    data = profile_data()
    profile = MachineProfile(data)
    viewer.machine_profile = profile
    ws.selected_machine_profile = {"id": "tab-test"}
    try:
        canonical = capture_bookmark_context(ws)
        assert profile.geometry_sha256 == hashlib.sha256(profile.geometry_json.encode()).hexdigest()
        fast = capture_navigation_context(ws)
        # Accessing the large string on a click is itself a regression, regardless of CPU speed.
        with monkeypatch.context() as patch:
            patch.setattr(MachineProfile, "geometry_json", property(lambda _self: pytest.fail("CAD read on tab click")))
            assert capture_navigation_context(ws) == fast
            ws.navigation.reset()
            ws.select("Overview")
            ws.select("Console")
            ws.select("Setup")
        assert capture_bookmark_context(ws) == canonical  # Existing saved bookmarks retain their identity.
        data["components"][0]["vertices"][0] = 12
        viewer.machine_profile = MachineProfile(data)
        assert capture_navigation_context(ws) != fast
        assert ws.navigation.navigate(-1) is False
    finally:
        viewer.machine_profile, ws.selected_machine_profile = original
        ws.navigation.reset()
        ws.select("Job", record_navigation=False)


def test_repeated_tab_switches_with_registered_cad(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    original = viewer.machine_profile, ws.selected_machine_profile
    path = os.environ.get("CARVERA_TAB_BENCHMARK_PROFILE")
    profile = MachineProfile.load(path) if path else MachineProfile(profile_data())
    viewer.machine_profile = profile
    ws.selected_machine_profile = {"id": "tab-benchmark"}
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        ws.navigation.reset()
        pump_frames(5)
        timings = []
        for _ in range(3):
            for key, button in ws.tab_buttons.items():
                started = time.perf_counter()
                button.dispatch("on_release")
                callback_ms = (time.perf_counter() - started) * 1000
                pump_frames(2)
                timings.append(
                    {"tab": key, "callback_ms": callback_ms, "two_frames_ms": (time.perf_counter() - started) * 1000}
                )
                assert ws.inspector_pages.current == key
        send.assert_not_called()
        # A generous guard against returning to multi-second synchronous tab work.
        assert max(item["callback_ms"] for item in timings) < 250
        output = os.environ.get("CARVERA_TAB_BENCHMARK_OUTPUT")
        if output:
            from pathlib import Path

            Path(output).write_text(
                json.dumps({"geometry_bytes": len(profile.geometry_json), "switches": timings}, indent=2)
            )
    finally:
        viewer.machine_profile, ws.selected_machine_profile = original
        ws.navigation.reset()
        ws.select("Job", record_navigation=False)
