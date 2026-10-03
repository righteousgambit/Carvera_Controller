"""Native camera surfaces, sharing one texture and one read-only worker."""

from kivy.graphics.texture import Texture
from kivy.uix.image import Image


class WebcamTexture:
    def __init__(self):
        self.sequence = None
        self.texture = None
        self.views = []

    def new_view(self):
        view = Image(texture=self.texture)
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
