"""Bounded configuration decoding without passing machine input to native code."""

from __future__ import annotations

import struct

MAX_CONFIG_BYTES = 1024 * 1024


def _decode_block(block: bytes) -> bytes:
    """Decode the nonstreaming level-3 QuickLZ 1.4 format used by C1/CA1.

    Token layout follows QuickLZ 1.4.1's level-3 format. Unlike its native
    fast-read/copy implementation, every read and overlapping copy is bounded.
    Other levels need different history tables and are rejected explicitly.
    """
    flag = block[0]
    if flag & 0xFC != 0x4C:  # 01SSLLHC: version marker, no streaming, level 3.
        raise ValueError("Unsupported QuickLZ configuration mode")
    wide = bool(flag & 2)
    header_size = 9 if wide else 3
    if len(block) < header_size:
        raise ValueError("Truncated QuickLZ header")
    packed = int.from_bytes(block[1:5], "little") if wide else block[1]
    unpacked = int.from_bytes(block[5:9], "little") if wide else block[2]
    if packed != len(block) or not 1 <= unpacked <= 4096:
        raise ValueError("Invalid QuickLZ configuration lengths")
    if not flag & 1:
        if len(block) - header_size != unpacked:
            raise ValueError("Invalid QuickLZ raw payload length")
        return block[header_size:]

    offset = header_size
    output = bytearray()
    control = 1
    while len(output) < unpacked:
        if control == 1:
            if len(block) - offset < 4:
                raise ValueError("Truncated QuickLZ control word")
            control = int.from_bytes(block[offset : offset + 4], "little")
            offset += 4
            if not control & 0x80000000:
                raise ValueError("Invalid QuickLZ control word sentinel")
        if offset >= len(block):
            raise ValueError("Truncated QuickLZ token")
        if control & 1:
            first = block[offset]
            if first & 3 == 0:
                token_size, length, distance = 1, 3, first >> 2
            else:
                if first & 2 == 0 or first & 1 == 0:
                    token_size = 2
                elif first & 127 != 3:
                    token_size = 3
                else:
                    token_size = 4
                if len(block) - offset < token_size:
                    raise ValueError("Truncated QuickLZ match token")
                token = int.from_bytes(block[offset : offset + token_size], "little")
                if first & 2 == 0:
                    length, distance = 3, token >> 2
                elif first & 1 == 0:
                    length, distance = ((token >> 2) & 15) + 3, token >> 6
                elif first & 127 != 3:
                    length, distance = ((token >> 2) & 31) + 2, (token >> 7) & 0x1FFFF
                else:
                    length, distance = ((token >> 7) & 255) + 3, token >> 15
            if distance < 3 or distance > len(output):
                raise ValueError("Invalid QuickLZ backreference")
            # The compressor starts matches at least 11 bytes before the end
            # and leaves four literal bytes after the final match.
            if length > 255 or len(output) > unpacked - 11 or len(output) + length > unpacked - 4:
                raise ValueError("QuickLZ match exceeds output boundary")
            for _ in range(length):
                output.append(output[-distance])
            offset += token_size
        else:
            output.append(block[offset])
            offset += 1
        control >>= 1

    # The 1.4 compressor pads tiny compressed payloads to nine bytes for its
    # size functions. These are the only permitted unconsumed bytes.
    if len(block) - header_size < 9:
        raise ValueError("Truncated QuickLZ minimum payload padding")
    if offset != len(block) and not (offset - header_size < 9 and len(block) - header_size == 9):
        raise ValueError("Trailing QuickLZ payload bytes")
    return bytes(output)


def decode_configuration(payload: bytes) -> bytes:
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
        raw = _decode_block(block)
        if len(result) + len(raw) > MAX_CONFIG_BYTES:
            raise ValueError("Decoded configuration exceeds size limit")
        result.extend(raw)
    if offset != len(payload) - 2 or not result:
        raise ValueError("Truncated configuration checksum")
    if struct.unpack_from(">H", payload, offset)[0] != sum(result) & 0xFFFF:
        raise ValueError("Configuration checksum mismatch")
    return bytes(result)
