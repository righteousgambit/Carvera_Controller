import struct
from unittest.mock import Mock

import pytest
import quicklz

from carveracontroller.machine.configuration_transfer import decode_configuration


def test_multiblock_config_round_trip():
    raw = b"alpha_steps_per_mm 200\n" * 300
    payload = bytearray()
    for offset in range(0, len(raw), 4096):
        block = quicklz.compress(raw[offset : offset + 4096])
        payload.extend(struct.pack(">I", len(block)) + block)
    payload.extend(struct.pack(">H", sum(raw) & 0xFFFF))
    assert decode_configuration(bytes(payload), quicklz.decompress) == raw


@pytest.mark.parametrize("payload", [b"\0\0", b"\0\0\0\x10abc\0\0", b"\0\0\0\x09\x4f\x09\0\0\0\xff\xff\xff\x7f\0\0"])
def test_bad_framing_never_enters_native_decoder(payload):
    decoder = Mock()
    with pytest.raises(ValueError):
        decode_configuration(payload, decoder)
    decoder.assert_not_called()
