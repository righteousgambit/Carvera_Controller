import json
from unittest.mock import Mock

from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.desktop_profiles import ProfileStore, validate_library
from tests.integration.conftest import pump_frames


def test_library_filters_pages_drafts_and_compact_layout(kivy_app, tmp_path, monkeypatch):
    # One atomic write of a large real library, not dozens of redundant fsyncs.
    data = validate_library(
        {
            "schema": 1,
            "machines": [],
            "toolsets": [],
            "tools": [
                {
                    "id": f"tool-{i}",
                    "name": f"Cutter {i:03}",
                    "vendor": "Titan" if i % 2 else "Helical",
                    "product_id": f"part-{i}",
                    "diameter": 6.35 if i % 2 else 3.175,
                    "shank_diameter": 6.35,
                    "geometry_path": "attached.json" if i % 2 else "",
                    "shape": "flat_end_mill",
                }
                for i in range(95)
            ],
        }
    )
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data))
    store = ProfileStore(path)
    before = store.path.read_bytes()
    ws = kivy_app.root.desktop_workspace
    send, apply = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "apply_tool_profile", apply)
    library = ProfileLibrary(ws, store=store, size_hint=(None, None), size=(dp(1100), dp(780)))
    Window.add_widget(library)
    try:
        library.select_kind("tools")
        library.fields["name"].text = "Unfinished editor draft"
        pump_frames(10, sleep=0.02)
        assert len(library.matches) == 95
        assert len(library.list_items.children) == 31
        library._browse_page(1)
        assert library.page_index == 1 and len(library.list_items.children) == 31
        library.open_filters()
        popup = library.filter_popup
        pump_frames(4)
        popup.fields["vendor"].text = "Titan"
        popup.fields["shank"].text = "1/4 in"
        popup.fields["assets"].text = "CAD reference"
        popup.apply_action.dispatch("on_release")
        pump_frames(4)
        assert len(library.matches) == 47
        assert library.page_index == 0
        assert library.fields["name"].text == "Unfinished editor draft"
        selected = library.cutter_filter
        library.open_filters()
        popup = library.filter_popup
        popup.fields["minimum"].text = "1/2 in"
        popup.fields["maximum"].text = "1/4 in"
        popup.apply_action.dispatch("on_release")
        assert library.cutter_filter is selected and popup.parent is not None
        assert "exceeds" in popup.message.text
        popup.dismiss()
        library.search.text = "Titan part-93"
        pump_frames(10, sleep=0.02)
        assert [r["id"] for r in library.matches] == ["tool-93"]
        library.size = (dp(700), dp(780))
        pump_frames(10)
        assert library.browser_controls.parent is library.list_card
        assert library.list_scroll.height >= dp(54)
        assert library.editor_scroll.height > dp(100)
        library.export_to_png(str(tmp_path / "compact-browser.png"))
        library.open_filters()
        pump_frames(10)
        library.filter_popup.export_to_png(str(tmp_path / "cutter-filters.png"))
        library.filter_popup.clear_action.dispatch("on_release")
        library.search.text = ""
        pump_frames(10, sleep=0.02)
        assert len(library.matches) == 95
        assert not library.cutter_filter.active
        original_size = Window.size
        library.open_filters()
        try:
            Window.size = (dp(500), dp(650))
            pump_frames(12)
            popup = library.filter_popup
            assert popup.width <= Window.width * 0.88 + dp(1)
            assert popup.height <= Window.height * 0.86 + dp(1)
            assert popup.apply_action.right <= popup.right
            # The desktop's minimum window width can clamp Window.size. Exercise
            # the filter's genuinely narrower layout independently as well.
            popup.size = (dp(440), dp(550))
            pump_frames(12)
            assert popup.filter_grid.cols == 1
            for control in popup.fields.values():
                assert control.width >= dp(200)
            popup.form_scroll.scroll_to(popup.fields["assets"], animate=False)
            pump_frames(6)
            popup.export_to_png(str(tmp_path / "narrow-cutter-filters.png"))
        finally:
            library.filter_popup.dismiss()
            Window.size = original_size
            pump_frames(8)
        assert store.path.read_bytes() == before
        send.assert_not_called()
        apply.assert_not_called()
    finally:
        if getattr(library, "filter_popup", None):
            library.filter_popup.dismiss()
        Window.remove_widget(library)
