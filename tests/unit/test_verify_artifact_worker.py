import sys
from pathlib import Path

import pytest

from scripts.verify_artifact_worker import probe


def test_actual_worker_answers_and_exits_with_retained_writer():
    worker = Path(__file__).parents[2] / "carveracontroller/machine/artifact_fs.py"
    result = probe([sys.executable, str(worker)])
    assert result["exit"] == 0 and result["stdin_retained"] and not result["file_created"]


def test_eof_dependent_worker_fails_bounded_probe():
    code = 'import sys; sys.stdin.buffer.read(); print(\'{"result": {}, "error": null}\')'
    with pytest.raises(ValueError, match="stdin remained open"):
        probe([sys.executable, "-c", code], timeout=0.2)


@pytest.mark.parametrize("code", ["print('invalid')", "print('{}')", "raise SystemExit(1)", "print('x'*70000)"])
def test_bad_response_never_becomes_package_proof(code):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        probe([sys.executable, "-c", code])
