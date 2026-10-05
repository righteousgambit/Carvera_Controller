"""Lossless bounded pages for remote release notes, including very long lines."""


def note_pages(text, max_chars=2048, max_lines=40):
    if max_chars < 1 or max_lines < 1:
        raise ValueError("Page limits must be positive")
    pages = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        cursor = start
        for _ in range(max_lines):
            newline = text.find("\n", cursor, end)
            if newline < 0:
                break
            cursor = newline + 1
        else:
            end = cursor
        pages.append(text[start:end])
        start = end
    return pages or [""]
