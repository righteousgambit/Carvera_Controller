from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.machine.window_geometry import save_logical_window_size


def test_window_restore_retains_logical_dimensions_across_framebuffer_and_widget_scales():
    config = {}
    sink = SimpleNamespace(set=lambda section, key, value: config.__setitem__((section, key), value))
    # A 2x Retina framebuffer and arbitrary widget scale must not affect config.
    for framebuffer_scale in (2, 3, 1, 2):
        window = SimpleNamespace(system_size=(1353, 827), size=(1353 * framebuffer_scale, 827 * framebuffer_scale))
        save_logical_window_size(sink, window)
        assert (config["graphics", "width"], config["graphics", "height"]) == (1353, 827)


@pytest.mark.parametrize("size", [(0, 100), (100, float("nan")), (True, 100), (100, float("inf"))])
def test_invalid_dimensions_do_not_partially_write(size):
    config = SimpleNamespace(set=Mock())
    with pytest.raises(ValueError):
        save_logical_window_size(config, SimpleNamespace(system_size=size))
    config.set.assert_not_called()
