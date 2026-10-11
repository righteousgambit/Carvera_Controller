"""Rendered declared transfer preview, draft retention and current-review guards."""

import json
from unittest.mock import Mock

import pytest

from tests.integration.conftest import pump_frames
from tests.integration.test_mill_turn_workbench import wait_review


def prepare(kivy_app):
    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.load_example()
    review = wait_review(panel)
    panel.select_step("grip", review)
    card = panel.transfer_geometry
    card.set_expanded(True)
    pump_frames(8)
    return panel, card


@pytest.mark.parametrize("width", [360, 650, 1100])
def test_dimensioned_section_uniform_scale_and_compact_controls(kivy_app, width, tmp_path):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    panel, card = prepare(kivy_app)
    parent = card.parent
    parent.remove_widget(card)
    popup = Popup(content=card, size_hint=(None, None), size=(dp(width + 28), dp(1800)))
    popup.open(animation=False)
    try:
        pump_frames(10)
        assert card.preview.study.accepted
        assert card.preview.primitives
        for name, model, pos, size in card.preview.primitives:
            assert pos[0] >= card.preview.x and pos[0] + size[0] <= card.preview.right + 1
            axial_scale = size[0] / (model[1] - model[0])
            radial_scale = size[1] / (model[3] - model[2])
            assert axial_scale == pytest.approx(radial_scale)
        for action in (card.start_action, card.contact_action, card.apply_action):
            assert action.x >= card.x and action.right <= card.right + dp(1)
        card.slider.value = 0
        pump_frames(4)
        assert "receiver Z 80" in card.position.text
        assert next(p for p in card.preview.primitives if p[0] == "receiver upper wall")[1][0] == 80
        card.export_to_png(str(tmp_path / f"transfer-geometry-{width}.png"))
    finally:
        popup.dismiss(animation=False)
        if card.parent:
            card.parent.remove_widget(card)
        parent.add_widget(card)
        card.set_expanded(False)


def test_fractional_draft_and_pose_retained_across_step_selection(kivy_app):
    panel, card = prepare(kivy_app)
    card.fields["stock_diameter_mm"].text = "3/4 in"
    card.fields["receiver_end_z_mm"].text = "invalid"
    card.slider.value = 0.25
    review = panel.review
    panel.select_step("cutoff", review)
    assert card.preview.study is None and card.dimensions.parent is None
    assert card.apply_action.disabled
    panel.select_step("grip", review)
    assert card.fields["stock_diameter_mm"].text == "3/4 in"
    assert card.fields["receiver_end_z_mm"].text == "invalid"
    assert card.slider.value == 0.25
    card.apply()
    assert panel.review is review and "not admitted" in card.message.text
    card.set_expanded(False)


def test_reviewed_edit_blocks_dependents_and_contact_seek_is_exact(kivy_app, monkeypatch):
    panel, card = prepare(kivy_app)
    send = Mock()
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    original = panel.review
    card.fields["receiver_end_z_mm"].text = "35 mm"
    card.apply()
    review = wait_review(panel)
    assert review is not original and panel.selected_id == "grip"
    assert card.preview.study.contacts and not card.contact_action.disabled
    card.seek_contact()
    contact = card.preview.study.contacts[0]
    assert card.slider.value == pytest.approx(contact.fraction)
    assert f"receiver Z {contact.receiver_face_z_mm:g}" in card.position.text
    assert next(row for row in review.steps if row.step.id == "back-mill").status == "blocked"
    assert review.final_state.pieces[0].holders == ("main",)
    send.assert_not_called()
    card.set_expanded(False)


def test_add_absent_geometry_draft_is_retained_and_old_review_cannot_apply(kivy_app):
    from carveracontroller.machine.mill_turn_plan import example_record

    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.source.text = json.dumps(example_record())
    panel.request_review()
    review = wait_review(panel)
    panel.select_step("grip", review)
    card = panel.transfer_geometry
    assert card.preview.study is None and not card.add_action.disabled
    original = panel.source.text
    card.add_geometry()
    card.fields["receiver.bore_diameter_mm"].text = "1 in"
    panel.select_step("cutoff", review)
    panel.select_step("grip", review)
    assert card.fields["receiver.bore_diameter_mm"].text == "1 in"
    assert panel.source.text == original
    card.apply()
    assert wait_review(panel).plan.transfer_geometry
    assert card.fields["receiver.bore_diameter_mm"].value() == 25.4
    stale_item = card.item
    panel.source.text = "new invalid draft"
    assert card.item is None and card.preview.study is None
    card.item = stale_item  # Late callback from an old drawing/edit owner.
    card.apply()
    assert panel.source.text == "new invalid draft"
    card.show(None, None)
