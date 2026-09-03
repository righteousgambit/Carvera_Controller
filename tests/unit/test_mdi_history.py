"""MDI recall history persists, deduplicates and stays bounded."""

import json

import pytest


@pytest.fixture
def config(monkeypatch):
    """A stand-in for the app config that records what was written."""
    from carveracontroller import main as main_module

    store = {}
    monkeypatch.setattr(main_module.Config, "get", lambda _s, k: store.get(k, ""), raising=False)
    monkeypatch.setattr(main_module.Config, "set", lambda _s, k, v: store.__setitem__(k, v), raising=False)
    monkeypatch.setattr(main_module.Config, "write", lambda: None, raising=False)
    return store


def test_history_round_trips(config):
    from carveracontroller.main import load_mdi_history, save_mdi_history

    save_mdi_history(["G0 X0", "M5", "version"])

    assert load_mdi_history() == ["G0 X0", "M5", "version"]


def test_missing_history_loads_empty(config):
    from carveracontroller.main import load_mdi_history

    assert load_mdi_history() == []


@pytest.mark.parametrize("stored", ["not json", "{}", '"a string"', "5"])
def test_unreadable_history_loads_empty(config, stored):
    from carveracontroller.main import load_mdi_history

    config["mdi_history"] = stored

    assert load_mdi_history() == []


def test_history_is_bounded_on_save(config):
    from carveracontroller.main import MAX_MDI_HISTORY, load_mdi_history, save_mdi_history

    save_mdi_history([f"G0 X{n}" for n in range(MAX_MDI_HISTORY * 3)])
    loaded = load_mdi_history()

    assert len(loaded) == MAX_MDI_HISTORY
    assert loaded[-1] == f"G0 X{MAX_MDI_HISTORY * 3 - 1}", "kept the oldest instead of the newest"


def test_history_is_bounded_on_load(config):
    """An oversized file written by an older build must not be trusted."""
    from carveracontroller.main import MAX_MDI_HISTORY, load_mdi_history

    config["mdi_history"] = json.dumps([f"G0 X{n}" for n in range(MAX_MDI_HISTORY * 2)])

    assert len(load_mdi_history()) == MAX_MDI_HISTORY


def test_non_string_entries_are_coerced_rather_than_crashing(config):
    from carveracontroller.main import load_mdi_history

    config["mdi_history"] = json.dumps(["G0 X1", 42, None])

    assert load_mdi_history() == ["G0 X1", "42", "None"]
