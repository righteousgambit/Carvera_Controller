"""Keep the request boundary identical to the protected transport validator."""

import itertools

import pytest

from carveracontroller.headless.arguments import remote_path as request_path
from carveracontroller.headless.link import remote_path as transport_path


def result(validator, value):
    try:
        return ("accepted", validator(value))
    except ValueError as exc:
        return ("rejected", str(exc))


@pytest.mark.parametrize(
    "value",
    [None, True, 1, b"/sd/gcodes/a", [], {}, "", "/sd/gcodes/a.ngc", "/sd/gcodes/sub/a.ngc"]
    + ["/sd/gcodes/" + "a" * n for n in (1, 79, 80, 81, 110, 111)]
    + ["/sd/gcodes/" + "folder/" * n + "file.ngc" for n in (1, 10, 13, 14, 15)]
    + ["/sd/gcodes/" + item for item in ("../a", ".", "..", "a..b", "a/b", "a//b", "a\\b", "a\nb", "a\0b", "é", "a b")],
)
def test_bounded_path_and_type_cases_match(value):
    assert result(request_path, value) == result(transport_path, value)


def test_generated_short_paths_and_ascii_controls_match():
    for chars in itertools.product("ab.-_/ ", repeat=3):
        value = "/sd/gcodes/" + "".join(chars)
        assert result(request_path, value) == result(transport_path, value)
    for code in range(128):
        value = "/sd/gcodes/a" + chr(code) + "b"
        assert result(request_path, value) == result(transport_path, value)
