"""A pixel witness must not contaminate the next native latency observation."""

import pytest

from tools.native_texture_snapshot import texture_red_varies


@pytest.mark.parametrize(
    ("pixels", "expected"),
    [
        (b"", False),
        (bytes((4, 2, 3, 255)) * 100_000, False),
        (bytes((4, 2, 3, 255, 4, 99, 99, 0)), False),
        (bytes((0, 2, 3, 255)) * 100_000 + bytes((1, 2, 3, 255)), True),
    ],
)
def test_one_readback_preserves_the_complete_red_witness(pixels, expected):
    class NativeReadback:
        reads = 0

        @property
        def pixels(self):
            self.reads += 1
            if self.reads > 1:
                raise AssertionError("Repeated readback would allocate another native FBO")
            return pixels

    texture = NativeReadback()
    assert texture_red_varies(texture) is expected
    assert texture.reads == 1


def test_readback_failure_is_not_reported_as_a_completed_pixel_witness():
    class RefusedReadback:
        @property
        def pixels(self):
            raise RuntimeError("Native readback refused")

    with pytest.raises(RuntimeError, match="Native readback refused"):
        texture_red_varies(RefusedReadback())
