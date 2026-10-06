"""Native camera surfaces, sharing one texture and one read-only worker."""

from kivy.graphics import Color, InstructionGroup, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView


class RegisteredCameraImage(FocusBehavior, StencilView):
    """Overlay source-image pixels within a contained, proportioned viewport."""

    texture = ObjectProperty(None, allownone=True)
    color = ListProperty([1, 1, 1, 1])
    fit_mode = StringProperty("contain")

    empty_text = StringProperty("Waiting for a camera image")

    def __init__(self, **kwargs):
        self.zoom = 1.0
        self.frame_center = (0.5, 0.5)
        self._drag_touch = None
        self.interactive = False
        kwargs.setdefault("is_focusable", False)
        super().__init__(**kwargs)
        self.image_ink = InstructionGroup()
        self.canvas.add(self.image_ink)
        self.overlay_ink = InstructionGroup()
        self.canvas.add(self.overlay_ink)
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
        self.bind(
            pos=self.redraw_overlay, size=self.redraw_overlay, texture=self.redraw_overlay, focus=self.redraw_overlay
        )
        self.redraw_overlay()

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

    def capture_framing(self):
        return {"zoom": self.zoom, "center_x": self.frame_center[0], "center_y": self.frame_center[1]}

    def restore_framing(self, value):
        from carveracontroller.machine.workspace_layouts import validate_camera_framing

        value = validate_camera_framing(value)
        self.zoom, self.frame_center = value["zoom"], (value["center_x"], value["center_y"])
        self.redraw_overlay()

    def reset_framing(self):
        self.restore_framing({"zoom": 1, "center_x": 0.5, "center_y": 0.5})

    def _image_rect(self):
        if not self.texture:
            return None
        width, height = self.texture.size
        scale = min(self.width / width, self.height / height) * self.zoom
        if scale <= 0:
            return None
        rw, rh = width * scale, height * scale
        # Keep the image against its viewport edges, without hiding letterboxing.
        cx = (
            max(self.width / (2 * rw), min(1 - self.width / (2 * rw), self.frame_center[0])) if rw > self.width else 0.5
        )
        cy = (
            max(self.height / (2 * rh), min(1 - self.height / (2 * rh), self.frame_center[1]))
            if rh > self.height
            else 0.5
        )
        self.frame_center = cx, cy
        return self.center_x - cx * rw, self.center_y - cy * rh, rw, rh, scale

    def zoom_by(self, factor, anchor=None):
        pixel = self.local_to_image_pixel(anchor) if anchor is not None else None
        self.zoom = min(8, max(1, self.zoom * factor))
        if pixel is not None:
            width, height = self.texture.size
            scale = min(self.width / width, self.height / height) * self.zoom
            self.frame_center = (
                (pixel[0] * scale + self.center_x - anchor[0]) / (width * scale),
                ((height - pixel[1]) * scale + self.center_y - anchor[1]) / (height * scale),
            )
        self.redraw_overlay()

    def image_pixel_to_local(self, pixel):
        if not self.texture or self.overlay_image_size != self.texture.size:
            return None
        rect = self._image_rect()
        if rect is None:
            return None
        left, bottom, _rw, _rh, scale = rect
        return left + pixel[0] * scale, bottom + (self.texture.height - pixel[1]) * scale

    def local_to_image_pixel(self, position):
        """Inverse framing transform; reject letterbox and out-of-viewport picks."""
        rect = self._image_rect()
        if rect is None or not self.collide_point(*position):
            return None
        left, bottom, _rw, _rh, scale = rect
        width, height = self.texture.size
        u, v = (position[0] - left) / scale, height - (position[1] - bottom) / scale
        return (u, v) if 0 <= u < width and 0 <= v < height else None

    def redraw_overlay(self, *_args):
        self.image_ink.clear()
        self.overlay_ink.clear()
        rect = self._image_rect()
        if rect is None:
            return
        left, bottom, rw, rh, _scale = rect
        self.image_ink.add(Color(1, 1, 1, 1))
        self.image_ink.add(Rectangle(texture=self.texture, pos=(left, bottom), size=(rw, rh)))
        if self.focus:
            self.overlay_ink.add(Color(0.25, 0.95, 0.8, 0.95))
            self.overlay_ink.add(
                Line(rectangle=(self.x + 1, self.y + 1, max(0, self.width - 2), max(0, self.height - 2)), width=1.2)
            )
        if self.overlay_image_size != self.texture.size:
            return
        width, height = self.texture.size
        self.overlay_ink.add(Color(0.25, 0.95, 0.8, 0.95))
        for start, end in self.overlay_segments:
            if not all(0 <= p[0] <= width and 0 <= p[1] <= height for p in (start, end)):
                continue
            a, b = self.image_pixel_to_local(start), self.image_pixel_to_local(end)
            self.overlay_ink.add(Line(points=(*a, *b), width=1.2))

    def on_touch_down(self, touch):
        if not self.interactive or not self.texture or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        button = getattr(touch, "button", "left")
        if button in ("scrollup", "scrolldown"):
            self.zoom_by(1.25 if button == "scrollup" else 0.8, touch.pos)
            return True
        if button != "left":
            return super().on_touch_down(touch)
        self.focus = True
        FocusBehavior.ignored_touch.append(touch)
        if getattr(touch, "is_double_tap", False):
            self.reset_framing()
            return True
        self._drag_touch = touch
        self._drag_position = touch.pos
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch is self._drag_touch:
            rect = self._image_rect()
            if rect is not None:
                dx, dy = touch.x - self._drag_position[0], touch.y - self._drag_position[1]
                self._drag_position = touch.pos
                self.frame_center = self.frame_center[0] - dx / rect[2], self.frame_center[1] - dy / rect[3]
                self.redraw_overlay()
            return True
        return super().on_touch_move(touch)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if self.interactive and set(modifiers) <= {"shift"}:
            key = keycode[1]
            if key in ("+", "=", "plus", "equals", "numpadadd"):
                self.zoom_by(1.25)
                return True
            if key in ("-", "minus", "numpadsubtract"):
                self.zoom_by(0.8)
                return True
            if key in ("0", "home", "numpad0"):
                self.reset_framing()
                return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)

    def on_touch_up(self, touch):
        if touch is self._drag_touch:
            self._drag_touch = None
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)


class WebcamTexture:
    def __init__(self):
        self.sequence = None
        self.texture = None
        self.views = []

    def new_view(self, view_type=RegisteredCameraImage):
        view = view_type(texture=self.texture)
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
