"""Identity-bound spreadsheet exchange and selection for saved nominal cutters."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from carveracontroller.machine.desktop_profiles import ProfileError, validate_record
from carveracontroller.machine.quantities import parse_quantity

# Header names are also the exchange schema. ID is stable across sorting/filtering.
COLUMNS = (
    ("name", "Name", 250),
    ("number", "Tool", 70),
    ("diameter", "Diameter", 110),
    ("shank_diameter", "Shank", 110),
    ("length", "Overall", 110),
    ("flute_length", "Cutting", 110),
    ("stickout", "Stickout", 110),
    ("vendor", "Vendor", 150),
    ("product_id", "Part number", 180),
    ("shape", "Shape", 170),
    ("id", "ID", 180),
)
DIMENSIONS = {"diameter", "shank_diameter", "length", "flute_length", "stickout"}
HEADERS = {title.casefold(): key for key, title, _ in COLUMNS}
HEADERS.update({key: key for key, _, _ in COLUMNS})


def cell_text(record, key):
    value = record.get(key)
    if value is None:
        return ""
    return f"{value:g}" if type(value) in (int, float) else str(value)


def export_tsv(records):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow([title for _, title, _ in COLUMNS])
    writer.writerows([cell_text(record, key) for key, _, _ in COLUMNS] for record in records)
    return stream.getvalue()


@dataclass(frozen=True)
class CutterChange:
    before: dict
    after: dict
    fields: tuple


def review_tsv(text, records):
    """Validate the complete paste before returning any change; never infer row IDs."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2 * 1024 * 1024:
        raise ProfileError("Paste is limited to 2 MiB")
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter="\t", strict=True))
    except csv.Error as exc:
        raise ProfileError(f"Invalid tab-separated text: {exc}") from exc
    if len(rows) < 2 or len(rows) > 1001:
        raise ProfileError("Include a header and 1–1000 cutter rows")
    keys = []
    for header in rows[0]:
        key = HEADERS.get(header.strip().casefold())
        if key is None:
            raise ProfileError(f"Unknown column: {header}")
        if key in keys:
            raise ProfileError(f"Duplicate column: {header}")
        keys.append(key)
    if "id" not in keys or len(keys) < 2:
        raise ProfileError("Include ID and at least one editable column; copy rows to obtain their IDs")
    available = {item["id"]: validate_record("tools", item) for item in records}
    seen, changes = set(), []
    for row_number, row in enumerate(rows[1:], 2):
        if len(row) != len(keys):
            raise ProfileError(f"Row {row_number}: expected {len(keys)} columns, received {len(row)}")
        values = dict(zip(keys, row))
        identity = values.pop("id").strip()
        if identity not in available:
            raise ProfileError(f"Row {row_number}: unknown cutter ID {identity!r}")
        if identity in seen:
            raise ProfileError(f"Row {row_number}: duplicate cutter ID {identity!r}")
        seen.add(identity)
        before = available[identity]
        after = dict(before)
        try:
            for key, raw in values.items():
                raw = raw.strip()
                if key in DIMENSIONS:
                    after[key] = parse_quantity(raw, maximum=1000) if raw else None
                elif key == "number":
                    after[key] = int(parse_quantity(raw, "scalar", minimum=1, maximum=9999, integer=True))
                else:
                    after[key] = raw
            after = validate_record("tools", after)
        except ValueError as exc:
            raise ProfileError(f"Row {row_number} · {before['name']}: {exc}") from exc
        changed = tuple(key for key in keys if key != "id" and before[key] != after[key])
        if changed:
            changes.append(CutterChange(before, after, changed))
    return tuple(changes)


class TableSelection:
    """Stable IDs survive sort/filter changes; ranges use the current visible order."""

    def __init__(self):
        self.ids = set()
        self.current = None
        self.anchor = None

    def select(self, identity, order, *, toggle=False, extend=False):
        if identity not in order:
            return
        if extend and self.anchor in order:
            a, b = sorted((order.index(self.anchor), order.index(identity)))
            selected = set(order[a : b + 1])
            self.ids = self.ids | selected if toggle else selected
        elif toggle:
            self.ids.symmetric_difference_update({identity})
            self.anchor = identity
        else:
            self.ids = {identity}
            self.anchor = identity
        self.current = identity

    def reconcile(self, available):
        self.ids.intersection_update(available)
        if self.current not in available:
            self.current = None
        if self.anchor not in available:
            self.anchor = None
