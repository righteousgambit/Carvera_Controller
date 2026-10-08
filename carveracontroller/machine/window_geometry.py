"""Persist logical window dimensions independently of widget scaling or Retina pixels."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol


class WindowConfiguration(Protocol):
    def set(self, section: str, option: str, value: int) -> None: ...


class LogicalWindow(Protocol):
    @property
    def system_size(self) -> Sequence[float]: ...


def save_logical_window_size(config: WindowConfiguration, window: LogicalWindow) -> None:
    width, height = window.system_size
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 1 for v in (width, height)):
        raise ValueError("Window dimensions must be positive finite logical values")
    config.set("graphics", "width", int(width))
    config.set("graphics", "height", int(height))
