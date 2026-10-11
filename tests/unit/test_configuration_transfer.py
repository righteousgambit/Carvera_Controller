import random
import struct

import pytest
import quicklz

from carveracontroller.machine.configuration_transfer import MAX_CONFIG_BYTES, decode_configuration


def envelope(block, checksum=0):
    return struct.pack(">I", len(block)) + block + struct.pack(">H", checksum & 0xFFFF)


def wide_block(data, unpacked, flag=0x4F):
    return bytes([flag]) + struct.pack("<II", len(data) + 9, unpacked) + data


def test_multiblock_config_round_trip():
    raw = b"alpha_steps_per_mm 200\n" * 300
    payload = bytearray()
    for offset in range(0, len(raw), 4096):
        block = quicklz.compress(raw[offset : offset + 4096])
        payload.extend(struct.pack(">I", len(block)) + block)
    payload.extend(struct.pack(">H", sum(raw) & 0xFFFF))
    assert decode_configuration(bytes(payload)) == raw


@pytest.mark.parametrize("payload", [b"\0\0", b"\0\0\0\x10abc\0\0", b"\0\0\0\x09\x4f\x09\0\0\0\xff\xff\xff\x7f\0\0"])
def test_bad_framing_rejected(payload):
    with pytest.raises(ValueError):
        decode_configuration(payload)


@pytest.mark.parametrize("flag", [0x4E, 0x4F])
def test_missing_raw_or_compressed_payload_is_rejected(flag):
    # The original framing passed these blocks to an unchecked native decoder.
    with pytest.raises(ValueError, match="raw payload|control word"):
        decode_configuration(envelope(wide_block(b"", 4096, flag)))


@pytest.mark.parametrize(
    ("data", "size", "error"),
    [
        (b"\0\0\0", 32, "control word"),
        (b"\0\0\0\0" + b"a" * 32, 32, "sentinel"),
        (struct.pack("<I", 0x80000001), 32, "token"),
        (struct.pack("<I", 0x80000001) + b"\x01", 32, "match token"),
        (struct.pack("<I", 0x80000001) + b"\x07\0", 32, "match token"),
        (struct.pack("<I", 0x80000001) + b"\x03\0\0", 32, "match token"),
        (struct.pack("<I", 0x80000001) + b"\0", 32, "backreference"),
        (struct.pack("<I", 0x80000001) + b"\x0c", 32, "backreference"),
        (struct.pack("<I", 0x80000008) + b"abc\x08", 32, "backreference"),
        (struct.pack("<I", 0x80000008) + b"abc" + struct.pack("<I", (3 << 15) | (31 << 7) | 3), 20, "output boundary"),
        (struct.pack("<I", 0x80000000) + b"a" * 31, 32, "control word"),
        (struct.pack("<II", 0x80000000, 0x80000000) + b"ab", 50, "token"),
        (struct.pack("<I", 0x80000000) + b"a" * 11 + b"extra", 11, "Trailing"),
    ],
)
def test_invalid_compressed_tokens_are_bounded(data, size, error):
    with pytest.raises(ValueError, match=error):
        decode_configuration(envelope(wide_block(data, size)))


@pytest.mark.parametrize("flag", [0x40, 0x44, 0x48, 0x5C, 0x6C, 0x7C, 0xCC, 0x0C])
def test_unsupported_compression_level_streaming_or_version(flag):
    with pytest.raises(ValueError, match="Unsupported"):
        decode_configuration(envelope(wide_block(b"abc", 3, flag | 2), sum(b"abc")))


@pytest.mark.parametrize("data", [b"ab", b"abcd"])
def test_raw_payload_requires_exact_size(data):
    with pytest.raises(ValueError, match="raw payload length"):
        decode_configuration(envelope(wide_block(data, 3, 0x4E)))


def test_truncated_minimum_payload_padding():
    with pytest.raises(ValueError, match="padding"):
        decode_configuration(envelope(wide_block(struct.pack("<I", 0x80000000) + b"a", 1), ord("a")))


@pytest.mark.parametrize(
    ("token", "length"),
    [
        (b"\x0c", 3),
        (struct.pack("<H", (3 << 2) | 1), 3),
        (struct.pack("<H", (3 << 6) | (1 << 2) | 2), 4),
        (((3 << 7) | (17 << 2) | 3).to_bytes(3, "little"), 19),
        (struct.pack("<I", (3 << 15) | (31 << 7) | 3), 34),
    ],
)
def test_all_level_three_token_forms_and_overlapping_copy(token, length):
    expected = b"abc" + (b"abc" * 12)[:length] + b"tail-end"
    data = struct.pack("<I", 0x80000008) + b"abc" + token + b"tail-end"
    assert decode_configuration(envelope(wide_block(data, len(expected)), sum(expected))) == expected


def test_checksum_and_decoded_limits():
    with pytest.raises(ValueError, match="checksum mismatch"):
        decode_configuration(envelope(wide_block(b"abc", 3, 0x4E)))
    with pytest.raises(ValueError, match="size limit"):
        decode_configuration(b"a" * (MAX_CONFIG_BYTES + 1))
    block = quicklz.compress(b"a" * 4096)
    payload = (struct.pack(">I", len(block)) + block) * 257 + b"\0\0"
    with pytest.raises(ValueError, match="Decoded configuration exceeds"):
        decode_configuration(payload)


def test_valid_native_compressor_corpus_matches_native_decoder(monkeypatch):
    # Native decoding is used only on known-valid compressor output as an
    # independent parity oracle, never on machine or malformed input.
    rng = random.Random(338)
    sizes = list(range(1, 260)) + [511, 1024, 4095, 4096]
    corpus = [rng.randbytes(size) for size in sizes]
    corpus += [b"a" * size for size in sizes]
    corpus += [(b"alpha_steps_per_mm 200\n" * 200)[:size] for size in sizes]
    corpus += [bytes(rng.randrange(8) for _ in range(size)) for size in sizes]
    cases = [(raw, quicklz.compress(raw)) for raw in corpus]
    assert any(not block[0] & 1 for _, block in cases)
    assert all(quicklz.decompress(block) == raw for raw, block in cases)

    def native_decoder_forbidden(*_):
        pytest.fail("Configuration path called the native decoder")

    monkeypatch.setattr(quicklz, "decompress", native_decoder_forbidden)
    for raw, block in cases:
        assert decode_configuration(envelope(block, sum(raw))) == raw


def test_mutated_blocks_never_escape_bounded_python_errors(monkeypatch):
    raw = b"alpha_steps_per_mm 200\n" * 180
    block = quicklz.compress(raw)
    rng = random.Random(339)
    mutations = [block[:end] for end in range(3, len(block))]
    for _ in range(1000):
        changed = bytearray(block)
        changed[rng.randrange(len(changed))] ^= 1 << rng.randrange(8)
        mutations.append(bytes(changed))

    def native_decoder_forbidden(*_):
        pytest.fail("Malformed configuration reached native decoding")

    monkeypatch.setattr(quicklz, "decompress", native_decoder_forbidden)
    for changed in mutations:
        try:
            result = decode_configuration(envelope(changed, sum(raw)))
        except ValueError:
            continue
        assert len(result) <= 4096
