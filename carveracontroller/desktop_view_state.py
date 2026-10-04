"""Capture and restore validated local viewport state without machine commands."""

from carveracontroller.machine.simulation_bookmarks import VIEW_FIELDS, validate_view


def capture_view(viewer):
    view = {key: getattr(viewer, key) for key in VIEW_FIELDS}
    view["orthographic"] = viewer._ortho_projection
    return validate_view(view)


def restore_view(viewer, view):
    view = validate_view(view)
    for key in VIEW_FIELDS:
        setattr(viewer, key, view[key])
    viewer._ortho_projection = view["orthographic"]
    viewer.update_proj()
    viewer.update_view()
    viewer._scene_dirty = True
    viewer.canvas.ask_update()
