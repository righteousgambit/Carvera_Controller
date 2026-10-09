"""Articulated body editing, continuous review, projections and file readback."""

import json
import threading
import time
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_kinematic_review import KinematicReviewPanel
from tests.integration.conftest import pump_frames


def wait(panel):
    deadline = time.monotonic() + 20
    while panel.running and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel.running


def profile(tmp_path):
    path = tmp_path / "single-rotary.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "name": "Declared rotary enclosure test",
                "tool_chain": [{"name": "C", "kind": "rotary", "axis": [0, 0, 1], "minimum": -720, "maximum": 720}],
            }
        )
    )
    return path


def choose_body(card, name):
    card.choice.text = next(c for c, n in card.choice_names.items() if n == name)


def add_bodies(card):
    card.name_field.text = "Arm"
    card.frame.text = "Spindle after C"
    card.minimum.text = "9, -.1, -.1"
    card.maximum.text = "10, .1, .1"
    card.apply_body()
    choose_body(card, None)
    card.name_field.text = "Fixture"
    card.minimum.text = "-.2, 9.4, -.2"
    card.maximum.text = ".2, 9.6, .2"
    card.apply_body()
    assert len(card.owner.record["collision_bodies"]) == 2


@pytest.mark.parametrize("width", [360, 800])
def test_body_drafts_review_contact_projection_save_and_reimport(kivy_app, monkeypatch, tmp_path, width):
    ws = kivy_app.root.desktop_workspace
    owner = KinematicReviewPanel(ws)
    card = owner.clearance_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    source = profile(tmp_path)
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(source)))
    owner.import_profile()
    wait(owner)
    owner.seeds.text = "0\n360"
    owner.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Articulated clearance", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        card.toggle()
        popup.open()
        add_bodies(card)
        choose_body(card, "Arm")
        card.minimum.text = "9, -.2, -.1"
        choose_body(card, "Fixture")
        card.maximum.text = ".3, 9.6, .2"
        choose_body(card, "Arm")
        assert card.minimum.text == "9, -.2, -.1" and len(card.body_drafts) == 2
        card.review()
        assert not owner.running and "all retained body drafts" in card.note.text
        card.discard_body()
        choose_body(card, "Fixture")
        card.discard_body()
        assert not card.body_drafts
        choose_body(card, "Arm")
        card.minimum.text = "10, 0, 0"
        card.maximum.text = "9, 1, 1"
        previous = owner.record
        card.apply_body()
        assert owner.record is previous and "retained" in card.note.text
        card.discard_body()
        pump_frames(10)
        scroll.scroll_to(card.minimum, animate=False)
        pump_frames(5)
        assert card.minimum.width >= 120
        assert card.minimum.parent.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"joint-clearance-editor-{width}.png"))
        card.tolerance.text = "0.001"
        card.review()
        wait(owner)
        assert card.result is not None, card.note.text
        assert len(card.result.contacts) == 1 and "possible contact" in card.note.text
        assert len(card.plot.geometry) == 2 and card.plot.selected == ("Arm", "Fixture")
        assert "earliest possible interval" in card.details.text
        assert "XY left" in card.projection_note.text
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(10)
        popup.export_to_png(str(tmp_path / f"joint-clearance-result-{width}.png"))
        saved = tmp_path / "saved-geometry.json"
        monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(saved)))
        card.save_profile()
        wait(owner)
        assert "Saved declared geometry" in card.note.text and saved.exists()
        retained = json.loads(saved.read_text())
        assert retained["collision_bodies"][0]["name"] == "Arm"
        choose_body(card, "Arm")
        card.maximum.text = "11, .1, .1"
        card.apply_body()
        assert card.result is None
        monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(saved)))
        owner.import_profile()
        wait(owner)
        assert owner.record == retained and not card.body_drafts
        choose_body(card, "Arm")
        assert card.maximum.text == "10, 0.1, 0.1"
        review_file = tmp_path / "saved-review.cvclearance"
        monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(review_file)))
        owner.seeds.text = "0\n360"
        card.review()
        wait(owner)
        expected = card.result
        card.save_review()
        wait(owner)
        assert review_file.exists() and "Saved clearance review" in card.note.text
        owner.seeds.text = "0\n0"
        assert card.result is None
        monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(review_file)))
        card.load_review()
        wait(owner)
        assert card.result == expected and "Loaded and recomputed" in card.note.text
        assert [float(row) for row in owner.seeds.text.splitlines()] == [0, 360]
        invalid = tmp_path / "invalid.cvclearance"
        invalid.write_text("{}")
        preserved_record, preserved_result = owner.record, card.result
        monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(invalid)))
        card.load_review()
        wait(owner)
        assert owner.record is preserved_record and card.result is preserved_result
        assert "Unsupported joint-clearance" in card.note.text
        # Choosing a destination must not save a geometry or review made obsolete
        # while that picker was open.
        pending = []
        untouched = tmp_path / "stale.json"
        monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: pending.append(cb))
        card.save_profile()
        card.tolerance.text = "0.002"
        pending.pop()(str(untouched))
        assert not untouched.exists() and "changed while choosing" in card.note.text
        card.exclusions.text = "Arm | Fixture"
        card.review()
        wait(owner)
        assert card.result is None and "All body pairs" in card.note.text
        card.exclusions.text = ""
        card.review()
        wait(owner)
        assert card.result is not None
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()
        pump_frames(3)


def test_clearance_cancellation_stale_result_and_worker_failure_release_controls(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_joint_clearance as desktop

    ws = kivy_app.root.desktop_workspace
    owner = KinematicReviewPanel(ws)
    card = owner.clearance_panel
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(profile(tmp_path))))
    owner.import_profile()
    wait(owner)
    owner.seeds.text = "0\n360"
    add_bodies(card)
    original = desktop.review_joint_clearance
    for action in ("cancel", "change", "close"):
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, entered=entered, release=release, **kwargs):
            entered.set()
            assert release.wait(5)
            return original(*args, **kwargs)

        with monkeypatch.context() as scoped:
            scoped.setattr(desktop, "review_joint_clearance", delayed)
            card.review()
            assert entered.wait(2)
            if action == "cancel":
                owner.cancel()
            elif action == "change":
                card.tolerance.text = "0.02"
            else:
                owner.dispose()
            release.set()
            wait(owner)
            assert card.result is None and not card.review_action.disabled
    # A new instance verifies unexpected exceptions without reviving a closed card.
    owner = KinematicReviewPanel(ws)
    card = owner.clearance_panel
    owner.import_profile()
    wait(owner)
    owner.seeds.text = "0\n360"
    add_bodies(card)
    monkeypatch.setattr(
        desktop, "review_joint_clearance", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("synthetic defect"))
    )
    card.review()
    wait(owner)
    assert "RuntimeError" in card.note.text and not card.review_action.disabled and not owner.running
    owner.dispose()


def test_thread_launch_failure_restores_review_controls(kivy_app, monkeypatch):
    import carveracontroller.desktop_kinematic_review as desktop

    owner = KinematicReviewPanel(kivy_app.root.desktop_workspace)

    def fail(thread):
        raise RuntimeError("no thread")

    monkeypatch.setattr(desktop.threading.Thread, "start", fail)
    owner._start(lambda cancelled: None, lambda result: None, error_target=owner.clearance_panel.note)
    assert not owner.running and not owner.clearance_panel.review_action.disabled
    assert "could not start" in owner.clearance_panel.note.text
    owner.dispose()
