import pytest

from carveracontroller.machine.release_notes import note_pages


@pytest.mark.parametrize("text", ["", "é🙂\r\n" * 1000, "x" * 20000, "\n" * 1000, "one\ntwo\nthree"])
def test_pages_preserve_every_character_and_bound_layout_work(text):
    pages = note_pages(text, max_chars=100, max_lines=4)
    assert "".join(pages) == text
    assert all(len(page) <= 100 and page.count("\n") <= 4 for page in pages)
    assert pages and (text or pages == [""])


@pytest.mark.parametrize("chars,lines", [(0, 4), (4, 0), (-1, 4)])
def test_invalid_limits_are_rejected(chars, lines):
    with pytest.raises(ValueError):
        note_pages("notes", chars, lines)
