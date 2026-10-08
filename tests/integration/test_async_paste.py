import threading
import time

import pytest
from kivy.clock import Clock
from kivy.uix.modalview import ModalView

from carveracontroller import desktop_components as components
from tests.integration.conftest import pump_frames


@pytest.fixture
def paste_field(kivy_app, monkeypatch):
    monkeypatch.setattr(components.sys, "platform", "darwin")
    field = components.Field(text="before selected after")
    dialog = ModalView(size_hint=(0.6, 0.3))
    dialog.add_widget(field)
    dialog.open(animation=False)
    pump_frames(3)
    field.focus = True
    field.select_text(7, 15)
    pump_frames(3)
    yield field
    dialog.dismiss(animation=False)
    pump_frames(3)


def complete(field):
    for _ in range(30):
        pump_frames(1, sleep=0.01)
        if not field.paste_pending:
            return
    pytest.fail("paste completion was not delivered")


def test_pending_read_does_not_block_clock_and_preserves_selection_undo(paste_field, monkeypatch):
    release, entered = threading.Event(), threading.Event()

    def read(cancel):
        entered.set()
        assert release.wait(2)
        return "new\ntext"

    monkeypatch.setattr(components, "read_text", read)
    started = time.monotonic()
    paste_field.paste()
    assert time.monotonic() - started < 0.1
    assert entered.wait(0.5)
    ticks = []
    Clock.schedule_once(lambda dt: ticks.append(dt), 0)
    pump_frames(3)
    assert ticks and paste_field.paste_pending
    assert paste_field.text == "before selected after"
    release.set()
    complete(paste_field)
    assert paste_field.text == "before new text after"
    paste_field.do_undo()
    paste_field.do_undo()
    assert paste_field.text == "before selected after"


@pytest.mark.parametrize(
    "change", ["text", "cursor", "focus", "disabled", "readonly", "selection", "detached", "hidden"]
)
def test_late_result_does_not_edit_changed_field(paste_field, monkeypatch, change):
    release = threading.Event()

    def read(cancel):
        assert release.wait(2)
        return "unexpected"

    monkeypatch.setattr(components, "read_text", read)
    paste_field.paste()
    if change == "selection":
        paste_field.select_text(0, 6)
    elif change == "detached":
        paste_field.parent.remove_widget(paste_field)
    elif change == "hidden":
        paste_field.opacity = 0
    else:
        setattr(
            paste_field,
            change,
            {"text": "user edit", "cursor": (0, 0), "focus": False, "disabled": True, "readonly": True}[change],
        )
    expected = paste_field.text
    release.set()
    pump_frames(8, sleep=0.01)
    assert paste_field.text == expected and not paste_field.paste_pending


def test_superseded_read_cannot_replace_newer_paste(paste_field, monkeypatch):
    first_release, first_entered = threading.Event(), threading.Event()
    calls = []

    def read(cancel):
        calls.append(cancel)
        if len(calls) == 1:
            first_entered.set()
            assert first_release.wait(2)
            return "old"
        return "latest"

    monkeypatch.setattr(components, "read_text", read)
    paste_field.paste()
    assert first_entered.wait(0.5)
    paste_field.paste()
    complete(paste_field)
    assert paste_field.text == "before latest after"
    first_release.set()
    pump_frames(5, sleep=0.01)
    assert paste_field.text == "before latest after" and calls[0].is_set()


def test_read_failure_leaves_selection_and_text_intact(paste_field, monkeypatch):
    def read(cancel):
        raise components.ClipboardReadError("Clipboard timed out; try paste again.")

    monkeypatch.setattr(components, "read_text", read)
    paste_field.paste()
    complete(paste_field)
    assert paste_field.text == "before selected after"
    assert paste_field.selection_text == "selected"
    assert "timed out" in paste_field.paste_error
