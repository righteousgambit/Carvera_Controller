"""The embedded cutter library keeps contextual assignment separate from saving."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.desktop_profiles import ProfileStore
from tests.integration.conftest import pump_frames


class RecordingAssignment:
    """Only the library/controller boundary is exercised by these tests."""

    def __init__(self, number=3, *, accepted=True):
        self.number = number
        self.active = True
        self.pending = False
        self.accepted = accepted
        self.applied = []
        self.cancelled = []
        self.replacements = 0

    def cancel(self, reason=""):
        self.cancelled.append(reason)
        self.active = self.pending = False

    def editor_replaced(self):
        self.replacements += 1
        if self.pending:
            self.cancel("Editor replaced during preparation.")

    def apply(self, library):
        self.applied.append(library)
        self.pending = self.accepted
        return self.accepted


@pytest.fixture
def editor(kivy_app, tmp_path, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    store = ProfileStore(tmp_path / "profiles.json")
    first, second = (
        store.save_tool({"name": name, "number": 1, "diameter": 6, "shank_diameter": 6})
        for name in ("First saved cutter", "Second saved cutter")
    )
    requests = {}
    for name in ("request_machine_profile", "request_tool_profile", "request_toolset_profile"):
        requests[name] = Mock(return_value=True)
        monkeypatch.setattr(workspace, name, requests[name])
    send = Mock(side_effect=AssertionError("Library assignment must not issue machine commands"))
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    library = ProfileLibrary(workspace, store=store, embedded=True)
    library.select_record("tools", first["id"])
    try:
        yield SimpleNamespace(library=library, store=store, first=first, second=second, requests=requests)
        send.assert_not_called()
    finally:
        library.dispose()


@pytest.mark.parametrize("accepted", (True, False))
def test_saved_cutter_button_delegates_without_saving_or_generic_fallback(editor, monkeypatch, accepted):
    library, store = editor.library, editor.store
    context = RecordingAssignment(3, accepted=accepted)
    library.set_simulation_assignment(context)
    before, generation = store.path.read_bytes(), store.generation
    save = Mock(side_effect=AssertionError("Contextual assignment must not save implicitly"))
    monkeypatch.setattr(library, "save", save)

    assert "preview T3" in library.apply_button.text
    assert not library.apply_button.disabled
    library.apply_button.dispatch("on_release")

    assert context.applied == [library]
    assert context.pending is accepted
    assert library.apply_button.disabled is accepted
    assert library.fields["number"].text == "1"
    assert store.path.read_bytes() == before and store.generation == generation
    save.assert_not_called()
    for request in editor.requests.values():
        request.assert_not_called()


@pytest.mark.parametrize(
    "state,message",
    (
        ("dirty", "Save these edits first"),
        ("new", "Save this new cutter first"),
        ("changed", "changed or was removed"),
        ("removed", "changed or was removed"),
        ("pending", "Preparing"),
        ("cancelled", "Assignment ended"),
        ("other_kind", "Assignment ended"),
    ),
)
def test_contextual_apply_rejects_unavailable_saved_selection(editor, monkeypatch, state, message):
    library, store = editor.library, editor.store
    context = RecordingAssignment()
    library.set_simulation_assignment(context)
    if state == "dirty":
        library.fields["diameter"].text = "invalid unsaved geometry"
    elif state == "new":
        library.new()
    elif state == "changed":
        store.save_tool(dict(editor.first, name="Changed elsewhere"))
    elif state == "removed":
        store.delete("tools", editor.first["id"])
    elif state == "pending":
        context.pending = True
    elif state == "cancelled":
        context.cancel()
    else:
        library.select_kind("machines")
    before, generation, fields = store.path.read_bytes(), store.generation, library._raw_fields()
    save = Mock(side_effect=AssertionError("A disabled contextual action must not save"))
    monkeypatch.setattr(library, "save", save)
    library.refresh_context_action()

    assert library.apply_button.disabled
    # Direct calls must obey the same gate as the disabled button.
    assert library.apply() is False

    assert message in library.status.text
    assert "preview T3" in library.apply_button.text
    assert library._raw_fields() == fields
    assert store.path.read_bytes() == before and store.generation == generation
    assert not context.applied
    save.assert_not_called()
    for request in editor.requests.values():
        request.assert_not_called()


def test_context_caption_survives_compact_reflow_and_async_refresh(editor):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    library = editor.library
    context = RecordingAssignment()
    library.set_simulation_assignment(context)
    popup = Popup(content=library, size_hint=(None, None), size=(dp(388), dp(440)))
    popup.open(animation=False)
    try:
        pump_frames(8)
        assert library._space_limited
        assert "preview T3" in library.apply_button.text
        assert not library.apply_button.disabled
        library.fields["name"].text = "Unsaved cutter"
        assert library.apply_button.disabled and "Save these edits first" in library.draft_status.text
        library.revert()
        assert not library.apply_button.disabled
        replacements = context.replacements
        context.pending = True
        library._draft_changed()
        library.editor_tasks.show("Identity")
        pump_frames(3)
        assert context.active and context.pending and context.replacements == replacements
        assert library.apply_button.disabled and "preview T3" in library.apply_button.text
        context.pending = False
        library.refresh_context_action()
        assert not library.apply_button.disabled
        context.cancel()
        library.refresh_context_action()
        assert library.apply_button.disabled and "Assignment ended" in library.draft_status.text
        library.fields["name"].text = "Retained draft"
        library.set_simulation_assignment(None)
        assert not library.apply_button.disabled
        assert "preview T3" not in library.apply_button.text
        assert "Save &" in library.apply_button.text
        assert library.fields["name"].text == "Retained draft"
    finally:
        popup.dismiss(animation=False)
        pump_frames(3)


def test_editor_replacement_notifies_context_and_preserves_draft(editor):
    library = editor.library
    generation = editor.store.generation
    context = RecordingAssignment()
    library.set_simulation_assignment(context)
    library.fields["name"].text = "Retained first draft"
    library.select_record("tools", editor.second["id"])
    assert context.replacements > 0 and context.active
    library.select_record("tools", editor.first["id"])
    assert library.fields["name"].text == "Retained first draft"
    saved = library.save()
    assert saved["name"] == "Retained first draft"
    assert context.active and not library.apply_button.disabled
    assert editor.store.generation == generation + 1
    assert library.apply() is True
    assert context.applied == [library] and context.pending
    replacements = context.replacements
    library.refresh()
    assert context.replacements > replacements and not context.active
    assert library.simulation_assignment is context
    assert library.apply_button.disabled and "preview T3" in library.apply_button.text
    library.select_kind("machines")
    library.select_kind("tools")
    assert library.simulation_assignment is context and library.apply_button.disabled
    for request in editor.requests.values():
        request.assert_not_called()


def test_context_replacement_clear_and_dispose_cancel_only_previous_owner(editor):
    library = editor.library
    first, second = RecordingAssignment(3), RecordingAssignment(4)
    library.set_simulation_assignment(first)
    library.set_simulation_assignment(first)
    assert not first.cancelled
    library.set_simulation_assignment(second)
    assert first.cancelled and not second.cancelled
    assert "preview T4" in library.apply_button.text
    library.set_simulation_assignment(None)
    assert second.cancelled and library.simulation_assignment is None
    assert "preview T4" not in library.apply_button.text
    third = RecordingAssignment(5)
    third.pending = True
    library.set_simulation_assignment(third)
    library.dispose()
    assert third.cancelled and not third.active and not third.pending


def test_explicit_generic_entry_restores_saved_load_and_implicit_save_behavior(editor):
    library, store = editor.library, editor.store
    context = RecordingAssignment()
    library.set_simulation_assignment(context)
    library.set_simulation_assignment(None)
    before, generation = store.path.read_bytes(), store.generation

    library.apply_button.dispatch("on_release")
    request = editor.requests["request_tool_profile"]
    request.assert_called_once()
    assert request.call_args.args[0] == editor.first
    assert store.path.read_bytes() == before and store.generation == generation

    library.fields["name"].text = "Explicit generic draft"
    library.apply_button.dispatch("on_release")
    assert request.call_count == 2
    assert request.call_args.args[0]["name"] == "Explicit generic draft"
    assert request.call_args.args[0]["number"] == 1
    assert store.generation == generation + 1
    assert library._raw_fields() == library._baseline
    assert not context.applied
