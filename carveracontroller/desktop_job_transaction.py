"""Recover one complete local job preview; never changes machine configuration."""

import io
import logging
from configparser import ConfigParser
from pathlib import Path

from kivy.config import Config

from carveracontroller.desktop_program_publication import _capture, _restore, capture_program_state
from carveracontroller.machine.atomic_preferences import merge_preference_updates, preference_bytes, replace_preferences
from carveracontroller.machine.program_manifest import PreparedProgramManifest

logger = logging.getLogger(__name__)
VIEWER_FIELDS = (
    "machine_setup",
    "machine_profile",
    "machine_profile_error",
    "workholding_offset_mm",
    "workholding_rotation_deg",
    "jaw_offset_mm",
    "repeat_stock_plan",
    "repeat_stock_index",
    "repeat_rest_geometries",
    "library_tool_table_mm",
    "assembly_preview_binding",
    "preview_tool_override",
    "machine_view_scope",
    "cutter_visible",
    "_machine_pose",
    "_machine_camera_saved",
)
WORKSPACE_FIELDS = (
    "selected_machine_profile",
    "loaded_toolset",
    "loaded_tool_profiles",
    "restored_job",
    "pending_job_rest_stock",
    "simulation_geometry",
    "_job_import_publication",
)


class LocalJobTransaction:
    def __init__(self, workspace, profile=None):
        self.workspace, self.profile = workspace, profile
        self.machine, self.viewer = workspace.machine, workspace.machine.gcode_viewer
        self.committed = self.active = False
        self.recovery_errors = []
        self.warning = ""
        self.manifest = None
        self.program_generation = None
        self.import_generation = getattr(workspace, "_job_import_generation", 0)
        self.connection_generation = getattr(self.machine.controller, "_connection_generation", None)
        self.restore_program = capture_program_state(self.machine, workspace.app)
        self.viewer_state = _capture(self.viewer, VIEWER_FIELDS)
        self.components = dict(self.viewer.machine_component_profiles)
        self.workspace_state = _capture(workspace, WORKSPACE_FIELDS)
        self.selection = self.machine.file_popup.local_rv.curr_selected_file
        self.visible = self.viewer.machine_visible
        self.restore_camera = workspace.camera_registration_panel.capture_import_state()
        self.restore_scene = workspace.capture_job_scene_controls()
        self.labels = []
        for name, fields in (
            ("selected_machine_label", ("text",)),
            ("profile_status", ("text",)),
            ("tool_library_summary", ("text", "height")),
            ("camera_url_input", ("text",)),
        ):
            widget = getattr(workspace, name, None)
            if widget is not None:
                self.labels.append((widget, _capture(widget, fields)))
        self.camera_configured = False
        self.camera_url = workspace.camera_client.url
        self.camera_enabled = workspace.camera_client.snapshot()[0]
        self.preference_values = {}
        self.preference_path = None
        self.preference_before = None
        if profile is not None:
            if not Config.filename:
                raise ValueError("No local preferences file is available for this machine profile")
            self.preference_path = Path(Config.filename)
            self.preference_before = preference_bytes(self.preference_path)
            self.preference_updates = {"desktop_machine_profile_id": profile["id"]}
            if profile["camera_url"]:
                self.preference_updates["webcam_snapshot_url"] = profile["camera_url"]
            self.preference_values = {
                key: Config.get("carvera", key, raw=True) if key in Config._sections.get("carvera", {}) else None
                for key in self.preference_updates
            }

    def __enter__(self):
        if getattr(self.workspace, "_job_apply_active", False):
            raise ValueError("Another local job is already being published")
        self.active = self.workspace._job_apply_active = True
        self.workspace._job_program_changed = False
        try:
            self.viewer.set_machine_visible(False)
        except Exception:
            try:
                self.rollback()
            finally:
                self.active = self.workspace._job_apply_active = False
                self.workspace._job_program_changed = False
            raise
        return self

    def stage_manifest(self, manifest):
        if not self.active or self.committed or not isinstance(manifest, PreparedProgramManifest):
            raise ValueError("Program evidence belongs to an active job publication")
        if self.manifest is not None:
            raise ValueError("Job program evidence was already staged")
        self.manifest = manifest
        self.program_generation = self.machine.program_preview_generation

    def commit(self):
        if not self.active or self.committed or self.manifest is None:
            raise ValueError("A complete local program is required before committing the job")
        if (
            self.viewer.loaded_program_hash != self.manifest.parsed_lines_sha256
            or self.workspace.app.selected_local_filename != self.manifest.local_path
            or self.workspace.app.selected_remote_filename
            or self.machine._last_loaded_file_key != self.manifest.local_path
            or self.machine.program_preview_generation != self.program_generation
            or getattr(self.workspace, "_job_import_generation", 0) != self.import_generation
            or getattr(self.machine.controller, "_connection_generation", None) != self.connection_generation
        ):
            raise ValueError("The job publication context or completed program changed; import again")
        self.viewer.set_machine_visible(self.visible)
        if self.profile and self.profile["camera_url"]:
            self.camera_configured = True
            self.workspace.camera_client.configure(self.profile["camera_url"])
            self.workspace.camera_url_input.text = self.profile["camera_url"]
        if self.preference_path is not None:
            if not Config.filename or Path(Config.filename) != self.preference_path:
                raise ValueError("Preference target changed during job publication; import again")
            for key, value in self.preference_updates.items():
                Config.set("carvera", key, value)
            baseline = b""
            if self.preference_before is None:
                text = io.StringIO()
                ConfigParser.write(Config, text)
                baseline = text.getvalue().encode("utf-8")
            content = merge_preference_updates(self.preference_before, baseline, self.preference_updates)
            replace_preferences(self.preference_path, self.preference_before, content)
        # Atomic preference replacement is the last fallible commit operation.
        # Later evidence/notification failures are reported, never called rollback.
        self.committed = True
        try:
            self.machine.controller.publish_prepared_program_source(self.manifest)
        except Exception:
            with self.machine.controller._adaptive_lock:
                self.machine.controller.run_evidence.program = None
            self.warning = "Program evidence unavailable; recording identity withheld."
            logger.exception(self.warning)

    def rollback(self):
        if self.committed:
            raise ValueError("A committed local job cannot be rolled back by a closed transaction")

        def recover(action):
            try:
                action()
            except Exception as exc:
                self.recovery_errors.append(str(exc) or type(exc).__name__)
                logger.exception("Local job recovery step failed")

        self.machine.program_preview_generation += 1
        recover(lambda: self.viewer.set_machine_visible(False))
        recover(lambda: _restore(self.viewer, self.viewer_state))
        self.viewer.machine_component_profiles = self.components
        recover(lambda: _restore(self.workspace, self.workspace_state))
        self.machine.file_popup.local_rv.curr_selected_file = self.selection
        recover(self.restore_camera)
        recover(self.restore_scene)
        for widget, fields in self.labels:
            recover(lambda widget=widget, fields=fields: _restore(widget, fields))
        if self.camera_configured or self.workspace.camera_client.url != self.camera_url:
            recover(lambda: self.workspace.camera_client.configure(self.camera_url))
            recover(lambda: self.workspace.camera_client.set_enabled(self.camera_enabled))
        for key, value in self.preference_values.items():
            if value is None:
                Config.remove_option("carvera", key)
            else:
                Config.set("carvera", key, value)

        def restore_display():
            if self.restore_program() is False:
                raise RuntimeError("Previous display could not be reconstructed")

        recover(restore_display)
        recover(self.workspace.camera_registration_panel.update_overlay)
        if self.recovery_errors:
            self.viewer.set_loaded_program_identity(None)

    def __exit__(self, kind, error, traceback):
        try:
            if not self.committed:
                self.rollback()
                if kind is None:
                    raise RuntimeError("Job publication ended without a commit")
        finally:
            self.active = self.workspace._job_apply_active = False
            pending = self.workspace._job_program_changed
            self.workspace._job_program_changed = False
        if self.committed and pending:
            try:
                self.workspace._program_changed(self.workspace.app, self.workspace.app.selected_local_filename)
            except Exception:
                self.warning += " Operation analysis unavailable for the committed preview."
                logger.exception("Job committed; operation-analysis notification failed")
        return False
