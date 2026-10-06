from unittest.mock import Mock

from carveracontroller.machine.tool_custody import ToolCustodyStore

from .conftest import pump_frames


def setup_panel(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    store = ToolCustodyStore(tmp_path / "custody.json")
    monkeypatch.setattr(ws.machine, "_tool_custody", store, raising=False)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    a = store.create_assembly("Physical ball A")
    b = store.create_assembly("Replacement ball B")
    panel = ws.tool_comparison.custody
    panel.selected_id = a["id"]
    panel.refresh(force=True)
    panel.passport_section.text = "Lifecycle"
    assert a["id"][:8] in panel.choice.text
    return panel, store, a, b, send


def evidence(panel):
    panel.lifecycle_time.text = "2026-01-01T12:00:00Z"
    panel.lifecycle_source.text = "DEMO ONLY source record"
    panel.lifecycle_note.text = "DEMO ONLY observation"


def test_attributed_use_inspection_and_replacement_dialogs(kivy_app, monkeypatch, tmp_path):
    panel, store, a, b, send = setup_panel(kivy_app, monkeypatch, tmp_path)
    assert {w.text for w in panel.actions.children} == {
        "Record cutting use",
        "Record inspection",
        "Declare replacement",
        "View lifecycle",
    }
    panel.record_use()
    evidence(panel)
    panel.use_minutes.text = "3/2"
    panel.use_material.text = "6061"
    panel.use_reference.text = "DEMO job/interval-1"
    panel.popup_apply()
    pump_frames(20, sleep=0.01)
    assert store.lifecycle_events(a["id"])[0]["seconds"] == 90
    panel.record_inspection()
    evidence(panel)
    panel.inspection_method.text = "micrometer"
    panel.inspection_condition.text = "monitor"
    panel.inspection_diameter.text = "1/4 in"
    panel.popup_apply()
    pump_frames(20, sleep=0.01)
    assert store.lifecycle_events(a["id"])[-1]["measured_diameter_mm"] == 6.35
    panel.record_replacement()
    evidence(panel)
    panel.lifecycle_time.text = "2026-01-01T13:00:00Z"
    panel.replacement_choice.text = next(
        title for title in panel.replacement_choice.values if title.startswith("Replacement ball B")
    )
    panel.popup_apply()
    pump_frames(20, sleep=0.01)
    assert store.lifecycle_events(a["id"])[-1]["replacement_id"] == b["id"]
    assert panel.lifecycle_buttons[2].disabled and panel.assign_button.disabled
    panel.selected_id = b["id"]
    panel.refresh(force=True)
    assert "0 minutes" in panel.summary.text and "Replaces:" in panel.summary.text
    assert not send.called


def test_rejected_and_cancelled_drafts_preserve_evidence(kivy_app, monkeypatch, tmp_path):
    panel, store, a, b, send = setup_panel(kivy_app, monkeypatch, tmp_path)
    panel.record_use()
    evidence(panel)
    panel.use_minutes.text = "2"
    panel.use_material.text = "6061"
    panel.use_reference.text = "demo"
    before = store.path.read_bytes()
    panel.popup.dismiss()
    assert store.path.read_bytes() == before
    panel.record_use()
    evidence(panel)
    panel.use_minutes.text = "2"
    panel.use_material.text = "6061"
    panel.use_reference.text = "demo"
    other = ToolCustodyStore(store.path)
    other.revise(a["id"], a["id"], "A reseated", note="Changed seating")
    before = store.path.read_bytes()
    panel.popup_apply()
    pump_frames(20, sleep=0.01)
    assert store.path.read_bytes() == before
    assert panel.popup.parent is not None
    assert panel.selected()["revision_count"] == 2
    panel.popup.dismiss()
    assert not send.called


def test_lifecycle_history_and_compact_form_layout(kivy_app, monkeypatch, tmp_path):
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout

    from carveracontroller.desktop_components import Action, DesktopScrollView

    panel, store, a, b, send = setup_panel(kivy_app, monkeypatch, tmp_path)
    for i in range(43):
        store.record_use(
            a["id"],
            a["id"],
            seconds=60,
            material="6061",
            reference=f"interval-{i}",
            source="demo",
            note="demo",
            occurred_at=100 + i,
        )
    panel.show_lifecycle()
    pump_frames(8)
    following = next(w for w in panel.popup.content.walk() if isinstance(w, Action) and w.text == "Older receipts")
    following.dispatch("on_release")
    assert panel.lifecycle_page == 1
    following.dispatch("on_release")
    assert panel.lifecycle_page == 2 and following.disabled
    panel.popup.dismiss()
    viewport = DesktopScrollView(size=(dp(340), dp(500)), size_hint=(None, None), do_scroll_x=False)
    body = BoxLayout(orientation="vertical", size_hint_y=None)
    body.bind(minimum_height=body.setter("height"))
    body.add_widget(panel)
    viewport.add_widget(body)
    try:
        pump_frames(10)
        baseline = panel.height
        panel.passport_section.text = "Overview"
        pump_frames(10)
        panel.passport_section.text = "Lifecycle"
        pump_frames(10)
        assert panel.height == baseline
        panel.export_to_png(str(tmp_path / "lifecycle-compact.png"))
        panel.record_inspection()
        panel.popup.size_hint_x = None
        panel.popup.width = dp(360)
        pump_frames(12)
        assert panel.inspection_diameter.width <= dp(360)
        panel.popup.export_to_png(str(tmp_path / "inspection-compact.png"))
        scroll = next(w for w in panel.popup.content.walk() if isinstance(w, DesktopScrollView))
        scroll.scroll_y = 0
        pump_frames(8)
        panel.popup.export_to_png(str(tmp_path / "inspection-compact-bottom.png"))
        panel.popup.dismiss()
    finally:
        body.remove_widget(panel)
    assert not send.called


def test_background_save_keeps_original_owner_and_rejects_double_submit(kivy_app, monkeypatch, tmp_path):
    import threading

    panel, store, a, b, send = setup_panel(kivy_app, monkeypatch, tmp_path)
    original = store.record_use
    entered, proceed = threading.Event(), threading.Event()

    def slow_save(*args, **kwargs):
        entered.set()
        assert proceed.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "record_use", slow_save)
    panel.record_use()
    evidence(panel)
    panel.use_minutes.text = "1"
    panel.use_material.text = "6061"
    panel.use_reference.text = "background-interval"
    panel.popup_apply()
    assert entered.wait(2)
    panel.popup_apply()  # The saving state cannot issue a duplicate transaction.
    other = ToolCustodyStore(tmp_path / "other-custody.json")
    monkeypatch.setattr(panel.comparison.workspace.machine, "_tool_custody", other)
    panel.selected_id = None
    panel.result.text = "New machine context"
    # Event loop remains available while the disk writer is deliberately held.
    pump_frames(8)
    assert not store.lifecycle_events(a["id"])
    proceed.set()
    pump_frames(25, sleep=0.01)
    assert len(store.lifecycle_events(a["id"])) == 1
    assert other.events == []
    assert panel.result.text == "New machine context"
    assert not send.called


def test_long_form_scrollbar_drag_reaches_last_field(kivy_app, monkeypatch, tmp_path):
    from kivy.tests.common import UnitTestTouch

    from carveracontroller.desktop_components import DesktopScrollView

    panel, store, a, b, send = setup_panel(kivy_app, monkeypatch, tmp_path)
    panel.record_use()
    panel.popup.size_hint_x = None
    panel.popup.width = 720
    panel.popup.height = 520
    pump_frames(12)
    scroll = next(w for w in panel.popup.content.walk() if isinstance(w, DesktopScrollView))
    assert scroll._viewport.height > scroll.height
    x, y = scroll.to_window(scroll.right - scroll.bar_width / 2, scroll.top - 12)
    touch = UnitTestTouch(x, y)
    try:
        touch.touch_down()
        pump_frames(2)
        before = scroll.scroll_y
        touch.touch_move(x, y - scroll.height * 0.8)
        pump_frames(5)
        touch.touch_up()
        pump_frames(5)
        assert scroll.scroll_y < before
        assert scroll.scroll_y < 0.1
    finally:
        panel.popup.dismiss()
    assert not send.called


def test_long_form_mouse_navigation_reaches_fields_and_stays_out_of_save(kivy_app, monkeypatch, tmp_path):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from carveracontroller.desktop_components import Action, DesktopScrollView

    panel, store, a, b, send = setup_panel(kivy_app, monkeypatch, tmp_path)
    # Unit tests may initialize Window before the integration configuration.
    # Exercise a declared desktop size rather than whichever suite ran first.
    monkeypatch.setattr(Window, "size", (900, 600))
    pump_frames(8)
    before = store.path.read_bytes()
    panel.record_inspection()
    panel.popup.size_hint_x = None
    panel.popup.width = dp(360)
    pump_frames(12)
    scroll = next(w for w in panel.popup.content.walk() if isinstance(w, DesktopScrollView))
    actions = {w.text: w for w in panel.popup.content.walk() if isinstance(w, Action)}
    previous, following = actions["Scroll up"], actions["Scroll down"]
    assert previous.disabled and not following.disabled, (Window.size, dp(1), scroll.size, scroll._viewport.height)
    assert not previous.parent.disabled and previous.parent.height > 0
    assert following.texture_size[0] <= following.width
    panel.lifecycle_note.text = "Unsubmitted inspection draft"
    for _ in range(20):
        if following.disabled:
            break
        following.dispatch("on_release")
        pump_frames(2)
    assert scroll.scroll_y == 0 and following.disabled and not previous.disabled
    panel.popup.export_to_png(str(tmp_path / "inspection-pointer-navigation-bottom.png"))
    assert panel.lifecycle_note.text == "Unsubmitted inspection draft"
    assert store.path.read_bytes() == before
    for _ in range(20):
        if previous.disabled:
            break
        previous.dispatch("on_release")
        pump_frames(2)
    assert scroll.scroll_y == 1 and previous.disabled
    panel.popup.dismiss()
    panel.dialog("Short review", [], None, "Close")
    pump_frames(12)
    actions = {w.text: w for w in panel.popup.content.walk() if isinstance(w, Action)}
    assert actions["Scroll up"].parent.disabled
    assert actions["Scroll up"].parent.height == 0
    panel.popup.dismiss()
    assert not send.called and store.path.read_bytes() == before
