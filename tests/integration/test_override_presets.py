"""Feed and spindle override presets.

One tap to 80 / 100 / 120 rather than dragging a slider mid-cut, or holding
a plus button. The presets drive the same slider the existing controls do, so
whatever the slider is bound to still happens.
"""

import pytest


@pytest.fixture
def dropdowns(kivy_app):
    return kivy_app.root.feed_drop_down, kivy_app.root.spindle_drop_down


def _preset_buttons(dropdown):
    """Pressable widgets in the dropdown whose label is a percentage.

    Restricted to things that fire on_release: the readout labels show
    percentages too, and matching those finds a widget that cannot be pressed.
    """
    found = {}

    def walk(widget):
        for child in widget.children:
            text = getattr(child, "text", "")
            if isinstance(text, str) and text.endswith("%") and child.is_event_type("on_release"):
                found[text] = child
            walk(child)

    walk(dropdown)
    return found


@pytest.mark.parametrize("index", [0, 1])
def test_each_dropdown_offers_the_three_presets(dropdowns, index):
    buttons = _preset_buttons(dropdowns[index])

    assert {"80%", "100%", "120%"} <= set(buttons)


@pytest.mark.parametrize("label,expected", [("80%", 80), ("100%", 100), ("120%", 120)])
def test_pressing_a_preset_sets_the_slider(dropdowns, label, expected):
    for dropdown in dropdowns:
        buttons = _preset_buttons(dropdown)
        dropdown.scale_slider.value = 10
        buttons[label].dispatch("on_release")

        assert dropdown.scale_slider.value == expected


def test_presets_stay_inside_the_slider_range(dropdowns):
    """A preset outside min/max would be silently clamped and confusing."""
    for dropdown in dropdowns:
        slider = dropdown.scale_slider
        for value in (80, 100, 120):
            assert slider.min <= value <= slider.max


def _all_labels(widget):
    labels = []
    for child in widget.children:
        text = getattr(child, "text", "")
        if isinstance(text, str):
            labels.append(text)
        labels.extend(_all_labels(child))
    return labels


def test_the_reset_button_survived_the_change(dropdowns):
    for dropdown in dropdowns:
        assert any("Reset" in label for label in _all_labels(dropdown))
