"""Bounded views over every recorded channel and recomputed transition."""

from __future__ import annotations

from dataclasses import dataclass

from carveracontroller.machine.linuxcnc_hal import HalItem, HalObservation
from carveracontroller.machine.linuxcnc_status import SignalTransition, StatusObservation

CHANNEL_GROUPS = (
    "Digital inputs",
    "Digital outputs",
    "Analog inputs",
    "Analog outputs",
    "Sample changes",
    "HAL pins",
    "HAL signals",
    "HAL parameters",
)


@dataclass(frozen=True)
class ChannelPage:
    index: int
    pages: int
    total: int
    first: int
    last: int
    rows: tuple[tuple[str, str], ...]


def hal_group_items(hal: HalObservation | None, group: str) -> tuple[HalItem, ...] | None:
    if group not in ("HAL pins", "HAL signals", "HAL parameters"):
        raise ValueError("HAL group required")
    if hal is None:
        return None
    return {"HAL pins": hal.pins, "HAL signals": hal.signals, "HAL parameters": hal.parameters}[group]


def matching_hal_items(hal: HalObservation | None, group: str, query: str) -> tuple[HalItem, ...]:
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError("HAL search must contain at most 256 characters")
    source = hal_group_items(hal, group) or ()
    tokens = query.casefold().split()
    return tuple(
        item
        for item in source
        if all(
            token in f"{item.name} {item.type_name} {item.direction} {item.driver or ''}".casefold() for token in tokens
        )
    )


def hal_item_detail(hal: HalObservation | None, group: str, selected: str) -> str:
    if hal is None:
        return "HAL was not captured in this recording"
    source = hal_group_items(hal, group)
    if source is None:
        return "HAL parameters were not captured in this recording"
    item = next((item for item in source if item.name == selected), None)
    if item is None:
        return "No selected HAL item in this sample"
    value = str(int(item.value)) if item.type_name == "bit" else str(item.value)
    text = f"{item.name}\nReported {item.type_name} value {value} · {item.direction}"
    if group == "HAL signals":
        text += f"\nReported driver: {item.driver or 'none'}"
        if item.driver is not None:
            driver = next((pin for pin in hal.pins if pin.name == item.driver), None)
            if driver is None:
                text += "\nDriver pin is absent from this captured pin list"
            else:
                text += f"\nCaptured driver: {driver.type_name} · {driver.direction} · value {driver.value}"
                if driver.type_name != item.type_name:
                    text += "\nSignal/driver types differ in this recording"
        text += "\nPin and signal groups were read separately; this is historical association only."
    if group == "HAL parameters":
        text += "\nHistorical parameter readback only; rw describes HAL metadata, not permission to edit.\nHAL groups were read separately; parameter/pin/signal values are not atomic."
    return text


def channel_page(
    observation: StatusObservation,
    changes: tuple[SignalTransition, ...],
    group: str,
    page: int = 0,
    hal: HalObservation | None = None,
    query: str = "",
) -> ChannelPage:
    if group not in CHANNEL_GROUPS or type(page) is not int:
        raise ValueError("Valid channel group and integer page required")
    values: tuple[float, ...]
    hal_items = matching_hal_items(hal, group, query) if group.startswith("HAL ") else ()
    if group.startswith("HAL "):
        total = len(hal_items)
        prefix, values = "", ()
    elif group == "Sample changes":
        total = len(changes)
        prefix, values = "", ()
    else:
        prefix, values = {
            "Digital inputs": ("din", observation.digital_inputs),
            "Digital outputs": ("dout", observation.digital_outputs),
            "Analog inputs": ("ain", observation.analog_inputs),
            "Analog outputs": ("aout", observation.analog_outputs),
        }[group]
        total = len(values)
    pages = max(1, (total + 15) // 16)
    index = min(max(0, page), pages - 1)
    start, stop = index * 16, min(total, (index + 1) * 16)
    rows = []
    for number in range(start, stop):
        if group.startswith("HAL "):
            item = hal_items[number]
            value_text = str(int(item.value)) if item.type_name == "bit" else str(item.value)
            metadata = f"driver {item.driver or 'none'}" if group == "HAL signals" else item.direction
            rows.append((item.name, f"{value_text} · {item.type_name} · {metadata}"))
        elif group == "Sample changes":
            event = changes[number]
            rows.append((event.signal, f"{int(event.previous)} to {int(event.current)}"))
        else:
            value = values[number]
            rows.append((f"{prefix}.{number}", str(int(value)) if prefix.startswith("d") else f"{value:g}"))
    return ChannelPage(index, pages, total, start + 1 if total else 0, stop, tuple(rows))
