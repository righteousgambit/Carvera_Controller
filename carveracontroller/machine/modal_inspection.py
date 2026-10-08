"""Before/after program modal evidence, independent of UI and transport."""

from dataclasses import dataclass

from .move_inspection import MoveExplanation
from .program_operations import ModalState


@dataclass(frozen=True)
class ModalFact:
    key: str
    title: str
    before: str
    after: str
    changed: bool


_FIELDS = (
    ("units", "Program units"),
    ("distance", "Endpoint mode"),
    ("plane", "Arc plane"),
    ("arc_distance", "Arc-center mode"),
    ("feed_mode", "Feed mode"),
    ("wcs", "Work coordinate selection"),
    ("motion", "Motion mode"),
    ("tool", "Program tool"),
    ("pending_tool", "Pending tool"),
    ("tool_length_command", "Tool length compensation"),
    ("cutter_compensation", "Cutter compensation"),
    ("feed", "Programmed feed"),
    ("spindle_speed", "Programmed spindle speed"),
    ("spindle", "Spindle mode"),
    ("coolant", "Coolant mode"),
)
_MEANINGS = {
    "G20": "inches",
    "G21": "millimeters",
    "G90": "absolute",
    "G91": "incremental",
    "G17": "XY",
    "G18": "XZ",
    "G19": "YZ",
    "G90.1": "absolute centers",
    "G91.1": "incremental centers",
    "G93": "inverse minutes",
    "G94": "units per minute",
    "G95": "units per revolution",
    "G40": "off",
    "G49": "off",
    "M3": "clockwise",
    "M4": "counterclockwise",
    "M5": "stopped",
    "M7": "mist",
    "M8": "flood",
    "M9": "off",
}


def _display(state: ModalState, key: str) -> str:
    value = getattr(state, key)
    if value is None:
        return "Unknown"
    if key in ("tool", "pending_tool"):
        return f"T{value}"
    if key == "motion":
        return f"G{value}"
    if key == "spindle_speed":
        return f"{value:g} RPM"
    if key == "feed":
        suffix = (
            "inverse min"
            if state.feed_mode == "G93"
            else ("in" if state.units == "G20" else "mm" if state.units == "G21" else "units unknown")
            + ("/min" if state.feed_mode == "G94" else "/rev" if state.feed_mode == "G95" else " · mode unknown")
        )
        return f"{value:g} {suffix}"
    if key == "cutter_compensation" and value != "G40":
        return f"{value} · requested; path unsupported"
    if key == "coolant":
        return " + ".join(f"{code} · {_MEANINGS.get(code, 'unknown')}" for code in value.split())
    return f"{value} · {_MEANINGS[value]}" if value in _MEANINGS else str(value)


def modal_facts(move: MoveExplanation) -> tuple[ModalFact, ...]:
    """Compare semantic quantities as well as codes; never supply initial defaults."""
    facts = []
    for key, title in _FIELDS:
        before, after = _display(move.before, key), _display(move.after, key)
        # Feed units/mode can change without an F word; display meaning is part
        # of the transition. None -> None remains unknown, not 'comp off'.
        facts.append(ModalFact(key, title, before, after, before != after))
    return tuple(facts)


def modal_notes(move: MoveExplanation) -> tuple[str, ...]:
    notes = [
        "Program interpretation only; this is not a controller modal-state readback.",
        "G54–G59 select a work frame. Numeric work/local offsets, H/D table values and machine transforms are not supplied.",
    ]
    if move.after.recovery_errors:
        notes.append(
            "Interpretation uncertain after unsupported syntax or commands; later displayed values do not validate motion."
        )
    notes.extend(move.warnings)
    return tuple(dict.fromkeys(notes))
