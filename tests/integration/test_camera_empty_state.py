from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from PIL import Image, PngImagePlugin

from carveracontroller.webcam_view import WebcamTexture
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("size", [(600, 338), (320, 180)])
def test_missing_camera_receipt_is_explained_and_never_draws_white_rectangle(tmp_path, size):
    shared = WebcamTexture()
    view = shared.new_view()
    card = BoxLayout(size_hint=(None, None), size=size)
    with card.canvas.before:
        Color(0.07, 0.09, 0.12, 1)
        Rectangle(pos=card.pos, size=card.size)
    card.add_widget(view)
    view.empty_text = "Recorded camera · Outside retained camera receipts"
    pump_frames(5)
    assert view.empty_label.opacity == 1
    assert view.empty_label.text == view.empty_text
    rendered = card.export_as_image().texture
    pixels = Image.frombytes("RGBA", rendered.size, rendered.pixels)
    assert PngImagePlugin is not None
    pixels.save(tmp_path / f"camera-empty-{size[0]}.png", format="PNG")
    # Check the rendered surface, not only widget properties: an untextured
    # Image used to obscure essentially the entire pane with opaque white.
    raw = pixels.tobytes()
    bright = sum(min(raw[index : index + 3]) > 240 for index in range(0, len(raw), 4))
    assert bright / (pixels.width * pixels.height) < 0.01

    frame = SimpleNamespace(sequence=7, size=(4, 3), pixels=bytes((20, 80, 120)) * 12)
    shared.update(frame)
    pump_frames(3)
    assert view.texture is not None and view.empty_label.opacity == 0
    assert view.color[3] == 1
    rendered = card.export_as_image().texture
    pixels = Image.frombytes("RGBA", rendered.size, rendered.pixels)
    assert pixels.getpixel((pixels.width // 2, pixels.height // 2))[:3] == (20, 80, 120)
    shared.update(None)
    pump_frames(3)
    assert view.texture is None and view.empty_label.opacity == 1
    assert view.image_pixel_to_local((1, 1)) is None
    # Replaying the same frame after a gap must restore visibility as well.
    shared.update(frame)
    assert view.texture is not None and view.empty_label.opacity == 0
    later = shared.new_view()
    assert later.texture is view.texture and later.empty_label.opacity == 0


def test_workspace_empty_camera_status_does_not_claim_a_received_frame():
    from carveracontroller.desktop_workspace import DesktopWorkspace

    shared = WebcamTexture()
    view = shared.new_view()
    label = SimpleNamespace(text="", color=None)
    workspace = SimpleNamespace(
        camera_client=SimpleNamespace(snapshot=lambda: (True, None, None)),
        camera_status_labels=[label],
        camera_toggle=SimpleNamespace(text=""),
        workspaces=SimpleNamespace(current="Job"),
        camera_texture=shared,
        _layout_media=Mock(),
    )
    DesktopWorkspace._refresh_camera(workspace)
    assert label.text == view.empty_text == "Waiting for a camera image"
    assert view.texture is None and view.empty_label.opacity == 1
    workspace.run_recording_panel = SimpleNamespace(
        camera_replay_enabled=True,
        recorded_camera_frame=None,
        camera_replay_status="Recorded camera · Camera receipt gap or source boundary",
    )
    DesktopWorkspace._refresh_camera(workspace)
    assert label.text == view.empty_text == workspace.run_recording_panel.camera_replay_status
    assert view.texture is None and view.empty_label.opacity == 1
