"""Read-only shadow decision inspector with explicit observation boundaries."""

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid, Surface, label
from carveracontroller.machine.adaptive_decisions import (
    BACKOFF_DROOP,
    BACKOFF_INTERVAL,
    FEED_CEILING,
    FEED_FLOOR,
    PWM_BACKOFF,
    PWM_RECOVERY,
    RECOVERY_DROOP,
    RECOVERY_INTERVAL,
    SEVERE_DROOP,
)


class AdaptiveDecisionPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8), padding=dp(10), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Why this feed proposal?", 13, bold=True, height=26))
        self.summary = flowing_text("Waiting for complete spindle telemetry.", 48)
        self.add_widget(self.summary)
        self.fields = {}
        for key, title in (
            ("signals", "Governing measurements"),
            ("response", "Observed response"),
            ("motion", "Motion and timing context"),
        ):
            card = Surface(orientation="vertical", padding=dp(8), spacing=dp(4), size_hint_y=None)
            card.bind(minimum_height=card.setter("height"))
            card.add_widget(label(title, 12, bold=True, height=24))
            field = flowing_text("Waiting for evidence.", 54)
            self.fields[key] = field
            card.add_widget(field)
            self.add_widget(card)
        rules = (
            f"Experimental policy: filtered droop ≥ {BACKOFF_DROOP * 100:g}% or PWM ≥ {PWM_BACKOFF * 100:g}% "
            f"backs off 10 points every {BACKOFF_INTERVAL:g}s, down to {FEED_FLOOR:g}%. "
            f"Droop < {RECOVERY_DROOP * 100:g}% and PWM ≤ {PWM_RECOVERY * 100:g}% (or unavailable) "
            f"recovers 2 points every {RECOVERY_INTERVAL:g}s, up to {FEED_CEILING:g}%. "
            f"Raw droop ≥ {SEVERE_DROOP * 100:g}% latches a fault. "
            "Droop is a load clue; contact with stock is unverified. Shadow sends no commands."
        )
        self.add_widget(flowing_text(rules, 90))
        actions = AdaptiveGrid(max_cols=3, min_width=110, row_height=34, spacing=dp(6))
        for section in ("Signal", "Baseline", "Diagnostics"):
            actions.add_widget(
                Action(
                    section, lambda section=section: workspace.monitor_section_buttons[section].dispatch("on_release")
                )
            )
        self.add_widget(actions)

    def update(self, state, connected):
        decision = state["decision"]
        active = connected and decision["proposal_percent"] is not None
        proposal = f"{decision['proposal_percent']:.0f}% shadow proposal" if active else "No current feed proposal"
        self.summary.text = (
            f"{proposal} · {decision['status'] if connected else 'disconnected'}\n"
            f"Limiting factor: {decision['limiting_factor'] if connected else 'Live connection required'}\n"
            + decision["explanation"]
        )

        def number(value, unit="", digits=2):
            return "unavailable" if value is None else f"{value:.{digits}f}{unit}"

        self.fields["signals"].text = (
            f"Unloaded baseline: {number(decision['baseline_rpm'], ' RPM', 0)}\n"
            f"Reported spindle: {number(decision['rpm'], ' RPM', 0)} · "
            f"PWM: {number(decision['pwm'] * 100 if decision['pwm'] is not None else None, '%', 1)}\n"
            f"Raw droop: {number(decision['raw_droop'] * 100 if decision['raw_droop'] is not None else None, '%')} · "
            f"Filtered: {number(decision['filtered_droop'] * 100 if decision['filtered_droop'] is not None else None, '%')}\n"
            f"Reported override: {number(decision['reported_override'], '%', 0)} · "
            f"Policy dwell remaining: {number(decision['next_adjustment_s'], ' s')}"
            + ("\nRetained measurements; live connection unavailable." if not connected else "")
        )
        response = decision["response"]
        self.fields["response"].text = (
            f"{response['status'].title()} · {response['explanation']}\n"
            f"Reported override: {response['override_before']:g}% → {response['override_after']:g}%\n"
            f"Spindle: {response['rpm_before']:g} → {response['rpm_after']:g} RPM "
            f"({response['rpm_change']:+g} RPM) · {response['elapsed_s']:.2f}s after arrival\n"
            f"Reported feed: {response['feed_before']:g} → {response['feed_after']:g} mm/min"
            if active and response["status"] != "unavailable"
            else "No current response comparison. "
            + (response["explanation"] if connected else "Live connection unavailable.")
        )
        position = decision["machine_position"]
        self.fields["motion"].text = (
            (
                f"{'Reported' if active else 'Retained'} machine position: "
                f"X {position[0]:.3f} · Y {position[1]:.3f} · Z {position[2]:.3f} mm\n"
                if position is not None
                else "Machine position unavailable.\n"
            )
            + f"Complete-sample arrival age: {number(decision['arrival_age_s'], ' s')}\n"
            "Firmware sample age and command response latency: unavailable.\n"
            "Executed source line, operation and camera exposure association: unverified."
        )
