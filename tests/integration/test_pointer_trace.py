"""Trace observers must stay bounded, disposable and non-consuming."""

from types import SimpleNamespace
from unittest.mock import Mock

from kivy.base import EventLoop
from kivy.core.window import Window
from kivy.input.providers.mouse import MouseMotionEventProvider

from carveracontroller.desktop_pointer_trace import PointerTrace
from tests.integration.conftest import pump_frames
from tests.integration.test_stage_pointer_routing import system_position


def test_pointer_trace_limit_detaches_and_never_consumes():
    window = SimpleNamespace(bind=Mock(), unbind=Mock(), size=(640, 360), system_size=(320, 180))
    clock = SimpleNamespace(create_trigger=lambda callback, delay: lambda: callback(0), schedule_once=Mock())
    change = Mock()
    trace = PointerTrace({}, change, window, clock)
    trace.start()
    trace.start()
    window.bind.assert_called_once()
    for i in range(128):
        assert trace.record("touch move", (i, 5), "left") is False
    assert not trace.active and len(trace.events) == 128
    window.unbind.assert_called_once()
    assert "128-event limit" in trace.summary()
    assert trace.record("touch move", (129, 5)) is False
    assert len(trace.events) == 128
    trace.start()
    assert not trace.events
    callback = clock.schedule_once.call_args.args[0]
    callback(30)
    assert not trace.active and "30-second" in trace.reason


def test_window_trace_observes_input_without_changing_reference_or_machine(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    ws.select("Camera")
    panel = ws.camera_registration_panel
    panel.select_section("Reference")
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    pump_frames(10)
    provider = MouseMotionEventProvider("trace-pointer", "multitouch_on_demand")
    trace = panel.pointer_trace
    image = panel.reference_view
    image.focus = False
    try:
        provider.start()
        panel._toggle_pointer_trace()
        position = system_position(image.to_window(*image.center))
        for event in ("on_mouse_down", "on_mouse_up"):
            Window.dispatch(event, *position, "left", [])
            provider.update(EventLoop.post_dispatch_input)
            pump_frames(3)
        assert any(e["route"] == "raw down" for e in trace.events)
        assert any(e["route"] == "touch down" and "reference" in e["panes"] for e in trace.events)
        assert "Window" in panel.pointer_note.text
        panel.select_section("Fit & exchange")
        assert not trace.active
        before = len(trace.events)
        Window.dispatch("on_mouse_down", *position, "scrollup", [])
        assert len(trace.events) == before
        panel.select_section("Reference")
        trace.start()
        ws.select("Job")
        assert not trace.active and trace.reason == "Camera workbench left"
        send.assert_not_called()
    finally:
        trace.stop()
        provider.stop()
        image.focus = False
