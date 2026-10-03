from types import SimpleNamespace

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.desktop_job_packages import capture_job
from carveracontroller.desktop_operations import OperationPanel
from carveracontroller.machine.job_packages import load_package, save_package
from carveracontroller.machine.program_operations import ProgramOperations


def test_capture_preserves_program_stock_vise_and_component_assets(tmp_path):
    program = tmp_path / "part.nc"
    program.write_bytes(b"G21\r\nG90\r\n")
    cad = tmp_path / "fixture.json.gz"
    cad.write_bytes(b"fixture bytes")
    viewer = SimpleNamespace(
        machine_setup=MachineSetup((-180, -120, -110), (10, 20, 30), (-10, -20, 0)),
        machine_component_profiles={"fixture": SimpleNamespace(asset_path=str(cad))},
        workholding_offset_mm=(-70, -40, 0),
        workholding_rotation_deg=90,
        jaw_offset_mm=-74,
    )
    workspace = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(program)),
        machine=SimpleNamespace(gcode_viewer=viewer),
        profile_store=None,
        selected_machine_profile=None,
        loaded_toolset=None,
    )
    package = capture_job(workspace)
    assert package.program == program.read_bytes()
    assert package.stock["size_mm"] == [10, 20, 30]
    assert package.stock["alignment_confirmed"] is False
    assert package.vise["rotation_deg"] == 90
    archive = tmp_path / "part.cvjob"
    save_package(package, archive)
    restored = load_package(archive, destination=tmp_path / "restored")
    assert restored.package.fixtures[0]["cad_path"].startswith("asset://")
    assert next(iter(restored.asset_paths.values())).read_bytes() == b"fixture bytes"


def test_capture_rejects_component_without_source(tmp_path):
    program = tmp_path / "part.nc"
    program.write_text("G21")
    viewer = SimpleNamespace(machine_setup=MachineSetup(), machine_component_profiles={"workholding": object()})
    workspace = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(program)),
        machine=SimpleNamespace(gcode_viewer=viewer),
        profile_store=None,
    )
    with pytest.raises(ValueError, match="source asset"):
        capture_job(workspace)


def test_operation_selection_seeks_preview_without_controller():
    calls = []
    viewer = SimpleNamespace(set_distance_by_lineidx=lambda *args: calls.append(args))
    panel = OperationPanel(SimpleNamespace(machine=SimpleNamespace(gcode_viewer=viewer)))
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\n(Operation: Face)\nG1 X0 Y0 Z0 F100\nG1 X10\n")
    panel.generation = 1
    panel._loaded(1, program, None)
    operation = program.operations[-1]
    panel.select(operation)
    assert calls == [(operation.start_line, 0)]
    assert operation.name in panel.detail.text
    assert "Slot 1" in panel.banks.text
    panel._loaded(0, None, "stale failure")
    assert panel.program is program
