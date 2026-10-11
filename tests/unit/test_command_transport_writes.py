"""Command transports must not report success for partial or absent writes."""

from unittest.mock import Mock

import pytest

from carveracontroller.USBStream import USBStream
from carveracontroller.WIFIStream import WIFIStream


class ShortWriteSocket:
    def __init__(self):
        self.wire = bytearray()
        self.send_calls = 0

    def send(self, data):
        self.send_calls += 1
        count = min(3, len(data))
        self.wire.extend(data[:count])
        return count

    def sendall(self, data):
        # Model sendall consuming an underlying socket that repeatedly accepts
        # only a prefix; the command path must invoke this complete-write API.
        while data:
            count = self.send(data)
            data = data[count:]


@pytest.mark.parametrize("payload", [b"resume\n", b"abort -R 4294967295\n", b"\x12\x34\x00\xff"])
def test_wifi_command_writes_complete_payload_over_short_writes(payload):
    stream = WIFIStream()
    stream.socket = ShortWriteSocket()
    stream.send(payload)
    assert bytes(stream.socket.wire) == payload
    assert stream.socket.send_calls > 1


@pytest.mark.parametrize("failure", [TimeoutError("write timed out"), OSError("connection lost")])
def test_wifi_command_failure_propagates_without_retry(failure):
    stream = WIFIStream()
    stream.socket = Mock()
    stream.socket.sendall.side_effect = failure
    with pytest.raises(type(failure), match=str(failure)):
        stream.send(b"resume\n")
    stream.socket.sendall.assert_called_once_with(b"resume\n")
    stream.socket.send.assert_not_called()


def test_wifi_disconnected_command_is_failure():
    stream = WIFIStream()
    stream.socket = None
    with pytest.raises(OSError, match="disconnected"):
        stream.send(b"resume\n")


@pytest.mark.parametrize("written", [0, 3, 8, None, True, 7.0])
def test_usb_partial_or_invalid_write_is_failure_without_retry(written):
    stream = USBStream()
    stream.serial = Mock(is_open=True)
    stream.serial.write.return_value = written
    with pytest.raises(OSError, match="incomplete"):
        stream.send(b"resume\n")
    stream.serial.write.assert_called_once_with(b"resume\n")


@pytest.mark.parametrize("failure", [TimeoutError("write timed out"), OSError("port disappeared")])
def test_usb_write_failure_propagates_without_retry(failure):
    stream = USBStream()
    stream.serial = Mock(is_open=True)
    stream.serial.write.side_effect = failure
    with pytest.raises(type(failure), match=str(failure)):
        stream.send(b"resume\n")
    stream.serial.write.assert_called_once_with(b"resume\n")


def test_usb_disconnected_and_closed_commands_are_failures():
    stream = USBStream()
    stream.serial = None
    with pytest.raises(OSError, match="disconnected"):
        stream.send(b"resume\n")
    stream.serial = Mock(is_open=False)
    with pytest.raises(OSError, match="closed"):
        stream.send(b"resume\n")
    stream.serial.write.assert_not_called()


def test_usb_complete_unicode_command_uses_encoded_byte_length():
    stream = USBStream()
    stream.serial = Mock(is_open=True)
    payload = "cat /sd/café.nc\n".encode()
    stream.serial.write.return_value = len(payload)
    stream.send("cat /sd/café.nc\n")
    stream.serial.write.assert_called_once_with(payload)
