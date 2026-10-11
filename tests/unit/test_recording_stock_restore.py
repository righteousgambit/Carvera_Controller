from copy import deepcopy

import pytest

from carveracontroller.addons.machine_simulation.stock_model import StockModel
from carveracontroller.machine.recording_stock_restore import recorded_setup_kwargs
from carveracontroller.machine.run_recording import stock_source_identity
from tests.unit.test_stock_solid import l_stock, mesh


def test_recorded_imported_stock_restore_reuses_exact_source_and_preserves_input(tmp_path):
    source = mesh(tmp_path, l_stock())
    model = StockModel.load(source.source_path, "mm")
    setup = {
        "work_offset_mm": [-180, -120, -110],
        "stock_size_mm": list(model.size_mm),
        "stock_origin_mm": [2, 3, 4],
        "stock_rotation_deg": 20,
        "stock_tilt_deg": [10, -5],
        "alignment_confirmed": False,
        "stock_source": stock_source_identity(model.reference),
    }
    original = deepcopy(setup)
    options = recorded_setup_kwargs(setup, model)
    assert options["stock_model"] is model and "stock_source" not in options
    assert {key: value for key, value in options.items() if key != "stock_model"} == {
        key: value for key, value in original.items() if key != "stock_source"
    }
    assert setup == original
    with pytest.raises(ValueError, match="Recorded stock source differs"):
        recorded_setup_kwargs(setup, None)
    changed = {**setup, "stock_source": {**setup["stock_source"], "source_sha256": "0" * 64}}
    with pytest.raises(ValueError, match="Recorded stock source differs"):
        recorded_setup_kwargs(changed, model)
    block = {key: value for key, value in setup.items() if key != "stock_source"}
    assert recorded_setup_kwargs(block, model)["stock_model"] is None
