import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_surface_inspection import SurfaceInspectionReview
from tests.integration.conftest import pump_frames
from tests.unit.test_inspection_plane import plane_features

_owners = []


@pytest.fixture(autouse=True)
def close_review_popups():
    yield
    for owner in _owners:
        owner.popup.dismiss(animation=False)
    pump_frames(12, sleep=0.01)
    _owners.clear()


def wait_until(predicate):
    until = time.monotonic() + 5
    while not predicate() and time.monotonic() < until:
        pump_frames(1, sleep=0.01)
    assert predicate()


def review_owner(tmp_path):
    store, ids = plane_features(tmp_path, noise=0.02)
    ws = SimpleNamespace(
        surface_inspection_store=store,
        choose_profile_file=Mock(),
        machine=SimpleNamespace(controller=SimpleNamespace(executeCommand=Mock())),
    )
    owner = SurfaceInspectionReview(ws, ids[0])
    _owners.append(owner)
    owner.popup.open()
    pump_frames(4)
    return owner, store, ids


def test_plane_worker_review_selection_limit_export_and_read_only_custody(tmp_path):
    owner, store, ids = review_owner(tmp_path)
    before = store.path.read_bytes()
    owner.section.text = "Plane review"
    owner.plane.review()
    owner.plane.review()  # Duplicate review remains one serialized operation.
    wait_until(lambda: not owner.busy)
    result = owner.plane.result
    assert result["fit"]["residual_range_mm"] > 0.039
    assert "4 selected compensated" in owner.plane.status.text
    assert "Unknown" in owner.plane.details.text
    owner.plane.select(3)
    assert ids[3] in owner.plane.details.text
    assert owner.plane.next.disabled
    owner.plane.limit.text = "0.001 in"
    assert "outside entered limit 0.0254 mm" in owner.plane.status.text
    owner.plane.limit.text = "0.002 in"
    assert "within entered limit 0.0508 mm" in owner.plane.status.text
    owner.plane.export()
    chooser = owner.workspace.choose_profile_file.call_args.args[0]
    target = tmp_path / "native-plane.cvplane"
    chooser(str(target))
    wait_until(lambda: not owner.busy)
    assert json.loads(target.read_bytes())["report"] == result
    assert json.loads(target.read_bytes())["comparison"]["maximum_residual_range_mm"] == pytest.approx(0.0508)
    assert "saved and read back" in owner.plane.details.text
    assert store.path.read_bytes() == before
    owner.workspace.machine.controller.executeCommand.assert_not_called()
    owner.popup_close()


def test_section_changes_release_hidden_focus_and_retain_entry_draft(tmp_path):
    owner, store, ids = review_owner(tmp_path)
    owner.section.text = "Record receipt"
    owner.positions[0].text = "12.5 mm"
    owner.positions[0].focus = True
    owner.section.text = "Plane review"
    assert not owner.positions[0].focus
    assert owner.section_content.children == [owner.plane]
    owner.section.text = "Receipts"
    assert owner.section_content.children == [owner.receipts]
    owner.section.text = "Record receipt"
    assert owner.positions[0].text == "12.5 mm"
    owner.popup_close()


def test_selection_change_while_worker_running_discards_original_result(tmp_path, monkeypatch):
    import carveracontroller.desktop_inspection_plane as module

    original = module.plane_review
    entered, release = threading.Event(), threading.Event()

    def held(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(module, "plane_review", held)
    owner, store, ids = review_owner(tmp_path)
    owner.plane.review()
    assert entered.wait(2)
    owner.selector.text = next(k for k, v in owner.choices.items() if v == ids[1])
    release.set()
    wait_until(lambda: not owner.busy)
    assert owner.plane.result is None
    assert owner.plane.export_button.disabled
    owner.popup_close()


def test_close_during_review_cannot_publish_or_reopen(tmp_path, monkeypatch):
    import carveracontroller.desktop_inspection_plane as module

    original = module.plane_review
    entered, release = threading.Event(), threading.Event()

    def held(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(module, "plane_review", held)
    owner, store, ids = review_owner(tmp_path)
    owner.plane.review()
    assert entered.wait(2)
    owner.popup_close()
    release.set()
    wait_until(lambda: not owner.busy)
    assert owner.closed and owner.plane.result is None
    wait_until(lambda: owner.popup.parent is None)


@pytest.mark.parametrize("width", [400, 1200])
def test_plane_panel_layout_and_render_at_narrow_and_wide_widths(tmp_path, width):
    from kivy.core.window import Window
    from kivy.uix.floatlayout import FloatLayout
    from PIL import Image

    owner, store, ids = review_owner(tmp_path)
    owner.section.text = "Plane review"
    panel = owner.plane
    owner.plane.review()
    wait_until(lambda: not owner.busy)
    owner.section_content.remove_widget(panel)
    panel.size_hint_x = None
    panel.width = width
    host = FloatLayout()
    host.add_widget(panel)
    Window.add_widget(host)
    try:
        pump_frames(8)
        assert panel.plot.width > 0 and panel.plot.right <= panel.right
        assert panel.review_button.width > 0 and panel.review_button.right <= panel.right
        assert panel.export_button.right <= panel.right
        texture = panel.export_as_image().texture
        Image.frombytes("RGBA", texture.size, texture.pixels).save(tmp_path / f"inspection-plane-{width}.png")
    finally:
        Window.remove_widget(host)
        owner.popup_close()


def test_optional_limit_and_every_excluded_feature_are_reachable(tmp_path):
    from carveracontroller.machine.surface_inspection import restore_plan

    owner, store, ids = review_owner(tmp_path)
    anchor = store.get(ids[0])
    for i in range(25):
        store.create(
            restore_plan(anchor["plan"]), part=anchor["part"], name=f"Unmeasured {i + 1}", context=anchor["context"]
        )
    assert owner.plane.limit.optional and not owner.plane.limit.error
    owner.plane.review()
    wait_until(lambda: not owner.busy)
    assert len(owner.plane.result["excluded"]) == 25
    assert "1–20/25" in owner.plane.exclusions.text
    owner.plane.turn_exclusions(1)
    assert "21–25/25" in owner.plane.exclusions.text
    assert "Unmeasured 25" in owner.plane.exclusions.text
    assert owner.plane.exclusion_next.disabled
    owner.popup_close()


def test_export_chooser_cannot_publish_after_anchor_change(tmp_path):
    owner, store, ids = review_owner(tmp_path)
    owner.plane.review()
    wait_until(lambda: not owner.busy)
    owner.plane.export()
    callback = owner.workspace.choose_profile_file.call_args.args[0]
    owner.selector.text = next(k for k, v in owner.choices.items() if v == ids[1])
    target = tmp_path / "stale.cvplane"
    callback(str(target))
    assert not target.exists()
    assert owner.plane.result is None
    owner.popup_close()
