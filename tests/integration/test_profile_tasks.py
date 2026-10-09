"""Profile task navigation retains drafts and reading position without machine writes."""

from unittest.mock import Mock

import pytest

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.desktop_profiles import ProfileStore
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize(
    "kind,tasks",
    [
        ("machines", ("Identity", "Connection", "Scene", "Workholding")),
        ("tools", ("Geometry", "Assets", "Catalog")),
        ("toolsets", ("Slots",)),
    ],
)
def test_profile_task_navigation_retains_widgets_drafts_and_record_context(
    kivy_app, tmp_path, monkeypatch, kind, tasks
):
    from kivy.uix.popup import Popup

    store = ProfileStore(tmp_path / "profiles.json")
    method = getattr(store, {"machines": "save_machine", "tools": "save_tool", "toolsets": "save_toolset"}[kind])
    extra = {"diameter": 6.35, "shank_diameter": 6.35} if kind == "tools" else {}
    first, second = (method({"name": name, **extra}) for name in ("First", "Second"))
    before = store.path.read_bytes()
    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    library = ProfileLibrary(workspace, store=store, embedded=True)
    library.select_record(kind, first["id"])
    popup = Popup(content=library, size_hint=(None, None), size=(600, 540))
    popup.open(animation=False)
    try:
        pump_frames(8)
        assert library.editor_tasks.names == tasks
        fields = dict(library.fields)
        library.fields["name"].text = "Unsaved first"
        for name in tasks:
            library.editor_tasks.show(name)
            pump_frames(6)
            assert library.editor_tasks.host.children == [library.editor_tasks.sections[name]]
            assert library.fields == fields
            for other in tasks:
                assert (library.editor_tasks.sections[other].parent is library.editor_tasks.host) == (other == name)
            assert library.actions.top <= library.editor_scroll.y
            assert library.editor_scroll.height >= 80, {
                "task": name,
                "library": library.size,
                "editor": library.editor_card.size,
                "deck": library.editor_tasks.size,
                "summary": library.editor_tasks.summary.size,
                "heading": library.editor_heading.size,
                "parent": library.editor_heading.parent,
                "status": library.draft_status.size,
                "limited": library._space_limited,
            }
        library.editor_scroll.scroll_y = 0.37
        library._edit(second)
        departed = library.editor_tasks
        library._edit(first)
        pump_frames(8)
        assert departed.closed and departed.choice.is_open is False
        assert library.editor_tasks.active == tasks[-1]
        assert library.editor_scroll.scroll_y == pytest.approx(0.37)
        assert library.fields["name"].text == "Unsaved first"
        assert store.path.read_bytes() == before
        send.assert_not_called()
        for name in tasks:
            library.editor_tasks.show(name)
            pump_frames(8)
            library.export_to_png(str(tmp_path / f"profile-{kind}-{name.lower()}-compact.png"))
    finally:
        library.dispose()
        popup.dismiss(animation=False)
        pump_frames(3)


def test_hidden_geometry_focus_returns_to_geometry_without_late_scroll_restore(kivy_app, tmp_path):
    from kivy.uix.popup import Popup

    store = ProfileStore(tmp_path / "profiles.json")
    tool = store.save_tool({"name": "Cutter", "diameter": 6.35, "shank_diameter": 6.35, "length": 75})
    library = ProfileLibrary(kivy_app.root.desktop_workspace, store=store, embedded=True)
    library.select_record("tools", tool["id"])
    popup = Popup(content=library, size_hint=(None, None), size=(500, 540))
    popup.open(animation=False)
    try:
        pump_frames(8)
        library.fields["diameter"].focus = True
        library.fields["diameter"].text = "invalid"
        library.editor_tasks.show("Assets")
        pump_frames(6)
        assert not library.fields["diameter"].focus
        assert library.tool_drawing_card.parent is None
        assert library.focus_field("stickout")
        pump_frames(8)
        assert library.editor_tasks.active == "Geometry"
        assert library.fields["stickout"].focus
        assert library.editor_tasks.restore_event is None
        assert library.fields["diameter"].text == "invalid"
        library.editor_tasks.show("Assets")
        assert library.focus_field("stickout")
        library.editor_tasks.show("Catalog")
        pump_frames(8)
        assert library.editor_tasks.active == "Catalog"
        assert not library.fields["stickout"].focus
        old = library.editor_tasks
        library.new()
        pump_frames(8)
        assert old.closed
        assert library.editor_tasks.active == "Geometry"
    finally:
        library.dispose()
        popup.dismiss(animation=False)
        pump_frames(3)


def test_new_profile_save_carries_task_to_saved_identity_without_loading(kivy_app, tmp_path, monkeypatch):
    store = ProfileStore(tmp_path / "profiles.json")
    workspace = kivy_app.root.desktop_workspace
    load = Mock()
    monkeypatch.setattr(workspace, "request_tool_profile", load)
    library = ProfileLibrary(workspace, store=store, embedded=True)
    library.select_kind("tools")
    library.new()
    library.fields["name"].text = "Imperial cutter"
    library.fields["diameter"].text = "1/4 in"
    library.fields["shank_diameter"].text = "1/4 in"
    library.editor_tasks.show("Catalog")
    library.fields["vendor"].text = "Draft manufacturer"
    saved = library.save()
    assert saved is not None, library.status.text
    assert saved["diameter"] == 6.35
    assert saved["vendor"] == "Draft manufacturer"
    assert library.selected_id == saved["id"]
    assert library.editor_tasks.active == "Catalog"
    assert library._task_contexts[("tools", saved["id"])][0] == "Catalog"
    assert library._raw_fields() == library._baseline
    load.assert_not_called()
    library.dispose()
