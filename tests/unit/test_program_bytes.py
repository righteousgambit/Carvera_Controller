from hashlib import sha256

import pytest

from carveracontroller.machine.program_bytes import preview_digest, read_program_bytes, selected_preview_identity
from carveracontroller.machine.run_recording import selected_context


@pytest.mark.parametrize("raw", [b"G21\nG1 X1\n", b"G21\r\nG1 X1\r\n", b"G21\rG1 X1\r"])
def test_review_matches_normalized_preview_but_preserves_exact_raw_bytes(tmp_path, raw):
    path = tmp_path / "job.cnc"
    path.write_bytes(raw)
    digest = sha256(b"G21\nG1 X1\n").hexdigest()
    assert read_program_bytes(path, expected_preview=digest) == raw
    assert preview_digest(raw) == digest


def test_changed_file_with_same_size_is_rejected_for_recording_and_later_effects(tmp_path):
    path = tmp_path / "job.cnc"
    path.write_bytes(b"G20\n")
    expected = preview_digest(b"G21\n")
    with pytest.raises(ValueError, match="differ from the reviewed"):
        read_program_bytes(path, expected_preview=expected)
    with pytest.raises(ValueError, match="differ from the reviewed"):
        selected_context(path, {}, expected_preview=expected)


def test_budget_is_checked_on_the_actual_read_not_stat(tmp_path):
    path = tmp_path / "job.cnc"
    path.write_bytes(b"G21\n")
    with pytest.raises(ValueError, match="byte budget"):
        read_program_bytes(path, maximum=3)


def test_unreviewed_binary_file_is_permitted_without_claiming_preview_identity(tmp_path):
    path = tmp_path / "firmware.bin"
    raw = b"\xff\x00\xfe"
    path.write_bytes(raw)
    assert read_program_bytes(path) == raw
    with pytest.raises(UnicodeDecodeError):
        read_program_bytes(path, expected_preview="0" * 64)


def test_digest_does_not_follow_an_incomplete_or_different_selection():
    digest = "a" * 64
    assert selected_preview_identity("new.cnc", "", "old.cnc", digest) is None
    assert selected_preview_identity("new.cnc", "", None, digest) is None
    assert selected_preview_identity("new.cnc", "", "new.cnc", digest) == digest
    assert selected_preview_identity("cache.cnc", "/sd/job.cnc", "/sd/job.cnc", digest) == digest
