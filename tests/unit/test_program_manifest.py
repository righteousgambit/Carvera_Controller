"""Retained raw and parsed source are different evidence identities."""

import hashlib

import pytest

from carveracontroller.machine.program_manifest import prepare_program_manifest


def test_raw_crlf_identity_and_normalized_source_identity(tmp_path):
    raw = b"(operation: Face)\r\nG21\r\n"
    lines = ["(operation: Face)\n", "G21\n"]
    manifest = prepare_program_manifest(str(tmp_path / "missing.nc"), raw, lines)
    assert manifest.sha256 == hashlib.sha256(raw).hexdigest()
    assert manifest.parsed_lines_sha256 == hashlib.sha256("".join(lines).encode()).hexdigest()
    assert manifest.sha256 != manifest.parsed_lines_sha256
    record = manifest.to_record()
    assert record["operations"][0]["name"] == "Face"
    assert record["machine_file_identity"] == "unverified"
    assert record["requested_machine_path"] is None and record["request"] is None
    record["operations"].clear()
    assert len(manifest.operations) == 1
    assert not (tmp_path / "missing.nc").exists()


def test_operation_retention_and_cancellation():
    lines = [f"(operation: pass {i})\n" for i in range(4100)]
    manifest = prepare_program_manifest("retained.nc", "".join(lines).encode(), lines)
    record = manifest.to_record()
    assert record["operation_count"] == 4100 and record["operations_dropped"] == 4
    assert len(record["operations"]) == 4096 and record["operations"][0]["line"] == 5
    with pytest.raises(InterruptedError):
        prepare_program_manifest("retained.nc", b"", [], cancelled=lambda: True)


def test_mismatched_raw_bytes_cannot_be_claimed_by_parsed_manifest():
    with pytest.raises(ValueError, match="do not match"):
        prepare_program_manifest("retained.nc", b"G20\n", ["G21\n"])
