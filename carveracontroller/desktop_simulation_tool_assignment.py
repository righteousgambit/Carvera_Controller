"""One local simulation-to-library intent, with no persistence or CNC commands."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict

from kivy.animation import Animation
from kivy.clock import Clock

from carveracontroller.machine.desktop_profiles import to_tool_definition
from carveracontroller.machine.retained_program_source import RetainedProgramSource


class SimulationToolAssignment:
    def __init__(self, panel, number):
        self.panel, self.workspace = panel, panel.workspace
        self.number = int(number)
        self.active, self.pending, self.navigating = True, False, False
        self.library = None
        self._bindings = []
        self._origin_bindings = []
        self._request = None
        self._return_event = None
        self._scroll_binding = None
        self.program = self.workspace.operation_panel.program
        if self.program is None or self.number not in self.program.motion_tool_ids():
            raise ValueError("Choose a cutter used by the completed program preview.")
        self.owners, self.preview = self._preview()
        self.viewer = self.workspace.machine.gcode_viewer
        self.epoch = self.viewer.declaration_epoch
        self.scene = self.workspace._profile_scene_identity()
        self.operation = self.workspace.operation_panel.selected_operation
        self.line = self.workspace.operation_panel.selected_line
        self.settings = self._settings()
        self.task = self.workspace.program_tasks.active
        self.position = self.workspace.program_tasks.scroll.scroll_y
        for name in ("scope", "stock_source", "resolution", "clearance_tolerance"):
            control = getattr(panel, name)
            callback = lambda *_: self.cancel("Simulation settings changed. Review the cutter again.")
            control.bind(text=callback)
            self._origin_bindings.append((control, callback))

    def _settings(self):
        return tuple(
            getattr(self.panel, name).text for name in ("scope", "stock_source", "resolution", "clearance_tolerance")
        )

    def _preview(self):
        ws = self.workspace
        machine, app = ws.machine, ws.app
        viewer = machine.gcode_viewer
        source = getattr(ws, "_retained_program_source", None)
        if (
            ws._profile_load_closed
            or machine.loading_file
            or getattr(ws, "_job_apply_active", False)
            or ws.operation_panel.program is not self.program
            or not isinstance(source, RetainedProgramSource)
            or not source.matches(
                app.selected_local_filename,
                app.selected_remote_filename,
                viewer.loaded_program_hash,
                machine.program_preview_generation,
            )
            or viewer.loaded_program_hash != self.program.file_hash
        ):
            raise ValueError("Wait for a complete local program preview, then review this cutter again.")
        return (ws, machine, app, viewer, viewer.meshmanager, source), (
            machine.program_preview_generation,
            viewer._program_identity_generation,
            ws.operation_panel.generation,
            app.selected_local_filename,
            app.selected_remote_filename,
            viewer.loaded_program_hash,
        )

    def _require_origin(self, *, check_epoch=True):
        owners, preview = self._preview()
        ws = self.workspace
        if (
            not self.active
            or getattr(ws, "simulation_tool_assignment", None) is not self
            or any(a is not b for a, b in zip(owners, self.owners))
            or preview != self.preview
            or (check_epoch and self.viewer.declaration_epoch != self.epoch)
            or ws._profile_scene_identity() != self.scene
            or ws.operation_panel.selected_operation is not self.operation
            or ws.operation_panel.selected_line != self.line
            or self._settings() != self.settings
        ):
            raise ValueError("The program, setup or simulation review changed; review the cutter again.")

    @contextmanager
    def navigation(self):
        previous, self.navigating = self.navigating, True
        try:
            yield
        finally:
            self.navigating = previous

    def open_library(self):
        try:
            self._require_origin()
        except ValueError as exc:
            self.cancel(str(exc))
            self.panel.note.text = str(exc)
            return
        with self.navigation():
            self.workspace._open_profiles(simulation_assignment=self)
            library = self.workspace.profile_library
            library.select_kind("tools")
            library.set_simulation_assignment(self)
            self.library = library

    def _unbind_editor(self):
        for control, callback in self._bindings:
            control.unbind(text=callback)
        self._bindings.clear()

    def editor_replaced(self):
        """Browsing remains available; replacing an editor retires its pending Apply."""
        if self.pending:
            self._request = None
            self.pending = False
            self._unbind_editor()
            if self.library is not None:
                self.library.status.text = "Cutter selection changed. Apply the saved selection when ready."
                self.library.refresh_context_action()

    def cancel(self, reason="Review closed. Open a simulation cutter to assign its preview again."):
        self.active = False
        self.pending = False
        self._request = None
        self._unbind_editor()
        self._unbind_origin()
        self._cancel_return()
        if self.library is not None and self.library.simulation_assignment is self:
            self.library.status.text = reason
            self.library.refresh_context_action()

    def _unbind_origin(self):
        for control, callback in self._origin_bindings:
            control.unbind(text=callback)
        self._origin_bindings.clear()

    def _owns_request(self, token):
        return (
            self.active
            and self.pending
            and self._request is token
            and getattr(self.workspace, "simulation_tool_assignment", None) is self
            and not self.workspace._profile_load_closed
            and self.workspace.active_section == "Profiles"
            and self.workspace.profile_library is self.library
            and self.library.simulation_assignment is self
        )

    def apply(self, library):
        if self.pending or not self.active:
            return False
        try:
            self._require_origin()
            if library is not self.library or library.store is not self.workspace.profile_store:
                raise ValueError("The cutter library changed. Open this review again.")
            store = library.store
            generation, data = store.snapshot()
            record = next((item for item in data["tools"] if item["id"] == library.selected_id), None)
            if (
                library.selected_kind != "tools"
                or record is None
                or record != library._baseline_record
                or library._raw_fields() != library._baseline
            ):
                raise ValueError("Choose an unchanged saved cutter, or save your edits before applying.")
            definition = to_tool_definition(record, number=self.number, units="mm")
        except (ValueError, OSError) as exc:
            library.status.text = str(exc)
            return False

        token = object()
        self._request, self.pending = token, True
        for control in library.fields.values():
            callback = lambda *_: self.editor_replaced()
            control.bind(text=callback)
            self._bindings.append((control, callback))
        library.status.text = f"Preparing {record['name']} for preview T{self.number}…"
        library.refresh_context_action()

        def publish(prepared):
            if not self._owns_request(token):
                raise ValueError("Cutter assignment superseded.")
            self._require_origin()
            if (
                store is not library.store
                or store is not self.workspace.profile_store
                or store.generation != generation
            ):
                raise ValueError("Saved cutter library changed during preparation. Apply the saved selection again.")
            if library.selected_id != record["id"] or library._raw_fields() != library._baseline:
                raise ValueError("Cutter selection changed during preparation.")
            profiles = self._profile_bindings(record, data, prepared[0])
            previous = self.viewer.capture_tool_display()
            try:
                self.viewer.publish_tool_profiles(prepared)
            except Exception as exc:
                try:
                    self.viewer.restore_tool_display(previous)
                except Exception as restore_error:
                    raise RuntimeError(f"{exc}; preview redraw restoration incomplete: {restore_error}") from exc
                self.epoch = self.viewer.declaration_epoch
                raise
            # Only renderer-owned tooling changes are acknowledged. Source/scene
            # identities stay pinned to the original review.
            self.epoch = self.viewer.declaration_epoch
            self.workspace.loaded_tool_profiles = profiles
            self.workspace.loaded_toolset = None

        def result(ok, message):
            if not self._owns_request(token):
                return
            self.pending = False
            self._request = None
            self._unbind_editor()
            if not ok:
                library.status.text = f"Preview T{self.number} assignment failed: {message}"
                library.refresh_context_action()
                return
            summary = f"Preview T{self.number}: {record['name']} · custom tool selection"
            library.status.text = summary
            self.workspace.profile_status.text = summary
            self.workspace.tool_library_summary.text = summary
            # Geometry is committed. Refresh/navigation failures cannot relabel it
            # as a failed publication or restore an old program over a newer one.
            try:
                library.refresh_context_action()
                self.panel.refresh_inputs()
                self._require_origin()
                self._return_to_review()
            except Exception as exc:
                self._return_failed(exc)

        try:
            accepted = self.workspace._request_tool_profiles(
                {self.number: definition}, False, publish, result, current=lambda: self._owns_request(token)
            )
        except Exception as exc:
            result(False, str(exc) or type(exc).__name__)
            return False
        if not accepted:
            result(False, "The workspace is closed.")
        return accepted

    def _profile_bindings(self, record, data, updated):
        ws = self.workspace
        candidates = dict(getattr(ws, "loaded_tool_profiles", {}))
        if ws.loaded_toolset:
            by_id = {profile["id"]: profile for profile in data["tools"]}
            for number, profile_id in ws.loaded_toolset.get("slots", {}).items():
                profile = by_id.get(profile_id)
                if profile is not None:
                    candidates[int(number)] = profile
        profiles = {}
        for number, profile in candidates.items():
            active = updated.get(number)
            if active is None or number == self.number:
                continue
            expected, actual = asdict(to_tool_definition(profile, number=number)), asdict(active)
            for key in ("geometry_sha256", "holder_geometry_sha256"):
                expected.pop(key, None)
                actual.pop(key, None)
            if expected == actual:
                profiles[number] = deepcopy(profile)
        profiles[self.number] = deepcopy(record)
        return profiles

    def _cancel_return(self):
        if self._return_event is not None:
            self._return_event.cancel()
            self._return_event = None
        if self._scroll_binding is not None:
            scroll, callback = self._scroll_binding
            scroll.unbind(scroll_y=callback)
            self._scroll_binding = None

    def _return_failed(self, error):
        self.active = False
        self._unbind_origin()
        self._cancel_return()
        self.library.status.text = (
            f"Preview T{self.number} applied. Return position could not be restored; "
            f"open Simulation to review the new cutter. {error}"
        )

    def _return_to_review(self):
        ws = self.workspace
        with self.navigation():
            ws.select("Job")
            ws.program_tasks.show(self.task)
        deck = ws.program_tasks
        deck.generation += 1  # Retire an older inspect-line reveal, including same-task returns.
        generation = deck.generation
        ws.navigation.restore_generation += 1
        navigation_generation = ws.navigation.restore_generation
        scroll, viewport = deck.scroll, deck.scroll._viewport
        callback = lambda *_: self.cancel("Scroll changed after assignment; current position retained.")
        self._scroll_binding = scroll, callback
        scroll.bind(scroll_y=callback)
        attempts = 0

        def attempt_restore(_dt):
            nonlocal attempts
            self._return_event = None
            attempts += 1
            try:
                self._require_origin()
            except ValueError:
                self.cancel()
                return
            if (
                attempts > 120
                or ws.active_section != "Job"
                or deck.active != self.task
                or deck.generation != generation
                or ws.navigation.restore_generation != navigation_generation
                or deck.scroll is not scroll
                or scroll._viewport is not viewport
                or viewport is None
                or viewport.parent is not scroll
            ):
                self.cancel()
                return
            pending = list(viewport.walk(restrict=True)) + [scroll]
            if any(
                getattr(getattr(item, trigger, None), "is_triggered", False)
                for item in pending
                for trigger in ("_trigger_layout", "_trigger_texture")
            ):
                self._return_event = Clock.schedule_once(restore, 0)
                return
            self._cancel_return()
            Animation.cancel_all(scroll, "scroll_x", "scroll_y")
            if scroll.effect_y is not None:
                scroll.effect_y.velocity = 0
                scroll.effect_y.reset(-max(0, viewport.height - scroll.height) * self.position)
            scroll.scroll_y = self.position
            self.active = False
            self._unbind_origin()
            self.library.refresh_context_action()

        def restore(dt):
            try:
                attempt_restore(dt)
            except Exception as exc:
                self._return_failed(exc)

        self._return_event = Clock.schedule_once(restore, 0)
