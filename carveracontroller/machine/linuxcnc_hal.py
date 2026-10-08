"""Optional read-only HAL metadata/value observations, never a component/writer.

https://www.linuxcnc.org/docs/stable/html/config/python-hal-interface.html
"""

from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Any

from carveracontroller.machine.linuxcnc_status import SignalTransition, finite, integer


@dataclass(frozen=True)
class HalItem:
    name: str
    type_name: str
    value: bool | int | float
    direction: str
    driver: str | None


@dataclass(frozen=True)
class HalObservation:
    machine_id: str
    observed_at: float
    sequence: int
    generation: int
    pins: tuple[HalItem, ...]
    signals: tuple[HalItem, ...]
    parameters: tuple[HalItem, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "backend": "linuxcnc-hal", **asdict(self)}


def name(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("Bounded HAL name required")
    return value


def items(data: object, signal: bool, parameter: bool = False) -> tuple[HalItem, ...]:
    if not isinstance(data, list) or len(data) > 4096:
        raise ValueError("HAL group must contain at most 4096 entries")
    result = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("HAL metadata object required")
        key, kind, value = name(item["name"]), item["type_name"], item["value"]
        if kind == "bit":
            if type(value) is not bool:
                raise ValueError("HAL bit must be boolean")
        elif kind == "float":
            value = finite(value)
        elif kind in ("s32", "u32", "s64", "u64"):
            value = integer(value)
            bits = int(kind[1:])
            low, high = (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1) if kind[0] == "s" else (0, 2**bits - 1)
            if not low <= value <= high:
                raise ValueError("HAL integer outside declared range")
        else:
            raise ValueError("Unknown HAL type")
        direction, driver = item["direction"], item["driver"]
        if signal:
            if direction != "signal":
                raise ValueError("Invalid HAL signal direction")
            if driver is not None:
                driver = name(driver)
        elif direction not in (("ro", "rw") if parameter else ("in", "out", "io")) or driver is not None:
            raise ValueError("Invalid HAL pin metadata")
        result.append(HalItem(key, kind, value, direction, driver))
    if len({item.name for item in result}) != len(result):
        raise ValueError("Duplicate HAL names")
    return tuple(sorted(result, key=lambda item: item.name))


def decode_hal(data: dict[str, Any]) -> HalObservation:
    if (
        type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
        or data.get("backend") != "linuxcnc-hal"
    ):
        raise ValueError("Unsupported HAL observation")
    stamp, sequence, generation = finite(data["observed_at"]), integer(data["sequence"]), integer(data["generation"])
    if stamp < 0 or sequence < 1 or generation < 0:
        raise ValueError("Invalid HAL observation identity")
    return HalObservation(
        name(data["machine_id"]),
        stamp,
        sequence,
        generation,
        items(data["pins"], False),
        items(data["signals"], True),
        items(data["parameters"], False, True) if data.get("parameters") is not None else None,
    )


def hal_changes(previous: HalObservation | None, current: HalObservation) -> tuple[SignalTransition, ...]:
    if previous is None:
        return ()

    def identity(observation: HalObservation) -> tuple[object, ...]:
        return (
            observation.machine_id,
            observation.generation,
            observation.parameters is not None,
            tuple(
                (item.name, item.type_name, item.direction, item.driver)
                for item in (*observation.pins, *observation.signals, *(observation.parameters or ()))
            ),
        )

    if (
        identity(previous) != identity(current)
        or current.sequence != previous.sequence + 1
        or current.observed_at < previous.observed_at
    ):
        return ()
    changes = []
    for group, old, new in (("pin", previous.pins, current.pins), ("signal", previous.signals, current.signals)):
        for a, b in zip(old, new):
            if b.type_name == "bit" and a.value != b.value:
                changes.append(
                    SignalTransition(
                        f"hal.{group}.{b.name}", bool(a.value), bool(b.value), previous.observed_at, current.observed_at
                    )
                )
    return tuple(changes)


class LinuxCNCHalReader:
    def __init__(self, machine_id: str, module: Any):
        self.machine_id, self.module = name(machine_id), module
        self.last: HalObservation | None = None
        self.transitions: tuple[SignalTransition, ...] = ()
        self.sequence, self.generation = 0, 0

    @classmethod
    def connect_local(cls, machine_id: str) -> LinuxCNCHalReader:
        return cls(machine_id, importlib.import_module("hal"))

    def poll(self, now: float) -> HalObservation:
        try:
            now = finite(now)
            if now < 0 or (self.last is not None and now < self.last.observed_at):
                raise ValueError("HAL observation clock regressed")
            types = {
                getattr(self.module, "HAL_" + kind.upper()): kind
                for kind in ("bit", "float", "s32", "u32", "s64", "u64")
                if hasattr(self.module, "HAL_" + kind.upper())
            }
            directions = {self.module.HAL_IN: "in", self.module.HAL_OUT: "out", self.module.HAL_IO: "io"}

            def convert(raw: object, signal: bool, parameter: bool = False) -> tuple[HalItem, ...]:
                if not isinstance(raw, list) or len(raw) > 4096:
                    raise ValueError("HAL group exceeds metadata bound")
                parameter_directions = {self.module.HAL_RO: "ro", self.module.HAL_RW: "rw"} if parameter else {}
                converted = []
                for item in raw:
                    if not isinstance(item, dict):
                        raise ValueError("HAL metadata object required")
                    converted.append(
                        {
                            "name": item["NAME"],
                            "type_name": types[integer(item["TYPE"])],
                            "value": item["VALUE"],
                            "direction": "signal"
                            if signal
                            else (parameter_directions if parameter else directions)[integer(item["DIRECTION"])],
                            "driver": item["DRIVER"] if signal else None,
                        }
                    )
                return items(converted, signal, parameter)

            observation = HalObservation(
                self.machine_id,
                now,
                self.sequence + 1,
                self.generation,
                convert(self.module.get_info_pins(), False),
                convert(self.module.get_info_signals(), True),
                convert(self.module.get_info_params(), False, True)
                if hasattr(self.module, "get_info_params")
                else None,
            )
            self.transitions = hal_changes(self.last, observation)
            self.last, self.sequence = observation, observation.sequence
            return observation
        except Exception:
            self.last, self.transitions = None, ()
            self.generation += 1
            raise
