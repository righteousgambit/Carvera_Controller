"""Native camera surfaces, sharing one texture and one read-only worker."""

from kivy.graphics import Color, Line
from kivy.graphics.texture import Texture
from kivy.uix.image import Image


class RegisteredCameraImage(Image):
    """Overlay source-image pixels within a contained, proportioned viewport."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.overlay_segments = ()
        self.overlay_image_size = None
        self.bind(pos=self.redraw_overlay, size=self.redraw_overlay, texture=self.redraw_overlay)

    def set_overlay(self, segments, image_size):
        self.overlay_segments = tuple(segments)
        self.overlay_image_size = image_size
        self.redraw_overlay()

    def image_pixel_to_local(self, pixel):
        if not self.texture or self.overlay_image_size != self.texture.size:
            return None
        width, height = self.texture.size
        scale = min(self.width / width, self.height / height)
        return (
            self.x + (self.width - width * scale) / 2 + pixel[0] * scale,
            self.y + (self.height - height * scale) / 2 + (height - pixel[1]) * scale,
        )

    def redraw_overlay(self, *_args):
        self.canvas.after.clear()
        if not self.texture or self.overlay_image_size != self.texture.size:
            return
        width, height = self.texture.size
        with self.canvas.after:
            Color(0.25, 0.95, 0.8, 0.95)
            for start, end in self.overlay_segments:
                # An out-of-frame endpoint is withheld rather than drawing over
                # neighbouring controller controls. Full clipping is handled by
                # the projection producer when needed.
                if not all(0 <= p[0] <= width and 0 <= p[1] <= height for p in (start, end)):
                    continue
                a, b = self.image_pixel_to_local(start), self.image_pixel_to_local(end)
                Line(points=(*a, *b), width=1.2)


class WebcamTexture:
    def __init__(self):
        self.sequence = None
        self.texture = None
        self.views = []

    def new_view(self):
        view = RegisteredCameraImage(texture=self.texture)
        # Set after initialization: Image's compatibility bindings can replace
        # a constructor fit_mode with scale-down, preventing upscaling.
        view.fit_mode = "contain"
        self.views.append(view)
        return view

    def update(self, frame):
        if frame is None:
            self.texture = None
            self.sequence = None
            for view in self.views:
                view.texture = None
            return
        if frame.sequence == self.sequence:
            return
        if self.texture is None or self.texture.size != frame.size:
            self.texture = Texture.create(size=frame.size, colorfmt="rgb")
            self.texture.flip_vertical()
        self.texture.blit_buffer(frame.pixels, colorfmt="rgb", bufferfmt="ubyte")
        self.sequence = frame.sequence
        for view in self.views:
            view.texture = self.texture
            view.canvas.ask_update()
