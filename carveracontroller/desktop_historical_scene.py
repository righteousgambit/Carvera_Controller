"""Publish prepared historical geometry locally; retain a reversible previous scene."""

SCENE_FIELDS = (
    "machine_setup",
    "repeat_stock_plan",
    "repeat_stock_index",
    "repeat_rest_geometries",
    "_repeat_stock_edges",
    "declared_playback",
    "_legacy_playback_rows",
    "_legacy_playback_hash",
    "machine_profile",
    "machine_profile_error",
    "machine_component_profiles",
    "workholding_offset_mm",
    "workholding_rotation_deg",
    "jaw_offset_mm",
    "library_tool_table_mm",
    "_tool_meshes",
    "_default_tool_mesh",
    "assembly_preview_binding",
    "preview_tool_override",
    "_rest_stock_geometry",
)


def capture_scene(viewer):
    return {name: getattr(viewer, name) for name in SCENE_FIELDS}


def publish_scene(viewer, values, geometry=None):
    previous = capture_scene(viewer)
    try:
        for name, value in values.items():
            setattr(viewer, name, value)
        _refresh(viewer, geometry)
    except Exception:
        for name, value in previous.items():
            setattr(viewer, name, value)
        _refresh(viewer)
        raise
    return previous


def _refresh(viewer, geometry=None):
    viewer.refresh_declared_playback()
    viewer._machine_pose = viewer._machine_pose_for((0, 0, 0))
    if viewer.machine_visible:
        viewer._build_machine_scene(geometry)
    if viewer.pointer_mesh_instrs:
        viewer._active_tool_number = object()
        viewer._update_pointer_tool_mesh(int(getattr(viewer, "cur_line_index", 0)))
    viewer._scene_dirty = True
    viewer.canvas.ask_update()


def apply_historical_scene(viewer, prepared):
    if viewer.move_scale_by_positon != prepared.scale:
        raise ValueError("Preview scale changed during preparation")
    return publish_scene(
        viewer,
        {
            "machine_setup": prepared.setup,
            "repeat_stock_plan": None,
            "repeat_stock_index": None,
            "repeat_rest_geometries": None,
            "declared_playback": None,
            "_repeat_stock_edges": None,
            "machine_profile": prepared.profile,
            "machine_profile_error": None,
            "machine_component_profiles": prepared.components,
            "workholding_offset_mm": prepared.offset,
            "workholding_rotation_deg": prepared.rotation,
            "jaw_offset_mm": prepared.jaw,
            "library_tool_table_mm": prepared.definitions,
            "_tool_meshes": prepared.meshes,
            "_default_tool_mesh": prepared.fallback,
            "assembly_preview_binding": None,
            "preview_tool_override": None,
            "_rest_stock_geometry": None,
        },
        prepared.geometry,
    )


def prepare_previous_scene(previous, cam_tools, cam_scale, scale):
    """Rebuild for the current program scale on the artifact worker, never in a click."""
    from carveracontroller.addons.cad_identity import asset_digest
    from carveracontroller.addons.machine_simulation.model import build_scene
    from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_meshes

    definitions = previous["library_tool_table_mm"]
    for definition in definitions.values():
        for path_key, digest_key in (
            ("geometry_path", "geometry_sha256"),
            ("holder_geometry_path", "holder_geometry_sha256"),
        ):
            path, expected = getattr(definition, path_key), getattr(definition, digest_key)
            if path and expected and asset_digest(path) != expected:
                raise ValueError("Previous tool CAD changed; prior state remains retained")
    meshes, fallback = build_tool_meshes(cam_tools, scale=scale * cam_scale)
    library_meshes, _ = build_tool_meshes(definitions, scale=scale)
    meshes.update(library_meshes)
    profile, setup = previous["machine_profile"], previous["machine_setup"]
    args = (setup, previous["workholding_offset_mm"], previous["workholding_rotation_deg"], previous["jaw_offset_mm"])
    geometry = profile.scene(*args) if profile else build_scene(setup)
    for group, component in previous["machine_component_profiles"].items():
        geometry[group] = component.scene(*args)[group]
    if previous["_rest_stock_geometry"] is not None:
        geometry["stock"] = previous["_rest_stock_geometry"]
    from carveracontroller.machine.repeat_parts import repeat_stock_geometry

    geometry["repeat_stock"], edges = repeat_stock_geometry(
        previous["repeat_stock_plan"], previous["repeat_stock_index"], previous["repeat_rest_geometries"]
    )
    if previous["repeat_rest_geometries"] is not None:
        geometry["stock"] = previous["repeat_rest_geometries"][
            previous["repeat_stock_plan"].parts[previous["repeat_stock_index"]].wcs
        ]
    return {**previous, "_repeat_stock_edges": edges, "_tool_meshes": meshes, "_default_tool_mesh": fallback}, geometry
