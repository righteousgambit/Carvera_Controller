import pytest

from carveracontroller.machine.connection_attempt import ConnectionAttempt, connection_failure


@pytest.mark.parametrize(
    "error, phrase",
    [
        (OSError(65, "route"), "No route"),
        (OSError(113, "route"), "No route"),
        (OSError(111, "refused"), "refused"),
        (TimeoutError(), "timed out"),
        (OSError(13, "denied"), "denied"),
        (None, "protocol"),
    ],
)
def test_network_failure_guidance(error, phrase):
    assert phrase in connection_failure(error, "Wi-Fi")


def test_attempt_elapsed_freezes_at_completion_without_claiming_machine_state():
    pending = ConnectionAttempt("Wi-Fi", "192.0.2.1:2222", 10)
    assert pending.elapsed(9) == 0
    assert "3.0s" in pending.summary(13)
    failed = pending.finish(14, False, "Check address.")
    assert failed.elapsed(100) == 4
    assert "Check address." in failed.summary(100)
    opened = pending.finish(15, True, "must disappear")
    assert opened.failure == ""
    assert "live status is checked separately" in opened.summary(100)
    assert pending.finished_at is None
    assert "serial port" in connection_failure(OSError(13, "access"), "USB")
