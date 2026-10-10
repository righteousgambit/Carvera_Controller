"""Restore validated recorded placement using exact retained stock geometry."""

from __future__ import annotations

from typing import Any

from carveracontroller.addons.machine_simulation.stock_model import StockModel
from carveracontroller.machine.run_recording import stock_source_identity


def recorded_setup_kwargs(setup: dict[str, Any], model: StockModel | None) -> dict[str, Any]:
    """No file I/O: path-free recording identity can reuse only matching CAD.

    A mismatch withholds restoration instead of guessing a path or converting
    shaped stock to a block. Complete archived scene loading is a separate action.
    """
    options = {key: value for key, value in setup.items() if key != "stock_source"}
    source = setup.get("stock_source")
    if source is not None:
        if model is None or stock_source_identity(model.reference) != stock_source_identity(source):
            raise ValueError(
                "Recorded stock source differs · load the recorded scene and tools before restoring placement."
            )
        options["stock_model"] = model
    else:
        options["stock_model"] = None
    return options
