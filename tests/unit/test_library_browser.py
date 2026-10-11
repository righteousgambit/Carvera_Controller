import copy

import pytest

from carveracontroller.machine.library_browser import CutterFilter, browse_profiles
from carveracontroller.machine.quantities import QuantityError


@pytest.fixture
def records():
    return [
        {
            "id": "square",
            "name": "Square",
            "vendor": "Helical",
            "product_id": "03182",
            "shape": "flat_end_mill",
            "diameter": 6.35,
            "shank_diameter": 6.35,
            "notes": "Aluminum",
            "geometry_path": "attached.json",
        },
        {
            "id": "ball",
            "name": "Ball",
            "vendor": "Titan",
            "shape": "ball_end_mill",
            "diameter": 3.175,
            "shank_diameter": 6.35,
            "drawing_path": "attached.pdf",
        },
        {
            "id": "large",
            "name": "Large",
            "vendor": "Titan",
            "shape": "ball_end_mill",
            "diameter": 9.525,
            "shank_diameter": 9.525,
        },
    ]


def test_combined_vendor_shape_and_imperial_dimensions(records):
    selected = CutterFilter.from_text(
        vendor="TIT", shape="ball_end_mill", minimum="1/8 in", maximum="1/4 in", shank="1/4 in"
    )
    assert [r["id"] for r in browse_profiles(records, cutter_filter=selected)] == ["ball"]
    assert selected.active


@pytest.mark.parametrize(
    "assets,expected", [("CAD reference", "square"), ("Drawing reference", "ball"), ("Dimensions only", "large")]
)
def test_asset_references_do_not_require_io(records, assets, expected):
    assert [r["id"] for r in browse_profiles(records, cutter_filter=CutterFilter(assets=assets))] == [expected]


@pytest.mark.parametrize(
    "values",
    [
        {"minimum": "1/2 in", "maximum": "1/4 in"},
        {"shank": "nan"},
        {"minimum": "0"},
        {"maximum": "-1"},
        {"assets": "verified CAD"},
    ],
)
def test_invalid_filters_rejected(values):
    with pytest.raises(QuantityError):
        CutterFilter.from_text(**values)


def test_multiword_search_sort_and_input_immutability(records):
    before = copy.deepcopy(records)
    assert [r["id"] for r in browse_profiles(records, "helical ALUMINUM 03182")] == ["square"]
    assert [r["id"] for r in browse_profiles(records, sort="Diameter")] == ["ball", "square", "large"]
    assert records == before
    assert browse_profiles(records)[0] is records[1]


def test_exact_shank_tolerance_excludes_other_collet_size(records):
    selected = CutterFilter.from_text(shank="6.3500005 mm")
    assert len(browse_profiles(records, cutter_filter=selected)) == 2
    selected = CutterFilter.from_text(shank="6.4 mm")
    assert not browse_profiles(records, cutter_filter=selected)


@pytest.mark.parametrize("dimension", [float("nan"), float("inf"), -1, 0, True, "6.35", None])
def test_unknown_dimensions_never_match_ranges_and_sort_after_known_values(dimension):
    unknown = {"id": "unknown", "name": "Unknown", "diameter": dimension, "shank_diameter": dimension}
    valid = {"id": "valid", "name": "Valid", "diameter": 6.35, "shank_diameter": 6.35}
    records = [unknown, valid]
    assert browse_profiles(records, cutter_filter=CutterFilter(minimum=1, maximum=10, shank=6.35)) == [valid]
    assert browse_profiles(records, sort="Diameter") == [valid, unknown]
    assert browse_profiles(records, sort="Diameter")[1] is unknown


def test_filter_summary_lists_every_active_constraint_in_normalized_mm():
    selected = CutterFilter.from_text(
        shape="ball_end_mill",
        vendor="Titan",
        minimum="1/8 in",
        maximum="1/4 in",
        shank="1/4 in",
        assets="CAD reference",
    )
    assert selected.summary == "ball end mill · Vendor: Titan · Diameter 3.175–6.35 mm · Shank 6.35 mm · CAD reference"
    assert CutterFilter().summary == ""
    assert CutterFilter(minimum=2).summary == "Diameter at least 2 mm"
    assert CutterFilter(maximum=5).summary == "Diameter at most 5 mm"


@pytest.mark.parametrize(
    "values", [{"minimum": float("nan")}, {"shank": True}, {"minimum": 5, "maximum": 2}, {"assets": "verified CAD"}]
)
def test_direct_filter_construction_cannot_bypass_validation(values):
    with pytest.raises(QuantityError):
        CutterFilter(**values)
