import pytest

from carveracontroller.machine.operation_highlight import operation_vertex_span


def test_motion_destination_includes_full_first_segment_and_arc_samples():
    lines = [3, 4, 4, 4, 7, 8, 9]
    assert operation_vertex_span(lines, 4, 7) == (2.0, 14.0)
    assert operation_vertex_span(lines, 8, 9) == (14.0, 20.0)
    assert operation_vertex_span(lines, 1, 9) == (2.0, 20.0)


def test_empty_non_motion_and_single_point_spans():
    assert operation_vertex_span([], 1, 10) is None
    assert operation_vertex_span([3, 5, 8], 6, 7) is None
    assert operation_vertex_span([3], 1, 3) is None
    assert operation_vertex_span([3, 5], 5, 5) == (2.0, 5.0)


@pytest.mark.parametrize("start,end", [(True, 3), (1, False), (1.0, 3), (0, 3), (3, 2)])
def test_reject_invalid_source_spans(start, end):
    with pytest.raises(ValueError):
        operation_vertex_span([1, 2, 3], start, end)
