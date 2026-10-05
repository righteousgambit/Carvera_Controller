"""Persist logical window dimensions independently of widget scaling or Retina pixels."""

import math


def save_logical_window_size(config, window):
    width, height = window.system_size
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 1 for v in (width, height)):
        raise ValueError("Window dimensions must be positive finite logical values")
    config.set("graphics", "width", int(width))
    config.set("graphics", "height", int(height))
