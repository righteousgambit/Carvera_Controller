"""Bounded QuickLZ configuration framing before native decompression."""

from __future__ import annotations

import struct
from collections.abc import Callable

MAX_CONFIG_BYTES = 1024 * 1024


def decode_configuration(payload: bytes, decompress: Callable[[bytes], bytes]) -> bytes:
    if len(payload) > MAX_CONFIG_BYTES:
        raise ValueError("Configuration transfer exceeds size limit")
    if not payload.startswith(b"\x00\x00"):
        return payload
    result = bytearray()
    offset = 0
    while offset < len(payload) - 2:
        if len(payload) - offset < 6:
            raise ValueError("Truncated configuration block header")
        size = struct.unpack_from(">I", payload, offset)[0]
        offset += 4
        if not 3 <= size <= 8192 or size > len(payload) - offset - 2:
            raise ValueError("Invalid configuration block size")
        block = payload[offset : offset + size]
        offset += size
        wide = bool(block[0] & 2)
        header_size = 9 if wide else 3
        if size < header_size:
            raise ValueError("Truncated QuickLZ header")
        packed = int.from_bytes(block[1:5], "little") if wide else block[1]
        unpacked = int.from_bytes(block[5:9], "little") if wide else block[2]
        if packed != size or not 1 <= unpacked <= 4096 or len(result) + unpacked > MAX_CONFIG_BYTES:
            raise ValueError("Invalid QuickLZ configuration lengths")
        raw = decompress(block)
        if len(raw) != unpacked:
            raise ValueError("Decoded configuration block size mismatch")
        result.extend(raw)
    if offset != len(payload) - 2 or not result:
        raise ValueError("Truncated configuration checksum")
    if struct.unpack_from(">H", payload, offset)[0] != sum(result) & 0xFFFF:
        raise ValueError("Configuration checksum mismatch")
    return bytes(result)
