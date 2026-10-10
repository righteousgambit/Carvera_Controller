"""Read a native texture once before checking the retained red-channel witness."""

from typing import Protocol


class PixelTexture(Protocol):
    @property
    def pixels(self) -> bytes: ...


def texture_red_varies(texture: PixelTexture) -> bool:
    """Preserve the original predicate without repeated GPU readback.

    Kivy Texture.pixels creates a temporary FBO on each access. Reading inside
    a per-pixel generator can queue thousands of GPU objects for cleanup during
    the next measured UI action. Evaluate the same predicate on one snapshot.
    """
    pixels = texture.pixels
    return any(pixels[index] != pixels[0] for index in range(0, len(pixels), 4))
