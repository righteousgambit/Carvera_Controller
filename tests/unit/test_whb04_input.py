"""Tests for defensive WHB04 input packet handling."""

import struct

import pytest

from carveracontroller.addons.pendant import whb04


@pytest.mark.parametrize(
    ("valid_button", "unknown_first"),
    [
        (whb04.Button.STOP, False),
        (whb04.Button.STOP, True),
        (whb04.Button.RESET, False),
        (whb04.Button.RESET, True),
    ],
)
def test_unknown_button_does_not_drop_valid_button_from_same_packet(valid_button, unknown_first):
    daemon = whb04.Daemon()
    pressed = []
    daemon.on_button_press = lambda _daemon, button: pressed.append(button)
    button1, button2 = (0xFF, valid_button.value) if unknown_first else (valid_button.value, 0xFF)
    packet = struct.pack(
        "BBBBBBbB",
        0x04,
        0,
        button1,
        button2,
        whb04.StepSize.LEAD.value,
        whb04.Axis.OFF.value,
        0,
        0,
    )

    daemon._process_input_packet(packet)

    assert pressed == [valid_button]
    assert daemon.pressed_buttons == {valid_button}


@pytest.mark.parametrize("clear_handler", [False, True])
def test_queued_input_resolves_current_handler_without_calling_none(clear_handler):
    queued = []
    daemon = whb04.Daemon(queued.append)
    old_events, new_events = [], []
    daemon.on_button_press = lambda _daemon, button: old_events.append(button)
    packet = struct.pack(
        "BBBBBBbB",
        0x04,
        0,
        whb04.Button.STOP.value,
        0,
        whb04.StepSize.LEAD.value,
        whb04.Axis.OFF.value,
        0,
        0,
    )
    daemon._process_input_packet(packet)
    assert len(queued) == 1 and old_events == []
    daemon.on_button_press = None if clear_handler else lambda _daemon, button: new_events.append(button)
    queued.pop()()
    assert old_events == []
    assert new_events == ([] if clear_handler else [whb04.Button.STOP])


@pytest.mark.parametrize("mode", [whb04.StepIndicator.MPG, whb04.StepIndicator.PERCENT])
def test_unsupported_distance_mode_has_explicit_error(mode):
    daemon = whb04.Daemon()
    daemon.set_display_step_indicator(mode)
    with pytest.raises(ValueError, match="Step distance is unavailable"):
        _ = daemon.step_size_value
