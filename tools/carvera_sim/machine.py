"""Simulated Carvera machine state.

Pure state model with no I/O, so it can be driven directly from tests. The
socket server in ``server.py`` wraps this and speaks the Makera framed
protocol on top of it.

The spindle model is the reason this exists. ``PWMSpindleControl`` in the
firmware runs a closed integrating loop: under load it raises PWM to hold the
commanded RPM, so RPM stays flat until PWM saturates at ``max_pwm`` and only
then falls away. Anything consuming spindle load needs that shape to develop
against, and it cannot be reproduced by replaying a canned status line.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Machine geometry (original Carvera, C1).
MAX_RPM = 15000.0
MIN_RPM = 1000.0

# Spindle loop constants. Chosen to behave like the firmware rather than to
# match it numerically: the observable shape is what callers depend on.
PWM_P_TERM = 0.00012
MAX_PWM = 1.0
# PWM is spindle *effort*, not speed. Holding full RPM unloaded costs roughly
# this fraction of available output; the remainder is headroom for cutting.
NO_LOAD_PWM_FRACTION = 0.55
# PWM demanded per unit of cutting load. Together these put saturation at
# roughly 60 % load when commanding 14000 RPM, which is the regime worth
# developing a load gauge against.
LOAD_PWM_FRACTION = 0.75

AMBIENT_TEMP_C = 24.0
# Degrees per second of temperature rise at full load, and passive decay.
TEMP_RISE_RATE = 0.9
TEMP_DECAY_RATE = 0.25

# Machine model identifiers as reported in the ``C:`` status field.
MACHINE_CARVERA = 2
# Bit 2 of FuncSetting is the ATC flag; bit 0 is the 4th axis.
FUNC_4AXIS = 1 << 0
FUNC_ATC = 1 << 2


@dataclass
class Axes:
    x: float = -180.0
    y: float = -120.0
    z: float = -5.0
    a: float = 0.0


@dataclass
class SimulatedMachine:
    """A Carvera that exists only in memory.

    ``load`` is the externally-imposed cutting load, 0.0 (free spinning) to
    1.0 (stalling). Tests and fault-injection scripts set it directly; there
    is no attempt to derive it from toolpath geometry.
    """

    state: str = "Idle"
    machine: Axes = field(default_factory=Axes)
    work_offset: Axes = field(default_factory=lambda: Axes(-180.0, -120.0, -5.0, 0.0))

    target_rpm: float = 0.0
    current_rpm: float = 0.0
    pwm: float = 0.0
    load: float = 0.0
    spindle_on: bool = False

    spindle_temp: float = AMBIENT_TEMP_C
    power_temp: float = AMBIENT_TEMP_C

    feed_current: float = 0.0
    feed_target: float = 0.0
    feed_override: int = 100
    spindle_override: int = 100

    tool: int = 1
    tlo: float = 35.0
    target_tool: int = -1
    target_collet: int = 0

    vacuum: int = 0
    ext_out: int = 0
    laser_mode: int = 0
    wp_voltage: float = 3.3

    wcs: int = 0
    rotation_angle: float = 0.0
    inch_mode: int = 0
    absolute_mode: int = 1
    func_setting: int = FUNC_4AXIS | FUNC_ATC

    halt_reason: int | None = None

    # Probe results, addressable as #151-#156 by probing cycles.
    probe_vars: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Physics
    # ------------------------------------------------------------------
    def tick(self, dt: float = 0.1) -> None:
        """Advance the machine by ``dt`` seconds."""
        self._tick_spindle(dt)
        self._tick_thermal(dt)

    def _tick_spindle(self, dt: float) -> None:
        if not self.spindle_on or self.target_rpm <= 0:
            self.target_rpm = self.target_rpm if self.spindle_on else 0.0
            # Coast down rather than stopping dead.
            self.current_rpm = max(0.0, self.current_rpm - MAX_RPM * dt)
            self.pwm = 0.0
            return

        commanded = self.target_rpm * (self.spindle_override / 100.0)

        # Integrating controller: accumulate PWM until the error closes.
        error = commanded - self.current_rpm
        self.pwm = _clamp(self.pwm + PWM_P_TERM * error * (dt / 0.1), 0.0, MAX_PWM)

        # What the spindle can actually deliver at this effort under this
        # load. Load consumes PWM budget first; whatever is left drives speed.
        spare = self.pwm - self.load * LOAD_PWM_FRACTION
        achievable = min(MAX_RPM, MAX_RPM * max(0.0, spare) / NO_LOAD_PWM_FRACTION)

        # First-order approach to the achievable speed.
        self.current_rpm += (achievable - self.current_rpm) * min(1.0, 6.0 * dt)
        self.current_rpm = max(0.0, self.current_rpm)

    def _tick_thermal(self, dt: float) -> None:
        if self.spindle_on and self.current_rpm > 0:
            duty = self.pwm * (0.35 + 0.65 * self.load)
            self.spindle_temp += TEMP_RISE_RATE * duty * dt
        else:
            self.spindle_temp -= TEMP_DECAY_RATE * dt
        self.spindle_temp = max(AMBIENT_TEMP_C, self.spindle_temp)
        self.power_temp = AMBIENT_TEMP_C + (self.spindle_temp - AMBIENT_TEMP_C) * 0.6

    def settle(self, seconds: float = 3.0, dt: float = 0.05) -> None:
        """Run the model forward until the spindle loop has converged."""
        steps = max(1, int(seconds / dt))
        for _ in range(steps):
            self.tick(dt)

    @property
    def is_saturated(self) -> bool:
        """True once the spindle has no headroom left to hold commanded RPM."""
        return self.pwm >= MAX_PWM - 1e-9

    @property
    def rpm_droop(self) -> float:
        """Fraction the spindle has fallen below its commanded speed."""
        commanded = self.target_rpm * (self.spindle_override / 100.0)
        if not self.spindle_on or commanded <= 0:
            return 0.0
        return max(0.0, (commanded - self.current_rpm) / commanded)

    # ------------------------------------------------------------------
    # Status reporting
    # ------------------------------------------------------------------
    def status_line(self) -> str:
        """Render a status report in the form the controller parses.

        Field order and arity follow the firmware. In particular ``S:`` is
        emitted with nine fields, which is the arity the controller requires
        before it will read spindle temperature (index 4) and external output
        (last index).
        """
        m, w = self.machine, self._work_position()
        parts = [
            self.state,
            f"MPos:{m.x:.3f},{m.y:.3f},{m.z:.3f},{m.a:.3f}",
            f"WPos:{w.x:.3f},{w.y:.3f},{w.z:.3f},{w.a:.3f}",
            f"F:{self.feed_current:.1f},{self.feed_target:.1f},{self.feed_override:.1f}",
            f"S:{self.current_rpm:.1f},{self.target_rpm:.1f},{self.spindle_override:.1f},{self.vacuum:d},{self.spindle_temp:.1f},{self.power_temp:.1f},0,0,{self.ext_out:d}",
            f"T:{self.tool:d},{self.tlo:.3f},{self.target_tool:d},{self.target_collet:d}",
            f"W:{self.wp_voltage:.2f}",
            f"L:{self.laser_mode:d},0,0,0.0,0.0",
            f"C:{MACHINE_CARVERA:d},{self.func_setting:d},{self.inch_mode:d},{self.absolute_mode:d}",
            f"G:{self.wcs:d}",
            f"R:{self.rotation_angle:.3f}",
            # Spindle PWM effort. Emitted by the firmware since 2.1.0c as its
            # own field rather than an addition to S:, so appending here is
            # safe for parsers that key on field names.
            f"PWM:{self.pwm:.3f}",
        ]
        return "<" + "|".join(parts) + ">"

    def _work_position(self) -> Axes:
        return Axes(
            self.machine.x - self.work_offset.x,
            self.machine.y - self.work_offset.y,
            self.machine.z - self.work_offset.z,
            self.machine.a - self.work_offset.a,
        )

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------
    def execute(self, line: str) -> str:
        """Apply one MDI line. Returns text the machine would print back."""
        text = line.split(";")[0].split("(")[0].strip()
        if not text:
            return ""

        words = _split_words(text)
        out = []

        for letter, value in words:
            if letter == "M":
                out.append(self._handle_m(value, words))
            elif letter == "G":
                out.append(self._handle_g(value, words))
            elif letter == "T":
                self.target_tool = int(value)

        if text.lower() == "version":
            return "version = Carvera Simulator, 2.2.0-sim"
        if text.lower() == "model":
            return f"model = C1, {MACHINE_CARVERA}, {self.func_setting}, 0"

        return "\n".join(p for p in out if p)

    def _handle_m(self, value: float, words: list) -> str:
        code = round(value, 1)
        if code in (3.0, 4.0):
            self.spindle_on = True
            self.state = "Run"
            s = _word_value(words, "S")
            if s is not None:
                self.target_rpm = _clamp(s, 0.0, MAX_RPM)
            return ""
        if code == 5.0:
            self.spindle_on = False
            self.target_rpm = 0.0
            self.state = "Idle"
            return ""
        if code == 6.0:
            t = _word_value(words, "T")
            if t is not None:
                self.tool = int(t)
                self.target_tool = -1
                self.tlo = 30.0 + (self.tool * 1.5)
            return f"Tool change to T{self.tool:d} complete"
        if code == 491.1:
            # Tool-break check: compare a fresh measurement against stored TLO.
            tolerance = _word_value(words, "H") or 0.1
            measured = self.tlo + self.probe_vars.get("tool_break_delta", 0.0)
            if abs(measured - self.tlo) > tolerance:
                self.halt_reason = 8
                self.state = "Alarm"
                return f"ERROR: Tool break detected. Delta {abs(measured - self.tlo):.3f} exceeds {tolerance:.3f}"
            return "Tool length within tolerance"
        return ""

    def _handle_g(self, value: float, words: list) -> str:
        code = round(value, 1)
        if code in (0.0, 1.0):
            for axis in ("X", "Y", "Z", "A"):
                v = _word_value(words, axis)
                if v is not None:
                    setattr(self.machine, axis.lower(), getattr(self.work_offset, axis.lower()) + v)
            f = _word_value(words, "F")
            if f is not None:
                self.feed_target = f
            self.feed_current = self.feed_target if code == 1.0 else 0.0
            return ""
        if code == 53.0:
            return ""
        if 54.0 <= code <= 59.0:
            self.wcs = int(code) - 54
            return ""
        return ""

    # ------------------------------------------------------------------
    # Fault injection
    # ------------------------------------------------------------------
    def inject_halt(self, reason: int, message: str = "") -> str:
        self.state = "Alarm"
        self.halt_reason = reason
        return "ERROR: {}".format(message or "simulated halt")

    def clear_halt(self) -> None:
        self.state = "Idle"
        self.halt_reason = None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _split_words(text: str) -> list:
    """Split a G-code line into (letter, value) pairs."""
    words = []
    token = ""
    for ch in text.upper() + " ":
        if ch.isalpha():
            if token:
                words.append(token)
            token = ch
        elif ch.isspace():
            if token:
                words.append(token)
            token = ""
        else:
            token += ch
    out = []
    for w in words:
        try:
            out.append((w[0], float(w[1:]) if len(w) > 1 else 0.0))
        except ValueError:
            continue
    return out


def _word_value(words: list, letter: str) -> float | None:
    for ltr, value in words:
        if ltr == letter:
            return value
    return None
