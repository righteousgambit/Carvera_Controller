from carveracontroller.machine.program_dependencies import describe_dependencies
from carveracontroller.machine.program_preview import inspect_program


def test_candidate_dependencies_use_captured_tools_and_local_declarations(tmp_path):
    path = tmp_path / "candidate.nc"
    path.write_text("G21 G54\nT8 M6\nG55\nT99\n")
    report = describe_dependencies(
        inspect_program(path),
        available_tools={8: object()},
        profile_name="Workshop",
        toolset_name="Roughing",
        stock_size_mm=(100, 50, 20),
        alignment_confirmed=True,
    )
    assert report.missing_tools == (99,)
    assert "Active parsed tools: T8" in report.text
    assert "Preselected only: T99" in report.text
    assert "P1: T8" in report.text and "P2: T99" not in report.text
    assert "registered transform" in report.text
    assert "100 × 50 × 20 mm" in report.text
    assert "physical tools, offsets, travel and clearance remain unchecked" in report.text


def test_empty_declarations_are_unknown_not_ready(tmp_path):
    path = tmp_path / "candidate.nc"
    path.write_text("G21\nT4\n")
    report = describe_dependencies(inspect_program(path))
    assert report.missing_tools == (4,)
    assert "Not selected" in report.text and "Stock declaration: Missing" in report.text
    assert "No active tool-bank sequence resolved" in report.text


def test_requirements_keep_complete_ids_while_display_is_bounded(tmp_path):
    path = tmp_path / "many.nc"
    path.write_text("G21\n" + "\n".join(f"T{tool} M6" for tool in range(1, 101)))
    report = describe_dependencies(inspect_program(path))
    assert report.missing_tools == tuple(range(1, 101))
    assert "(100 tools)" in report.text
    assert "Further banks omitted" in report.text
    assert "Motion bounds unavailable" in report.text
