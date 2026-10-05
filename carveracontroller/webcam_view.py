"""Native camera surfaces, sharing one texture and one read-only worker."""

from kivy.graphics import Color, Line
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.image import Image
from kivy.uix.label import Label


class RegisteredCameraImage(Image):
    """Overlay source-image pixels within a contained, proportioned viewport."""

    empty_text = StringProperty("Waiting for a camera image")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.empty_label = Label(
            text=self.empty_text,
            font_size=dp(14),
            color=(0.62, 0.69, 0.77, 1),
            halign="center",
            valign="middle",
            size_hint=(None, None),
        )
        self.add_widget(self.empty_label)
        self.bind(
            pos=self._refresh_empty_state,
            size=self._refresh_empty_state,
            texture=self._refresh_empty_state,
            empty_text=self._refresh_empty_state,
        )
        self._refresh_empty_state()
        self.overlay_segments = ()
        self.overlay_image_size = None
        self.bind(pos=self.redraw_overlay, size=self.redraw_overlay, texture=self.redraw_overlay)

    def _refresh_empty_state(self, *_args):
        # Kivy draws an untextured Image rectangle white unless it is transparent.
        # Withhold that rectangle and explain the missing image on the card.
        self.color = (*self.color[:3], 1 if self.texture is not None else 0)
        self.empty_label.text = self.empty_text
        self.empty_label.pos, self.empty_label.size = self.pos, self.size
        self.empty_label.text_size = (max(0, self.width - dp(32)), self.height)
        self.empty_label.opacity = 0 if self.texture is not None else 1

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

    def local_to_image_pixel(self, position):
        """Inverse contained-image mapping; clicks in the letterbox are rejected."""
        if not self.texture:
            return None
        width, height = self.texture.size
        scale = min(self.width / width, self.height / height)
        if scale <= 0:
            return None
        left = self.x + (self.width - width * scale) / 2
        bottom = self.y + (self.height - height * scale) / 2
        u, v = (position[0] - left) / scale, height - (position[1] - bottom) / scale
        return (u, v) if 0 <= u < width and 0 <= v < height else None

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
