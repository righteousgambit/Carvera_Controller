"""Bind saved display planes to declared setup/CAD identity, never hardware."""

from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.machine.section_view import SectionClip
from carveracontroller.machine.simulation_bookmarks import revision_hash
from carveracontroller.machine.workspace_layouts import validate_cutaway_state


def cutaway_setup_hash(workspace):
    viewer = workspace.machine.gcode_viewer
    selected = workspace.selected_machine_profile
    scene = capture_scene_setup(workspace)
    # Display visibility/framing and cutter selection do not change a nominal
    # machine component's section frame.
    scene.pop("visibility")
    scene.pop("scope")
    scene["choices"].pop("cutter")
    return revision_hash(
        {
            "machine_profile_id": selected["id"] if selected else None,
            "scene": scene,
            "machine_cad": viewer.machine_profile.geometry_sha256 if viewer.machine_profile else None,
            "component_cad": {
                key: profile.geometry_sha256 for key, profile in viewer.machine_component_profiles.items()
            },
        }
    )


def capture_cutaways(workspace):
    return validate_cutaway_state(
        {
            "setup_sha256": cutaway_setup_hash(workspace),
            "planes": {
                key: {"axis": clip.axis, "coordinate_mm": clip.coordinate_mm, "keep_above": clip.keep_above}
                for key, clip in workspace.machine.gcode_viewer.component_cutaways.items()
            },
        }
    )


def prepare_cutaways(workspace, value):
    state = validate_cutaway_state(value)
    if state is None:
        return {}
    if state["planes"] and state["setup_sha256"] != cutaway_setup_hash(workspace):
        raise ValueError("Saved section planes belong to another setup or CAD revision; restore that setup first")
    viewer = workspace.machine.gcode_viewer
    clips = {
        key: SectionClip(raw["axis"], raw["coordinate_mm"], raw["keep_above"]) for key, raw in state["planes"].items()
    }
    for clip in clips.values():
        clip.shader_plane(viewer.machine_setup.work_offset_mm, viewer.move_scale_by_positon or 1)
    return clips


def restore_cutaways(workspace, clips):
    viewer = workspace.machine.gcode_viewer
    viewer.component_cutaways = dict(clips)
    viewer._update_cutaway_uniforms()
    viewer._scene_dirty = True
    viewer.canvas.ask_update()
    panel = workspace.object_inspector.section_panel
    panel.selection = None
    panel.refresh()
