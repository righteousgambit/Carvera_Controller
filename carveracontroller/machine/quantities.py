"""Bounded arithmetic for operator quantities, converted to canonical units.

No Python evaluation, names, functions or machine commands are accepted. A unit
suffix applies to the entire expression; internal mixed-unit terms are rejected
instead of guessing. Unsuffixed expressions use the field's displayed unit.
"""

from __future__ import annotations

import ast
import math
import re
from typing import cast


class QuantityError(ValueError):
    pass


UNITS: dict[str, dict[str, float]] = {
    "length": {
        "mm": 1,
        "cm": 10,
        "m": 1000,
        "um": 0.001,
        "µm": 0.001,
        "μm": 0.001,
        "in": 25.4,
        "inch": 25.4,
        "inches": 25.4,
        '"': 25.4,
        "ft": 304.8,
    },
    "feed": {"mm/min": 1, "mm/s": 60, "in/min": 25.4, "inch/min": 25.4, "ipm": 25.4, "in/s": 1524},
    "angle": {"deg": 1, "degrees": 1, "°": 1, "rad": 180 / math.pi},
    "rpm": {"rpm": 1, "rev/min": 1},
    "force": {"n": 1, "kn": 1000, "lbf": 4.4482216152605},
    "pressure": {"mpa": 1, "gpa": 1000, "pa": 0.000001, "psi": 0.006894757293168},
    "scalar": {},
}
CANONICAL = {
    "length": "mm",
    "feed": "mm/min",
    "angle": "deg",
    "rpm": "rpm",
    "force": "N",
    "pressure": "MPa",
    "scalar": "",
}
_SUFFIXES = sorted({unit for units in UNITS.values() for unit in units}, key=len, reverse=True)
_MIXED = re.compile(r"^([+-]?)(\d+)\s+(\d+)\s*/\s*(\d+)$")


def parse_quantity(
    text: str,
    kind: str = "length",
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> float | int:
    """Return mm, mm/min, degrees, RPM or a scalar; bounds use canonical units."""
    if kind not in UNITS:
        raise QuantityError("Unknown quantity type")
    if not isinstance(text, str) or not text.strip():
        raise QuantityError("Enter a value")
    if len(text) > 256:
        raise QuantityError("Expression is limited to 256 characters")
    expression = text.strip().casefold().translate(str.maketrans("−×÷", "-*/"))
    factor = 1.0
    for unit in _SUFFIXES:
        if expression.endswith(unit):
            if unit not in UNITS[kind]:
                raise QuantityError(f"Use {CANONICAL[kind] or 'a unitless whole number'} in this field")
            expression, factor = expression[: -len(unit)].strip(), UNITS[kind][unit]
            break
    match = _MIXED.fullmatch(expression)
    if match:
        sign, whole, numerator, denominator = match.groups()
        expression = f"{sign}({whole}+{numerator}/{denominator})"
    if not re.fullmatch(r"[0-9eE.+\-*/()\s]+", expression):
        raise QuantityError("Use decimal numbers and arithmetic; put units at the end")
    nesting = 0
    for char in expression:
        nesting += (char == "(") - (char == ")")
        if nesting > 12:
            raise QuantityError("Expression is nested too deeply")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise QuantityError("Use numbers, + − * / and parentheses, with one unit suffix") from exc
    if len(list(ast.walk(tree))) > 64:
        raise QuantityError("Expression has too many operations")

    def evaluate(node: ast.AST, depth: int = 0) -> float:
        if depth > 12:
            raise QuantityError("Expression is nested too deeply")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(cast("int | float", node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand, depth + 1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            else:
                if right == 0:
                    raise QuantityError("Cannot divide by zero")
                value = left / right
        else:
            raise QuantityError("Use numbers and arithmetic only; put units at the end")
        if not math.isfinite(value) or abs(value) > 1e12:
            raise QuantityError("Value must be finite and within the supported range")
        return value

    value = evaluate(tree.body) * factor
    if not math.isfinite(value) or abs(value) > 1e12:
        raise QuantityError("Value is outside the supported range")
    if minimum is not None and value < minimum:
        raise QuantityError(f"Minimum is {minimum:g} {CANONICAL[kind]}")
    if maximum is not None and value > maximum:
        raise QuantityError(f"Maximum is {maximum:g} {CANONICAL[kind]}")
    if integer:
        if not value.is_integer():
            raise QuantityError("Enter a whole number")
        return int(value)
    return value


def format_quantity(value: float, kind: str = "length") -> str:
    if kind == "length":
        return f"{value:.6g} mm · {value / 25.4:.6g} in"
    if kind == "feed":
        return f"{value:.6g} mm/min · {value / 25.4:.6g} ipm"
    return f"{value:.6g} {CANONICAL[kind]}".strip()
