"""Real private-child reports reach calibration and bank views under one owner."""

import copy
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from kivy.metrics import dp

from carveracontroller.desktop_calibration_bench import CalibrationBench
from carveracontroller.desktop_components import Action
from carveracontroller.desktop_tool_banks import ToolBankPanel
from carveracontroller.desktop_tool_observation import observe_tool
from carveracontroller.machine.desktop_control_owner import ControlBinding
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.tool_bank_review import BankReviewStore
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport
from tests.integration import test_backend_connection as connection_support
from tests.integration import test_backend_live_report as scene_support
from tests.integration.conftest import pump_frames

backend_connection = connection_support.backend_connection
backend_scene = scene_support.backend_scene


def views(fixture, monkeypatch, tmp_path):
    ws, viewer, backend, machine, methods, gui_send = fixture
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Declared backend cutter", "Collet", 28, "design")
    machine_id = ws.selected_machine_profile["id"]
    endpoint = f"{backend.client.host}:{backend.client.port}"
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=100):
        store.assign(machine_id, 2, assembly["id"])
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=110):
        receipt = store.capture(2, TloReport((47.5, 47.5), 0, 47.5, 110), endpoint)
        store.link(receipt["id"], assembly["id"], "Synthetic operator attribution")
    monkeypatch.setattr(ws.machine, "_tool_custody", store, raising=False)
    monkeypatch.setattr(
        ws,
        "profile_store",
        SimpleNamespace(
            data={"tools": [{"id": "design", "number": 2, "name": "Cutter", "diameter": 6.35, "shank_diameter": 6.35}]},
            generation=0,
        ),
    )
    source = SimpleNamespace(
        workspace=ws,
        selected=2,
        custody=SimpleNamespace(
            store=store, selected_id=assembly["id"], selected=lambda: store.assembly(assembly["id"])
        ),
    )
    bench = CalibrationBench(source)
    banks = ToolBankPanel(SimpleNamespace(workspace=ws), BankReviewStore(tmp_path / "banks.json"))
    banks.load(ProgramOperations.from_text("G21 G90\nT1 M6\nT2 M6"))
    banks.choose(2, assembly["id"])
    assert banks.choices.get(2) == assembly["id"], banks.result.text
    banks.save()
    assert banks.record is not None, banks.result.text
    scene_support.wait_for(lambda: ws.backend_report().current)
    bench.refresh()
    banks.refresh()
    return bench, banks, store


def test_actual_backend_offset_and_endpoint_are_visible_but_never_established_mm(backend_scene, monkeypatch, tmp_path):
    ws, viewer, backend, machine, methods, gui_send = backend_scene
    bench, banks, store = views(backend_scene, monkeypatch, tmp_path)
    before, requests = store.path.read_bytes(), list(methods)
    assert "backend reported T2 offset: 47.5" in bench.observed.text
    assert "firmware units/reference unknown" in bench.observed.text
    assert "within 0.001 mm comparison" not in bench.observed.text
    assert "999" not in bench.observed.text
    row = next(row for row in banks.rows if row["pocket"] == 2)
    assert len(row["controller_applicable"]) == 1, (row["issues"], banks.result.text, row["reports"])
    assert row["offset_status"]["state"] == "unknown"
    assert row["offset_status"]["reported_mm"] is None
    assert "backend raw offset 47.5" in row["offset_status"]["detail"]
    bench.refresh()
    banks.refresh_if_changed()
    assert methods == requests and store.path.read_bytes() == before
    gui_send.assert_not_called()
    for width, columns in ((180, 1), (360, 1), (760, 2)):
        banks.size_hint_x = None
        banks.width = dp(width)
        pump_frames(10)
        assert banks.grid.cols == columns
        assert all(card.height >= card.minimum_height for card in banks.grid.children)
        assert all(
            widget.y >= card.y and widget.top <= card.top for card in banks.grid.children for widget in card.children
        )
        for card in banks.grid.children:
            for button in card.walk(restrict=True):
                if isinstance(button, Action):
                    assert button.texture_size[0] <= button.width, (
                        width,
                        button.text,
                        button.width,
                        button.texture_size,
                    )
        banks.export_to_png(str(tmp_path / f"backend-tool-banks-{width}.png"))
    banks._fit_grid.cancel()


@pytest.mark.parametrize("retire", ["stale", "replaced", "profile", "closed"])
def test_retired_backend_refreshes_both_views_without_inheriting_gui_offsets(
    backend_scene, monkeypatch, tmp_path, retire
):
    ws, viewer, backend, machine, methods, gui_send = backend_scene
    bench, banks, store = views(backend_scene, monkeypatch, tmp_path)
    before = store.path.read_bytes()
    starting_observation = None
    expected_endpoint = f"{backend.client.host}:{backend.client.port}"

    def both_views_have_current_tool():
        nonlocal starting_observation
        bench.refresh()
        banks.refresh_if_changed()
        observation = observe_tool(ws, time.monotonic())
        starting_observation = observation
        row = next((row for row in banks.rows if row["pocket"] == 2), None)
        return (
            observation.backend_selected
            and observation.current
            and observation.tool == 2
            and observation.raw_offset == 47.5
            and observation.endpoint == expected_endpoint
            and banks._signature[-1] == observation.signature
            and "backend reported T2 offset: 47.5" in bench.observed.text
            and row is not None
            and len(row["controller_applicable"]) == 1
        )

    scene_support.wait_for(both_views_have_current_tool)
    assert starting_observation is not None and starting_observation.current
    assert banks._signature[-1] == starting_observation.signature
    assert "backend reported T2 offset: 47.5" in bench.observed.text
    old_signature = banks._signature
    if retire == "stale":
        state = copy.deepcopy(backend.client.snapshot())
        state["last_machine_snapshot_age_s"] = 5
        monkeypatch.setattr(backend.client, "snapshot", lambda: state)
    elif retire == "replaced":
        ws.control_owner.binding = ControlBinding(backend.client.session_id, "other")
    elif retire == "profile":
        monkeypatch.setitem(ws.selected_machine_profile, "host", "127.0.0.2")
    else:
        monkeypatch.setattr(backend, "closed", True)
    bench.refresh()
    banks.refresh_if_changed()
    assert banks._signature != old_signature
    assert "backend offset unavailable" in bench.observed.text and "999" not in bench.observed.text
    assert all(row["offset_status"]["state"] == "unknown" for row in banks.rows)
    assert all(not row["controller_applicable"] for row in banks.rows)
    assert store.path.read_bytes() == before
    gui_send.assert_not_called()
    banks._fit_grid.cancel()
