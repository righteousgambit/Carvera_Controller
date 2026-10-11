"""Bound local tool CAD preparation; renderer publication stays on the UI thread."""

import threading
from copy import deepcopy

from kivy.clock import Clock

from carveracontroller.addons.tool_visualization.profile_loading import prepare_tool_profiles


class ToolProfileLoads:
    def __init__(self, workspace):
        self.workspace = workspace
        self.active = False
        self.pending = None
        self.generation = 0

    def identity(self):
        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        return (
            deepcopy(viewer.library_tool_table_mm),
            deepcopy(viewer.tool_table or {}),
            viewer.move_scale_by_positon,
            viewer.tool_unit_scale,
            deepcopy(viewer.assembly_preview_binding),
            ws._profile_scene_identity(),
            getattr(ws.app, "selected_local_filename", None),
            viewer.preview_tool_override,
        )

    def request(self, definitions, replace, publish, on_result=None):
        ws = self.workspace
        if ws._profile_load_closed:
            return False
        self.generation += 1
        request = self.generation, deepcopy(definitions), replace, self.identity(), publish, on_result
        if self.active:
            self.pending = request
        else:
            self.start(request)
        return True

    def start(self, request):
        generation, definitions, replace, identity, publish, on_result = request
        self.active = True
        existing, cam_tools, scale, units = identity[:4]

        def work():
            try:
                prepared = prepare_tool_profiles(definitions, existing, cam_tools, scale, units, replace)
                error = None
            except Exception as exc:
                prepared, error = None, str(exc)

            def finish(_dt):
                self.active = False
                pending, self.pending = self.pending, None
                ws = self.workspace
                if ws._profile_load_closed:
                    return
                if pending is not None:
                    self.start(pending)
                    return
                if generation != self.generation:
                    return
                message = error
                if message is None and identity != self.identity():
                    message = "Program, scene or tooling changed during preparation; load the profile again."
                if message is None:
                    try:
                        publish(prepared)
                    except Exception as exc:
                        message = str(exc)
                if message is not None:
                    ws.tool_library_summary.text = "Tool profile not loaded: " + message
                if on_result is not None:
                    on_result(message is None, message)

            Clock.schedule_once(finish, 0)

        threading.Thread(target=work, name="tool-profile-prepare", daemon=True).start()
