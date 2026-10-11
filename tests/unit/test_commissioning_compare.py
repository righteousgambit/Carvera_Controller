from dataclasses import replace
from types import SimpleNamespace

import pytest

from carveracontroller.machine.commissioning_compare import difference_page, hal_differences
from carveracontroller.machine.linuxcnc_hal import HalItem, LinuxCNCHalReader
from tests.unit.test_linuxcnc_hal import make_capture, parameter_module


def samples():
    before = LinuxCNCHalReader("mill", parameter_module()).poll(10)
    after = replace(
        before,
        observed_at=11,
        sequence=2,
        parameters=(
            HalItem("pid.0.Pgain", "float", 150.5, "rw", None),
            HalItem("new.limit", "s32", 8, "ro", None),
        ),
    )
    return before, after


def test_reference_differences_preserve_values_additions_removals_and_raw_delta():
    before, after = samples()
    changes, note = hal_differences(before, after, "HAL parameters")
    assert [(x.name, x.change) for x in changes] == [
        ("new.limit", "added"),
        ("pid.0.Pgain", "value changed"),
        ("servo-thread.time", "removed"),
    ]
    assert "raw delta +30.0" in changes[1].summary()
    assert "120.5" in changes[1].detail() and "150.5" in changes[1].detail()
    assert "independent" in note
    assert len(hal_differences(before, after, "HAL parameters", "PID rw changed")[0]) == 1
    assert not hal_differences(before, before, "HAL parameters")[0]


@pytest.mark.parametrize("mutation", [{"parameters": None}, {"generation": 1}, {"machine_id": "other"}])
def test_unavailable_or_different_identity_never_looks_like_added_removed(mutation):
    before, after = samples()
    changes, note = hal_differences(before, replace(after, **mutation), "HAL parameters")
    assert not changes and "unavailable" in note


def test_metadata_changes_do_not_subtract_incompatible_types_and_overflow_is_explicit():
    before, after = samples()
    after = replace(after, parameters=(HalItem("pid.0.Pgain", "u32", 150, "rw", None),))
    changes, _ = hal_differences(before, after, "HAL parameters")
    gain = next(x for x in changes if x.name == "pid.0.Pgain")
    assert gain.change == "metadata changed" and "delta" not in gain.summary()
    assert "float" in gain.detail() and "u32" in gain.detail()
    before = replace(before, parameters=(HalItem("huge", "float", -1e308, "rw", None),))
    after = replace(after, parameters=(HalItem("huge", "float", 1e308, "rw", None),))
    assert "exceeds finite" in hal_differences(before, after, "HAL parameters")[0][0].summary()


def test_comparison_pages_cover_all_changed_entries():
    before, after = samples()
    before = replace(before, parameters=())
    after = replace(after, parameters=tuple(HalItem(f"p.{i:04}", "s32", i, "rw", None) for i in range(4096)))
    changes, _ = hal_differences(before, after, "HAL parameters")
    names = []
    for i in range(256):
        page = difference_page(changes, i)
        assert len(page.rows) == 16
        names.extend(name for name, _ in page.rows)
    assert names == [p.name for p in after.parameters]
    with pytest.raises(ValueError):
        hal_differences(before, after, "HAL parameters", "x" * 257)
    with pytest.raises(ValueError):
        difference_page(changes, True)


@pytest.mark.parametrize("width", [360, 650])
def test_mounted_reference_tracks_navigation_resets_on_import_and_clear(tmp_path, width):
    from kivy.clock import Clock
    from kivy.uix.floatlayout import FloatLayout

    from carveracontroller.desktop_commissioning import CommissioningPanel
    from carveracontroller.machine.commissioning_capture import load_capture

    capture = load_capture(make_capture(tmp_path, parameter_module()))
    before, after = samples()
    capture = replace(capture, hal_observations=(before, after))
    panel = CommissioningPanel(SimpleNamespace())
    root = FloatLayout(size_hint=(None, None), size=(width, 2000))
    root.add_widget(panel)
    panel.width = width
    try:
        panel.deliver(0, capture, None)
        panel.channel_choice.text = "HAL parameters"
        panel.hal_mode.text = "Changed since reference"
        assert "No matching changes" in panel.channel_values.text
        panel.move(1)
        assert "Reference sample 1" in panel.reference_note.text
        assert "raw delta +30.0" in panel.channel_values.text
        panel.hal_selected.text = "pid.0.Pgain"
        assert "Reference: float" in panel.hal_detail.text
        panel.set_reference()
        assert "Reference sample 2" in panel.reference_note.text
        assert panel.reference_button.disabled
        assert "No matching changes" in panel.channel_values.text
        panel.move(0)
        assert "raw delta -30.0" in panel.channel_values.text
        panel.hal_search.text = "x" * 257
        panel.render_channels()
        assert panel.hal_selected.disabled and not panel.hal_detail.text
        panel.hal_search.text = "Pgain"
        panel.render_channels()
        assert tuple(panel.hal_selected.values) == ("pid.0.Pgain",)
        panel.deliver(
            0,
            replace(
                capture,
                observations=capture.observations[:1],
                utc_times=capture.utc_times[:1],
                hal_observations=(before,),
            ),
            None,
        )
        assert panel.cursor == panel.reference_cursor == 0
        assert panel.hal_mode.text == "Recorded values"
        for _ in range(3):
            Clock.tick()
        panel.clear()
        assert panel.capture is None and panel.reference_cursor == 0
    finally:
        panel.clear()
        root.remove_widget(panel)
