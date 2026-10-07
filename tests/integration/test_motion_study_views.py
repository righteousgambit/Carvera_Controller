import json

import pytest

from carveracontroller.desktop_declared_path import DeclaredPathPanel
from carveracontroller.desktop_joint_feedback import JointFeedbackPanel
from carveracontroller.desktop_motion_study_views import MotionStudyViews
from tests.unit.test_joint_motion_study import read, record


def review(tmp_path):
    data = record()
    data["observed_feedback"] = {
        "source": "Synthetic reported trace",
        "timing_source": "Unqualified independent clock",
        "duration_seconds": 32,
        "samples": [{"seconds": t, "reported": {"table": t}} for t in (0, 5, 15, 32)],
    }
    return read(tmp_path, data)


def test_exclusive_views_preserve_independent_cursors_and_release_hidden_keyboard_focus(tmp_path):
    path, feedback = DeclaredPathPanel(), JointFeedbackPanel()
    views = MotionStudyViews(path, feedback)
    report = review(tmp_path)
    views.show(report, ("p", 2))
    assert views.mode == "Declared path" and path.parent is views and feedback.parent is None
    path.select(90)
    views.actions["Feedback"].dispatch("on_release")
    assert path.parent is None and feedback.parent is views
    from carveracontroller.desktop_components import ACCENT, RAISED

    assert views.actions["Feedback"].base_color == ACCENT
    assert views.actions["Declared path"].base_color == RAISED
    feedback.select(2)
    feedback.plot.focus = True
    views.select("Declared path")
    assert not feedback.plot.focus and path.cursor == 90
    views.select("Feedback")
    assert feedback.cursor == 2
    views.show(report, ("p", 2))
    assert views.mode == "Feedback" and feedback.cursor == 2
    views.select("Overview")
    assert path.parent is feedback.parent is None
    views.show(report, ("p", 3))
    assert views.mode == "Declared path" and path.cursor == feedback.cursor == 0
    views.actions["Overview"].focus = True
    views.show(None, None)
    assert not any(action.focus for action in views.actions.values())
    assert views.mode == "Overview" and path.parent is feedback.parent is None
    assert views.actions["Declared path"].disabled and views.actions["Feedback"].disabled
    views.select("Feedback")
    assert views.mode == "Overview"


@pytest.mark.parametrize("width", [360, 650])
def test_compact_tab_layout_and_height_reduction(width, tmp_path):
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    from tests.integration.conftest import pump_frames

    views = MotionStudyViews(DeclaredPathPanel(), JointFeedbackPanel())
    views.show(review(tmp_path), ("p", 2))
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(views)
    popup = Popup(content=scroll, size_hint=(None, None), size=(width, 650))
    popup.open(animation=False)
    try:
        pump_frames(6)
        path_height = views.height
        assert views.actions["Feedback"].right <= views.right
        views.select("Overview")
        pump_frames(4)
        assert views.height < path_height / 2
        views.select("Feedback")
        pump_frames(4)
        assert views.feedback.parent is views and views.path.parent is None
        assert views.feedback.note.texture_size[1] <= views.feedback.note.height
        scroll.export_to_png(str(tmp_path / f"motion-study-views-{width}.png"))
    finally:
        popup.dismiss(animation=False)


def test_switching_charts_preserves_visible_selector_anchor_and_user_scroll_wins(tmp_path):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.popup import Popup
    from kivy.uix.widget import Widget

    from carveracontroller.desktop_components import DesktopScrollView
    from tests.integration.conftest import pump_frames

    views = MotionStudyViews(DeclaredPathPanel(), JointFeedbackPanel())
    views.show(review(tmp_path), ("p", 2))
    content = BoxLayout(orientation="vertical", size_hint_y=None)
    content.bind(minimum_height=content.setter("height"))
    content.add_widget(Widget(size_hint_y=None, height=900))
    content.add_widget(views)
    content.add_widget(Widget(size_hint_y=None, height=900))
    scroll = DesktopScrollView(do_scroll_x=False)
    scroll.add_widget(content)
    popup = Popup(content=scroll, size_hint=(None, None), size=(650, 650))
    popup.open(animation=False)
    try:
        pump_frames(8)

        def anchor():
            return views.tabs.to_window(views.tabs.x, views.tabs.top)[1]

        travel = content.height - scroll.height
        wanted = scroll.to_window(scroll.x, scroll.top)[1] - 100
        scroll.scroll_y += (anchor() - wanted) / travel
        pump_frames(4)
        before = anchor()
        assert abs(before - wanted) < 1
        path_height = views.height
        for mode in ("Feedback", "Overview", "Declared path"):
            views.actions[mode].dispatch("on_release")
            pump_frames(10)
            assert abs(anchor() - before) < 1, mode
            if mode == "Overview":
                assert views.height < path_height / 2
        # A scroll between the click and settled layout must not be undone.
        views.select("Feedback")
        scroll.scroll_y = 0.2
        pump_frames(10)
        assert scroll.scroll_y == pytest.approx(0.2)
        # A hidden page must not have its viewport adjusted by a late callback.
        views.select("Declared path")
        views.opacity = 0
        pump_frames(10)
        assert scroll.scroll_y == pytest.approx(0.2)
        views.opacity = 1
        # Replacement blocks invalidate any pending preservation.
        views.select("Declared path")
        views.show(None, None)
        pump_frames(10)
        assert views.report is None and views.mode == "Overview"
    finally:
        popup.dismiss(animation=False)
