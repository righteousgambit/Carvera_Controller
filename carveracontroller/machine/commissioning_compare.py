"""Historical HAL differences; never infer units, tuning authority or live state."""

from __future__ import annotations

import math
from dataclasses import dataclass

from carveracontroller.machine.commissioning_channels import ChannelPage, hal_group_items
from carveracontroller.machine.linuxcnc_hal import HalItem, HalObservation


@dataclass(frozen=True)
class HalDifference:
    name: str
    previous: HalItem | None
    current: HalItem | None
    change: str

    def summary(self) -> str:
        if self.previous is None or self.current is None:
            item = self.current or self.previous
            assert item is not None
            return f"{self.change} · {item.value} · {item.type_name} · {item.direction}"
        text = f"{self.change} · {self.previous.value} to {self.current.value}"
        if self.change == "value changed" and self.current.type_name != "bit":
            delta = self.current.value - self.previous.value
            if isinstance(delta, int) or math.isfinite(delta):
                text += f" · raw delta {delta:+}"
            else:
                text += " · raw delta exceeds finite range"
        return text

    def detail(self) -> str:
        lines = [self.name, self.summary()]
        for label, item in (("Reference", self.previous), ("Selected", self.current)):
            lines.append(
                f"{label}: {item.type_name} · {item.direction} · {item.value} · driver {item.driver or 'none'}"
                if item is not None
                else f"{label}: absent from captured group"
            )
        lines.append(
            "Historical separate group reads; raw values have no inferred physical units or tuning acceptance."
        )
        return "\n".join(lines)


def hal_differences(
    previous: HalObservation | None, current: HalObservation | None, group: str, query: str = ""
) -> tuple[tuple[HalDifference, ...], str]:
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError("HAL search must contain at most 256 characters")
    old, new = hal_group_items(previous, group), hal_group_items(current, group)
    if old is None or new is None:
        return (), "Comparison unavailable: this group was not captured in both samples"
    assert previous is not None and current is not None
    if previous.machine_id != current.machine_id or previous.generation != current.generation:
        return (), "Comparison unavailable: machine identity or reader generation differs"
    before, after = {item.name: item for item in old}, {item.name: item for item in new}
    results = []
    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name), after.get(name)
        if a == b:
            continue
        if a is None:
            change = "added"
        elif b is None:
            change = "removed"
        elif (a.type_name, a.direction, a.driver) != (b.type_name, b.direction, b.driver):
            change = "metadata changed"
        else:
            change = "value changed"
        result = HalDifference(name, a, b, change)
        searchable = " ".join([name, change, *(str(item) for item in (a, b) if item is not None)]).casefold()
        if all(token in searchable for token in query.casefold().split()):
            results.append(result)
    return tuple(results), "Historical comparison · changed items only · independent sample reads"


def difference_page(differences: tuple[HalDifference, ...], page: int) -> ChannelPage:
    if type(page) is not int:
        raise ValueError("Integer page required")
    total = len(differences)
    pages = max(1, (total + 15) // 16)
    index = min(max(page, 0), pages - 1)
    start, stop = index * 16, min(total, (index + 1) * 16)
    return ChannelPage(
        index,
        pages,
        total,
        start + 1 if total else 0,
        stop,
        tuple((item.name, item.summary()) for item in differences[start:stop]),
    )
