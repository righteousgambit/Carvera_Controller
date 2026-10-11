"""Real background exchange, compact controls and detached/stale historical routes."""

import threading
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_approach import prepared


def route_card(kivy_app, monkeypatch, tmp_path):
    viewer, send, owner, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    parent = target.sections.surfaces.result
    text = "G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG0 X1\nG1 X0 F100\nG0 X1\nT2 M6\nG0 X0\nG1 X1 F100"
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(text))
    assert source.file_hash == parent.body_review.program_hash
    target.sections.surfaces.review.retained_inputs = (source, {"G54": (-9, -5, -10)})
    card.route_mode.text = "Full approach route"
    card.start_coordinates.text = "-9, -5, -8"
    card.calculate()
    wait(owner)
    assert card.result is not None and not card.save_route.disabled
    return viewer, send, owner, target, card


@pytest.mark.parametrize("width", [360, 800])
def test_save_open_resave_and_historical_context_preserve_live_workbench(kivy_app, monkeypatch, tmp_path, width):
    viewer, send, owner, target, card = route_card(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        baseline = (
            viewer.machine_setup,
            owner.record,
            target.sections.surfaces.result,
            target.allowance.result,
            target.target,
            owner.workspace.operation_panel.program,
        )
        path = tmp_path / "saved.cvapproachreview"
        picker = Mock()
        monkeypatch.setattr(owner.workspace, "choose_profile_file", picker)
        card.save_route.dispatch("on_release")
        assert picker.call_args.kwargs["extension"] == ".cvapproachreview"
        picker.call_args.args[0](str(path))
        assert owner.running and card.save_route.disabled and card.open_route.disabled
        assert not card.cancel_button.disabled
        wait(owner)
        assert path.exists() and "Saved and recomputed" in card.exchange_status.text
        assert "declared bodies" in card.status.text and "Recompute" not in card.status.text
        first, raw = card.result, path.read_bytes()
        monkeypatch.setattr(owner.workspace, "choose_asset_file", picker)
        card.open_route.dispatch("on_release")
        assert picker.call_args.kwargs["suffixes"] == (".cvapproachreview",)
        picker.call_args.args[0](str(path))
        assert owner.running and not card.cancel_button.disabled
        wait(owner)
        assert card.result is not first and card.result.proposal_sha256 == first.proposal_sha256
        assert "Historical start only" in card.exchange_status.text and card.captured_start is None
        assert card.progress_event is None and not card.save_route.disabled
        assert baseline == (
            viewer.machine_setup,
            owner.record,
            target.sections.surfaces.result,
            target.allowance.result,
            target.target,
            owner.workspace.operation_panel.program,
        )
        again = tmp_path / "again.cvapproachreview"
        card.save_route.dispatch("on_release")
        picker.call_args.args[0](str(again))
        wait(owner)
        assert again.read_bytes() == raw
        assert "declared bodies" in card.status.text and "Recompute" not in card.status.text
        target.allowance.content.remove_widget(card)
        card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Complete saved approach", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        pump_frames(8)
        scroll.scroll_to(card.save_route, animate=False)
        pump_frames(4)
        for button in (card.save_route, card.open_route):
            button.texture_update()
            assert button.texture_size[0] <= button.width and button.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"approach-archive-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


@pytest.mark.parametrize(
    "mode", ["save_cancel", "save_aba", "open_cancel", "open_aba", "open_refusal", "picker_change"]
)
def test_cancelled_stale_refused_exchange_never_replaces_prior_evidence(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_approach_io as io

    viewer, send, owner, target, card = route_card(kivy_app, monkeypatch, tmp_path)
    prior = card.result
    path = tmp_path / "selected.cvapproachreview"
    picker = Mock()
    monkeypatch.setattr(owner.workspace, "choose_profile_file", picker)
    monkeypatch.setattr(owner.workspace, "choose_asset_file", picker)
    entered, release = threading.Event(), threading.Event()
    saving = mode.startswith("save")
    name = "save_approach_review" if saving else "load_approach_review"
    real = getattr(io, name)

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "open_refusal":
            raise ValueError("Saved route differs from recomputed source")
        return real(*args, **kwargs)

    monkeypatch.setattr(io, name, blocked)
    try:
        if saving:
            path.write_bytes(b"prior destination")
        else:
            io.save_approach_review(path, card.exchange_context.source, card.exchange_context.offsets, prior)
        (card.save_route if saving else card.open_route).dispatch("on_release")
        if mode == "picker_change":
            card.start_coordinates.text = "-9.5, -5, -8"
            picker.call_args.args[0](str(path))
            assert not owner.running and "changed" in card.exchange_status.text
            return
        picker.call_args.args[0](str(path))
        assert entered.wait(3)
        if mode.endswith("cancel"):
            owner.cancel()
        elif mode.endswith("aba"):
            original = card.start_coordinates.text
            card.start_coordinates.text = "-9.5, -5, -8"
            card.start_coordinates.text = original
        release.set()
        wait(owner)
        assert card.result is (None if mode.endswith("aba") else prior)
        if saving:
            assert path.read_bytes() == b"prior destination"
        assert card.progress_event is None and not owner.running
        assert not card.open_route.disabled
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()
