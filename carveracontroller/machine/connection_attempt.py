"""Session-only transport attempt evidence, separate from live machine state."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ConnectionAttempt:
    transport: str
    target: str
    started_at: float
    finished_at: float | None = None
    success: bool | None = None
    failure: str = ""

    def finish(self, now: float, success: bool, failure: str = "") -> ConnectionAttempt:
        return replace(self, finished_at=now, success=success, failure="" if success else failure)

    def elapsed(self, now: float) -> float:
        return max(0.0, (self.finished_at if self.finished_at is not None else now) - self.started_at)

    def summary(self, now: float) -> str:
        elapsed = self.elapsed(now)
        if self.success is None:
            return f"Connecting via {self.transport} to {self.target} · {elapsed:.1f}s"
        if self.success:
            return f"Transport opened via {self.transport} · {elapsed:.1f}s; live status is checked separately"
        return f"Connection to {self.target} failed after {elapsed:.1f}s. {self.failure}"


def connection_failure(error: BaseException | None, transport: str) -> str:
    """Offer relevant recovery steps without claiming an unverified root cause."""
    code = getattr(error, "errno", None)
    if transport == "USB":
        return "Check the cable, selected device and whether another application owns the serial port; then retry."
    if isinstance(error, TimeoutError) or code in (60, 110):
        return "The connection timed out. Check machine power, network address and reachability; then retry."
    if code in (65, 113, 51, 101):
        return "No route to host. Check network reachability and this app's Local Network permission; then retry."
    if code in (61, 111):
        return "The host refused the connection. Check the controller address, port and active connection; then retry."
    if code in (1, 13):
        return "Network access was denied. Check this app's network permission; then retry."
    return (
        "The transport could not open or detect the controller protocol. Check the address and connection; then retry."
    )
