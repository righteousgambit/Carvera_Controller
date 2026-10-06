"""Bounded views over every recorded channel and recomputed transition."""

from __future__ import annotations

from dataclasses import dataclass

from carveracontroller.machine.linuxcnc_hal import HalObservation
from carveracontroller.machine.linuxcnc_status import SignalTransition, StatusObservation

CHANNEL_GROUPS = (
    "Digital inputs",
    "Digital outputs",
    "Analog inputs",
    "Analog outputs",
    "Sample changes",
    "HAL pins",
    "HAL signals",
)


@dataclass(frozen=True)
class ChannelPage:
    index: int
    pages: int
    total: int
    first: int
    last: int
    rows: tuple[tuple[str, str], ...]


def channel_page(
    observation: StatusObservation,
    changes: tuple[SignalTransition, ...],
    group: str,
    page: int = 0,
    hal: HalObservation | None = None,
) -> ChannelPage:
    if group not in CHANNEL_GROUPS or type(page) is not int:
        raise ValueError("Valid channel group and integer page required")
    values: tuple[float, ...]
    hal_items = () if hal is None else hal.pins if group == "HAL pins" else hal.signals
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
