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
