"""TCP server that presents a SimulatedMachine over the Makera protocol."""

from __future__ import annotations

import logging
import socketserver
import threading
import time

from carveracontroller.protocols.framing import (
    PTYPE_NORMAL_INFO,
    PTYPE_STATUS_RES,
    build_frame,
    validate_packet_data,
)

from .machine import SimulatedMachine

logger = logging.getLogger(__name__)

TCP_PORT = 2222
TICK_SECONDS = 0.05

_FRAME_HEADER = b"\x86\x68"
_FRAME_END = b"\x55\xaa"


def frames_from(buffer: bytearray) -> list:
    """Pull complete frames out of ``buffer``, consuming what it returns.

    Mirrors the receive state machine in ``MakeraProtocol`` closely enough to
    decode what the controller sends, without depending on its internals.
    """
    out = []
    while True:
        start = buffer.find(_FRAME_HEADER)
        if start < 0:
            del buffer[:]
            return out
        if len(buffer) < start + 4:
            del buffer[:start]
            return out
        length = int.from_bytes(buffer[start + 2 : start + 4], "big")
        total = 4 + length + 2
        if len(buffer) < start + total:
            del buffer[:start]
            return out
        body = bytes(buffer[start + 2 : start + 4 + length])
        footer = bytes(buffer[start + 4 + length : start + total])
        del buffer[: start + total]
        if footer != _FRAME_END:
            continue
        parsed = validate_packet_data(body)
        if parsed is not None:
            out.append(parsed)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        machine: SimulatedMachine = self.server.machine
        buffer = bytearray()
        self.request.settimeout(0.1)
        logger.info("client connected from %s", self.client_address)

        while not self.server.stopping:
            try:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
            except OSError:
                chunk = b""

            for frame in frames_from(buffer):
                for reply in self._respond(machine, frame.ptype, frame.payload):
                    self.request.sendall(reply)

        logger.info("client disconnected from %s", self.client_address)

    def _respond(self, machine: SimulatedMachine, ptype: int, payload: bytes) -> list:
        replies = []
        text = payload.decode("utf-8", errors="replace")

        # Realtime single-byte controls arrive as CTRL_SINGLE.
        if "?" in text or "\x02" in text:
            replies.append(build_frame(PTYPE_STATUS_RES, machine.status_line().encode()))
            return replies

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            output = machine.execute(line)
            if output:
                replies.append(build_frame(PTYPE_NORMAL_INFO, (output + "\n").encode()))
        return replies


class CarveraSimServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, machine: SimulatedMachine | None = None, port: int = TCP_PORT) -> None:
        self.machine = machine or SimulatedMachine()
        self.stopping = False
        super().__init__(("127.0.0.1", port), _Handler)
        self._ticker: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.server_address[1]

    def start_background(self) -> None:
        """Serve and advance the physics on background threads."""
        threading.Thread(target=self.serve_forever, daemon=True).start()
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self._ticker.start()

    def _tick_loop(self) -> None:
        while not self.stopping:
            self.machine.tick(TICK_SECONDS)
            time.sleep(TICK_SECONDS)

    def stop(self) -> None:
        self.stopping = True
        self.shutdown()
        self.server_close()

    def __enter__(self) -> CarveraSimServer:
        self.start_background()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
