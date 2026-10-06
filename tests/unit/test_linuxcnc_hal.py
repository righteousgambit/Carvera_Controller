import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.machine.linuxcnc_hal import LinuxCNCHalReader, decode_hal
from carveracontroller.machine.linuxcnc_status import LinuxCNCStatusReader
from tests.unit.test_linuxcnc_status import Status


def module():
    return SimpleNamespace(
        HAL_BIT=1,
        HAL_FLOAT=2,
        HAL_S32=3,
        HAL_U32=4,
        HAL_IN=16,
        HAL_OUT=32,
        HAL_IO=48,
        get_info_pins=Mock(return_value=[{"NAME": "joint.0.homed", "TYPE": 1, "VALUE": False, "DIRECTION": 32}]),
        get_info_signals=Mock(
            return_value=[{"NAME": "air-pressure", "TYPE": 2, "VALUE": 5.2, "DRIVER": "sensor.pressure"}]
        ),
        component=Mock(side_effect=AssertionError("must not create component")),
        set_p=Mock(side_effect=AssertionError("must not write")),
    )


def test_actual_optional_hal_module_only_uses_read_metadata_api(monkeypatch):
    import sys

    api = module()
    monkeypatch.setitem(sys.modules, "hal", api)
    reader = LinuxCNCHalReader.connect_local("mill")
    observation = reader.poll(10.0)
    assert observation.pins[0].direction == "out"
    assert observation.signals[0].driver == "sensor.pressure"
    assert observation.signals[0].value == 5.2
    assert decode_hal(json.loads(json.dumps(observation.to_dict()))) == observation
    api.component.assert_not_called()
    api.set_p.assert_not_called()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda api: api.get_info_pins.return_value[0].update(VALUE=2),
        lambda api: api.get_info_pins.return_value[0].update(TYPE=99),
        lambda api: api.get_info_pins.return_value[0].update(DIRECTION=99),
        lambda api: api.get_info_signals.return_value[0].update(VALUE=float("nan")),
        lambda api: api.get_info_signals.return_value[0].update(DRIVER="x" * 257),
        lambda api: api.get_info_pins.return_value.append(api.get_info_pins.return_value[0].copy()),
        lambda api: setattr(api.get_info_pins, "return_value", [{}] * 4097),
    ],
)
def test_failed_hal_poll_clears_old_observation_and_breaks_transitions(mutation):
    api = module()
    reader = LinuxCNCHalReader("mill", api)
    reader.poll(10)
    mutation(api)
    with pytest.raises((ValueError, KeyError)):
        reader.poll(11)
    assert reader.last is None and reader.transitions == () and reader.generation == 1


def test_hal_bit_changes_are_recomputed_and_driver_change_breaks_continuity():
    api = module()
    reader = LinuxCNCHalReader("mill", api)
    reader.poll(10)
    api.get_info_pins.return_value[0]["VALUE"] = True
    reader.poll(11)
    assert reader.transitions[0].signal == "hal.pin.joint.0.homed"
    api.get_info_signals.return_value[0]["DRIVER"] = "other.pressure"
    api.get_info_pins.return_value[0]["VALUE"] = False
    reader.poll(12)
    assert reader.transitions == ()


def make_capture(tmp_path, hal_api=None):
    from scripts.capture_linuxcnc_status import capture

    status, api = Status(), module() if hal_api is None else hal_api
    config = tmp_path / "mill.ini"
    config.write_text("[KINS]\nJOINTS=2\n")
    status.ini_filename = str(config)
    output = tmp_path / "hal.jsonl"
    times = iter((10, 10.01, 11, 11.01))

    def advance(_interval):
        api.get_info_pins.return_value[0]["VALUE"] = True

    capture(
        LinuxCNCStatusReader("mill", status),
        output,
        2,
        0.1,
        clock=lambda: next(times),
        sleep=advance,
        hal_reader=LinuxCNCHalReader("mill", api),
    )
    return output


def test_capture_import_retains_named_metadata_and_recomputes_hal_changes(tmp_path):
    from carveracontroller.machine.commissioning_capture import load_capture
    from carveracontroller.machine.commissioning_channels import channel_page

    output = make_capture(tmp_path)
    lines = [json.loads(line) for line in output.read_text().splitlines()]
    lines[0]["hal_transitions"] = [{"signal": "forged permissive"}]
    output.write_text("\n".join(json.dumps(line) for line in lines))
    review = load_capture(output)
    assert review.hal_observations[0].signals[0].driver == "sensor.pressure"
    assert review.transitions[0] == ()
    assert review.transitions[1][0].signal == "hal.pin.joint.0.homed"
    rows = channel_page(review.observations[0], (), "HAL signals", hal=review.hal_observations[0]).rows
    assert rows == (("air-pressure", "5.2 · float · driver sensor.pressure"),)


@pytest.mark.parametrize("change", ["missing", "identity", "sequence", "timestamp", "value"])
def test_import_rejects_inconsistent_hal_coverage_and_metadata(tmp_path, change):
    from carveracontroller.machine.commissioning_capture import load_capture

    output = make_capture(tmp_path)
    lines = [json.loads(line) for line in output.read_text().splitlines()]
    hal = lines[1]["hal"]
    if change == "missing":
        del lines[1]["hal"]
    elif change == "identity":
        hal["machine_id"] = "other"
    elif change == "sequence":
        hal["sequence"] = 9
    elif change == "timestamp":
        hal["observed_at"] = 10
    else:
        hal["signals"][0]["value"] = float("inf")
    output.write_text("\n".join(json.dumps(line) for line in lines))
    with pytest.raises(ValueError):
        load_capture(output)


def test_capture_byte_limit_retains_samples_failure_and_no_false_completion(tmp_path, monkeypatch):
    import scripts.capture_linuxcnc_status as writer
    from carveracontroller.machine.commissioning_capture import load_capture

    monkeypatch.setattr(writer, "MAX_CAPTURE_BYTES", 8192)
    status = Status()
    config = tmp_path / "mill.ini"
    config.write_text("[KINS]\nJOINTS=2\n")
    status.ini_filename = str(config)
    output = tmp_path / "bounded.jsonl"
    with pytest.raises(ValueError, match="byte bound"):
        writer.capture(LinuxCNCStatusReader("mill", status), output, 100, 0.1, clock=lambda: 10, sleep=lambda _: None)
    assert output.stat().st_size <= 8192
    review = load_capture(output)
    assert review.observations and not review.complete and "byte bound" in review.failure


@pytest.mark.parametrize("width", [360, 650])
def test_named_hal_driver_review_wraps_in_mounted_panel(tmp_path, width):
    pytest.importorskip("kivy")
    from kivy.core.window import Window

    from carveracontroller.desktop_commissioning import CommissioningPanel
    from carveracontroller.machine.commissioning_capture import load_capture
    from tests.integration.conftest import pump_frames

    panel = CommissioningPanel(SimpleNamespace(), size_hint_x=None, width=width)
    Window.add_widget(panel)
    try:
        panel.deliver(0, load_capture(make_capture(tmp_path)), None)
        panel.channel_choice.text = "HAL signals"
        pump_frames(8)
        assert "driver sensor.pressure" in panel.channel_values.text
        assert "separate samples" in panel.scope_note.text
        assert panel.channel_values.height >= panel.channel_values.texture_size[1]
        panel.hal_search.text = "SENSOR float"
        pump_frames(12)
        assert tuple(panel.hal_selected.values) == ("air-pressure",)
        assert "Driver pin is absent" in panel.hal_detail.text
        assert "1 matches / 1 recorded" in panel.hal_filter_note.text
        panel.export_to_png(str(tmp_path / f"hal-{width}.png"))
        panel.hal_search.text = "x" * 257
        pump_frames(12)
        assert panel.hal_search.validation_error
        assert panel.hal_selected.disabled and panel.channel_next.disabled
        assert not panel.hal_selected.values and not panel.hal_detail.text
        panel.hal_search.text = "SENSOR float"
        pump_frames(12)
        assert not panel.hal_search.validation_error and not panel.hal_selected.disabled
        panel.hal_search.focus = True
        panel.move(1)
        panel.channel_choice.text = "Sample changes"
        assert panel.hal_tools.parent is None and not panel.hal_search.focus
        assert "hal.pin.joint.0.homed: 0 to 1" in panel.channel_values.text
        output = tmp_path / "hal.jsonl"
        records = [json.loads(line) for line in output.read_text().splitlines()]
        for record in records:
            record.pop("hal", None)
        output.write_text("\n".join(json.dumps(record) for record in records))
        panel.deliver(0, load_capture(output), None)
        panel.channel_choice.text = "HAL pins"
        panel.hal_search.text = ""
        pump_frames(12)
        assert "not captured" in panel.channel_values.text
        panel.clear()
        assert not panel.hal_search.text
    finally:
        Window.remove_widget(panel)


def test_large_hal_search_pages_preserve_names_values_and_bounded_rows():
    from dataclasses import replace

    from carveracontroller.machine.commissioning_channels import channel_page, matching_hal_items
    from carveracontroller.machine.linuxcnc_hal import HalItem

    hal = LinuxCNCHalReader("mill", module()).poll(10)
    hal = replace(
        hal, pins=tuple(HalItem(f"sensor.{i:04}.pressure", "float", i / 10, "out", None) for i in range(4096))
    )
    status = LinuxCNCStatusReader("mill", Status()).poll(10)
    found = []
    for index in range(256):
        page = channel_page(status, (), "HAL pins", index, hal, "SENSOR pressure FLOAT out")
        assert len(page.rows) == 16
        found.extend(name for name, _value in page.rows)
    assert found == [f"sensor.{i:04}.pressure" for i in range(4096)]
    assert matching_hal_items(hal, "HAL pins", "sensor.4095")[0].value == 409.5
    assert channel_page(status, (), "HAL pins", 100, hal, "not-found").total == 0
    with pytest.raises(ValueError, match="256"):
        matching_hal_items(hal, "HAL pins", "x" * 257)


def test_driver_detail_uses_exact_reported_pin_and_preserves_missing_or_mismatched_evidence():
    from dataclasses import replace

    from carveracontroller.machine.commissioning_channels import hal_item_detail
    from carveracontroller.machine.linuxcnc_hal import HalItem

    hal = LinuxCNCHalReader("mill", module()).poll(10)
    hal = replace(hal, pins=(*hal.pins, HalItem("sensor.pressure", "float", 5.1, "out", None)))
    detail = hal_item_detail(hal, "HAL signals", "air-pressure")
    assert "Reported float value 5.2" in detail
    assert "Captured driver: float · out · value 5.1" in detail
    assert "read separately" in detail
    hal = replace(hal, pins=(HalItem("sensor.pressure", "bit", True, "out", None),))
    assert "types differ" in hal_item_detail(hal, "HAL signals", "air-pressure")
    assert "No selected" in hal_item_detail(hal, "HAL signals", "unknown")


def parameter_module():
    api = module()
    api.HAL_RO, api.HAL_RW = 64, 128
    api.get_info_params = Mock(
        return_value=[
            {"NAME": "pid.0.Pgain", "TYPE": 2, "VALUE": 120.5, "DIRECTION": 128},
            {"NAME": "servo-thread.time", "TYPE": 3, "VALUE": 321, "DIRECTION": 64},
        ]
    )
    return api


def test_parameter_capture_preserves_access_values_and_legacy_absence():
    from dataclasses import replace

    from carveracontroller.machine.linuxcnc_hal import hal_changes

    api = parameter_module()
    reader = LinuxCNCHalReader("mill", api)
    first = reader.poll(10)
    assert [(p.name, p.value, p.direction) for p in first.parameters] == [
        ("pid.0.Pgain", 120.5, "rw"),
        ("servo-thread.time", 321, "ro"),
    ]
    assert decode_hal(json.loads(json.dumps(first.to_dict()))) == first
    old = json.loads(json.dumps(first.to_dict()))
    del old["parameters"]
    assert decode_hal(old).parameters is None
    old["parameters"] = []
    assert decode_hal(old).parameters == ()
    api.get_info_pins.return_value[0]["VALUE"] = True
    next_sample = reader.poll(11)
    assert hal_changes(replace(first, parameters=None), next_sample) == ()
    api.component.assert_not_called()
    api.set_p.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"VALUE": float("inf")},
        {"DIRECTION": 16},
        {"TYPE": 99},
        {"NAME": "x" * 257},
    ],
)
def test_parameter_failure_invalidates_reader(change):
    api = parameter_module()
    reader = LinuxCNCHalReader("mill", api)
    reader.poll(10)
    api.get_info_params.return_value[0].update(change)
    with pytest.raises((ValueError, KeyError)):
        reader.poll(11)
    assert reader.last is None and reader.generation == 1 and not reader.transitions


def test_parameter_pages_cover_every_entry_and_distinguish_missing():
    from dataclasses import replace

    from carveracontroller.machine.commissioning_channels import channel_page, hal_item_detail
    from carveracontroller.machine.linuxcnc_hal import HalItem

    hal = LinuxCNCHalReader("mill", parameter_module()).poll(10)
    status = LinuxCNCStatusReader("mill", Status()).poll(10)
    detail = hal_item_detail(hal, "HAL parameters", "pid.0.Pgain")
    assert "120.5" in detail and "rw" in detail and "not permission to edit" in detail
    assert "not captured" in hal_item_detail(replace(hal, parameters=None), "HAL parameters", "pid.0.Pgain")
    hal = replace(hal, parameters=tuple(HalItem(f"pid.{i:04}.Pgain", "float", i / 10, "rw", None) for i in range(4096)))
    found = []
    for page in range(256):
        rows = channel_page(status, (), "HAL parameters", page, hal, "PID float rw").rows
        assert len(rows) == 16
        found.extend(name for name, _ in rows)
    assert found == [p.name for p in hal.parameters]
    assert channel_page(status, (), "HAL parameters", 0, hal, "pid.4095").rows == (
        ("pid.4095.Pgain", "409.5 · float · rw"),
    )


@pytest.mark.parametrize("width", [360, 650])
def test_parameter_review_in_mounted_panel(tmp_path, width):
    from dataclasses import replace

    from kivy.clock import Clock
    from kivy.uix.floatlayout import FloatLayout

    from carveracontroller.desktop_commissioning import CommissioningPanel
    from carveracontroller.machine.commissioning_capture import load_capture

    capture = load_capture(make_capture(tmp_path))
    params = LinuxCNCHalReader("mill", parameter_module()).poll(10).parameters
    capture = replace(capture, hal_observations=tuple(replace(h, parameters=params) for h in capture.hal_observations))
    panel = CommissioningPanel(SimpleNamespace())
    root = FloatLayout(size_hint=(None, None), size=(width, 1800))
    root.add_widget(panel)
    panel.width = width
    try:
        panel.deliver(0, capture, None)
        panel.channel_choice.text = "HAL parameters"
        panel.hal_search.text = "Pgain rw"
        panel.render_channels()
        for _ in range(4):
            Clock.tick()
        assert tuple(panel.hal_selected.values) == ("pid.0.Pgain",)
        assert "120.5" in panel.channel_values.text
        assert "not permission to edit" in panel.hal_detail.text
        panel.capture = replace(
            capture, hal_observations=tuple(replace(h, parameters=None) for h in capture.hal_observations)
        )
        panel.render_channels()
        assert "not captured" in panel.channel_values.text
        assert panel.hal_selected.disabled
        assert "unavailable" in panel.hal_filter_note.text
    finally:
        panel.clear()
        root.remove_widget(panel)


def test_parameter_capture_roundtrip_in_recording_and_rejects_forged_access(tmp_path):
    from carveracontroller.machine.commissioning_capture import load_capture

    path = make_capture(tmp_path, parameter_module())
    capture = load_capture(path)
    assert all(h.parameters[0].name == "pid.0.Pgain" for h in capture.hal_observations)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    lines[0]["hal"]["parameters"][0]["direction"] = "out"
    with pytest.raises(ValueError):
        invalid = tmp_path / "forged-parameters.jsonl"
        invalid.write_text("\n".join(json.dumps(line) for line in lines))
        load_capture(invalid)
