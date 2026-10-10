"""Pixel-positioned input through Kivy's real window and event loop.

Keep this test support in the repository: packaged Kivy runtimes need not
include Kivy's own test suite. Widget callbacks are never invoked directly.
"""

from itertools import count

from kivy.base import EventLoop
from kivy.input.motionevent import MotionEvent


class WindowTouch(MotionEvent):
    _ids = count()

    def __init__(self, x, y):
        window = EventLoop.window
        super().__init__(
            "repository-test",
            next(self._ids),
            (x / (window.width - 1), y / (window.height - 1)),
            is_touch=True,
            type_id="touch",
        )
        self.profile = ["pos", "button"]
        self.button = "left"

    def depack(self, args):
        self.sx, self.sy = (args["x"], args["y"]) if isinstance(args, dict) else args
        super().depack(args)

    def touch_down(self):
        EventLoop.post_dispatch_input("begin", self)

    def touch_move(self, x, y):
        window = EventLoop.window
        self.move((x / (window.width - 1), y / (window.height - 1)))
        EventLoop.post_dispatch_input("update", self)

    def touch_up(self):
        self.update_time_end()
        EventLoop.post_dispatch_input("end", self)
