import time
from unittest.mock import Mock

import pytest

from carveracontroller import desktop_job_packages as jobs
from tests.integration.conftest import pump_frames


def test_engraver_editor_preserves_length_units_and_degree_half_angle(kivy_app, tmp_path):
    from carveracontroller.desktop_profiles import ProfileLibrary
    from carveracontroller.machine.desktop_profiles import ProfileStore, to_tool_definition

    store = ProfileStore(tmp_path / "editor.json")
    library = ProfileLibrary(kivy_app.root.desktop_workspace, store=store)
    library.select_kind("tools")
    library.new()
    library.fields["name"].text = "Harvey 47645 T4"
    library.fields["shape"].text = next(t for t, s in library.shape_choices.items() if s == "chamfer_mill")
    for key, text in {
        "number": "4",
        "diameter": "1/4 in",
        "shank_diameter": "1/4 in",
        "length": "2.5 in",
        "stickout": "12 mm",
        "tip_diameter": "0.010 in",
        "taper_angle_deg": "45 deg",
    }.items():
        library.fields[key].text = text
    saved = library.save()
    assert saved is not None, library.status.text
    assert saved["tip_diameter"] == pytest.approx(0.254)
    assert saved["taper_angle_deg"] == 45
    from kivy.uix.popup import Popup

    popup = Popup(title="T4 geometry", content=library, size_hint=(0.9, 0.9))
    popup.open()
    pump_frames(8)
    library.fields["tip_diameter"].focus = True
    pump_frames(4)
    assert "0.254 mm" in library.tool_drawing_status.text
    assert library.tool_drawing.radial_label.text == "Tip diameter: 0.254 mm"
    library.fields["tip_diameter"].focus = False
    library.fields["taper_angle_deg"].focus = True
    pump_frames(4)
    assert "45 degrees" in library.tool_drawing_status.text
    assert library.tool_drawing.radial_label.text == "Taper half angle: 45°"
    library.fields["taper_angle_deg"].focus = False
    popup.dismiss()
    metric = to_tool_definition(saved)
    assert metric.tip_diameter == pytest.approx(0.254) and metric.taper_angle_deg == 45


def test_native_job_import_assigns_four_tools_and_preserves_engraver(kivy_app, tmp_path, monkeypatch):
    import hashlib

    from carveracontroller.machine.desktop_profiles import initial_library
    from carveracontroller.machine.job_packages import JobPackage, save_package

    tools = initial_library()["tools"] + [
        {
            "id": "t4",
            "name": "Harvey 47645",
            "number": 4,
            "shape": "chamfer_mill",
            "diameter": 6.35,
            "shank_diameter": 6.35,
            "length": 63.5,
            "stickout": 12,
            "tip_diameter": 0.254,
            "taper_angle_deg": 45,
        }
    ]
    slots = {str(i + 1): t["id"] for i, t in enumerate(tools)}
    text = b"G21 G90 G17 G94\nT4 M6\nG0 X0 Y0 Z15\nG1 X1 Y1 Z0 F150\nM2\n"
    archive = save_package(
        JobPackage(
            "Four tools",
            text,
            program_name="t4.cnc",
            tools=tools,
            toolsets=[{"id": "four", "name": "Four tools", "slots": slots}],
            stock={"size_mm": [25, 40, 12.5], "origin_mm": [0, 0, -12.5], "alignment_confirmed": False},
        ),
        tmp_path / "four.cvjob",
    )
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ws, "choose_asset_file", lambda selected, **_kw: selected(archive))
    command = Mock(side_effect=AssertionError("Job import must not issue machine commands"))
    monkeypatch.setattr(ws.machine.controller, "executeCommand", command)
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    jobs.import_job(ws)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not ws.package_note.text.startswith("Restored local preview"):
        pump_frames(2, sleep=0.01)
    assert ws.package_note.text.startswith("Restored local preview"), ws.package_note.text
    assert ws.loaded_toolset["slots"] == slots
    assert "4/6 preview slots" in ws.profile_status.text
    assert all(f"T{n}  " in ws.tool_library_summary.text for n in (1, 2, 3, 4))
    viewer = ws.machine.gcode_viewer
    assert set(viewer.library_tool_table_mm) == {1, 2, 3, 4}
    assert viewer.library_tool_table_mm[4].tip_diameter == 0.254
    assert viewer.library_tool_table_mm[4].taper_angle_deg == 45
    digest = hashlib.sha256(text).hexdigest()
    while time.monotonic() < deadline and viewer.loaded_program_hash != digest:
        pump_frames(2, sleep=0.01)
    assert viewer.loaded_program_hash == digest
    assert viewer.machine_setup.alignment_confirmed is False
    command.assert_not_called()
