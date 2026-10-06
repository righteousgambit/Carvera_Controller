"""Setup evidence inspector and contextual navigation, entirely local/read-only."""

import time
from dataclasses import asdict
from datetime import datetime, timezone

from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    ACCENT,
    AMBER,
    MUTED,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    Surface,
    label,
)
from carveracontroller.desktop_planning import planning_field
from carveracontroller.desktop_scroll_navigation import queue_reveal
from carveracontroller.machine.setup_readiness import SetupEvidenceStore, evaluate_setup


def wrapped(text, size=11, color=MUTED):
    item = Label(
        text=text, font_name="Roboto", font_size=sp(size), color=color, halign="left", valign="middle", size_hint_y=None
    )
    item.bind(
        width=lambda obj, width: setattr(obj, "text_size", (width, None)),
        texture_size=lambda obj, texture: setattr(obj, "height", texture[1] + dp(8)),
    )
    return item


class SetupReadiness:
    def __init__(self, workspace):
        self.workspace = workspace
        self.store = SetupEvidenceStore()
        self.items = ()
        self.popup = None
        self.page = None
        self.signature = None
        self.record_popup = None
        self.strip = Surface(
            orientation="horizontal", padding=(dp(7), dp(3)), spacing=dp(7), size_hint_y=None, height=dp(38)
        )
        self.measured_count = 0
        self.summary = label("Inspect setup evidence", 11, MUTED, 32, shorten=True, max_lines=2)
        self.summary.bind(width=lambda *_: self._summary_text())
        self.next_button = Action("Inspect setup", self.next_action, size_hint_x=None, width=dp(144), height=dp(32))
        self.strip.add_widget(self.summary)
        self.strip.add_widget(self.next_button)
        self.strip.add_widget(Action("Evidence", self.open, size_hint_x=None, width=dp(76), height=dp(32)))

    def _summary_text(self):
        prefix = "Setup evidence · " if self.summary.width >= dp(150) else ""
        self.summary.text = f"{prefix}{self.measured_count}/4 measured"

    def snapshot(self):
        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        setup = viewer.machine_setup
        profile = ws.selected_machine_profile or {}
        machine = {key: profile.get(key) for key in ("id", "host", "port", "model", "cad_path")}
        choices = {key: field.text for key, field in ws.component_choices.items()}
        workholding = {
            "machine": machine,
            "fixture": choices.get("fixture"),
            "vise": choices.get("workholding"),
            "offset": viewer.workholding_offset_mm,
            "rotation": viewer.workholding_rotation_deg,
            "jaws": viewer.jaw_offset_mm,
        }
        stock = {"workholding": workholding, "size": setup.stock_size_mm, "origin": setup.stock_origin_mm}
        tools = {
            str(n): {**asdict(tool), "tool_type": tool.tool_type.value}
            for n, tool in viewer.library_tool_table_mm.items()
        }
        program = ws.operation_panel.program
        required = sorted({n for operation in program.operations for n in operation.tool_ids}) if program else []
        missing = [number for number in required if str(number) not in tools]
        snapshots = {
            "workholding": workholding,
            "stock": stock,
            "tools": {"machine": machine, "tools": tools, "required_tools": required},
            "offsets": {"stock": stock, "tools": tools, "preview_offset": setup.work_offset_mm},
        }
        present = {
            "stock": setup.stock_size_mm is not None,
            "workholding": bool(profile),
            "tools": bool(tools) and not missing,
            "offsets": bool(setup.alignment_confirmed),
        }
        present = {key: value and bool(profile.get("id")) for key, value in present.items()}
        return profile.get("id"), snapshots, present

    def refresh(self):
        machine_id, snapshots, present = self.snapshot()
        self.items = evaluate_setup(machine_id, snapshots, present, self.store, time.time())
        measured = sum(item.state == "measured" for item in self.items)
        unresolved = next((item for item in self.items if item.state != "measured"), None)
        pose = self.workspace.machine.gcode_viewer.observed_pose
        fresh = self.workspace.connected and pose is not None and pose.fresh(time.monotonic())
        if hasattr(self, "telemetry_note"):
            if fresh:
                tool = f"T{pose.tool}" if pose.tool is not None else "Tool unknown"
                length = f"{pose.tool_length_mm:.3f} mm" if pose.tool_length_mm is not None else "unknown"
                self.telemetry_note.text = (
                    f"Controller report · {tool} · TLO {length} · {time.monotonic() - pose.timestamp:.2f}s ago"
                )
                self.telemetry_note.color = ACCENT
            else:
                self.telemetry_note.text = "Controller report unavailable or stale · inspect connection"
                self.telemetry_note.color = AMBER
        filename = self.workspace.app.selected_local_filename or self.workspace.app.selected_remote_filename
        if not filename:
            self.next_button.text = "Choose program"
        elif unresolved:
            self.next_button.text = {
                "stock": "Review stock",
                "workholding": "Review mounting",
                "tools": "Review tools",
                "offsets": "Review offset",
            }[unresolved.key]
        elif not fresh:
            self.next_button.text = "Inspect connection"
        else:
            self.next_button.text = "Review program"
        self.measured_count = measured
        self._summary_text()
        signature = tuple((item.state, item.detail, str(item.receipt)) for item in self.items)
        signature += (fresh,)
        if (
            self.page is not None
            and self.workspace.inspector_pages.current == "Readiness"
            and signature != self.signature
        ):
            self._render()
        self.signature = signature

    def next_action(self):
        self.refresh()
        ws = self.workspace
        if not (ws.app.selected_local_filename or ws.app.selected_remote_filename):
            ws.select("Job")
            ws._choose_program()
        elif any(item.state != "measured" for item in self.items):
            self.open()
        elif (
            not ws.connected
            or not ws.machine.gcode_viewer.observed_pose
            or not ws.machine.gcode_viewer.observed_pose.fresh(time.monotonic())
        ):
            ws.select("Settings")
        else:
            ws.select("Job")

    def build_page(self):
        body = BoxLayout(orientation="vertical", spacing=dp(8))
        body.add_widget(label("Setup evidence", 18, height=30, bold=True))
        body.add_widget(
            wrapped("Measurement receipts describe your physical checks. The controller reports live state separately.")
        )
        self.state_summary = wrapped("Setup evidence · awaiting current dependencies", 11)
        body.add_widget(self.state_summary)
        self.telemetry_note = wrapped("Controller report unavailable or stale", 10)
        body.add_widget(self.telemetry_note)
        self.section_navigation = AdaptiveGrid(max_cols=4, min_width=70, row_height=32)
        self.section_actions = {}
        for key, title in (("stock", "Stock"), ("workholding", "Mounting"), ("tools", "Tools"), ("offsets", "Offset")):
            action = Action(title, lambda key=key: self.reveal_section(key))
            self.section_actions[key] = action
            self.section_navigation.add_widget(action)
        body.add_widget(self.section_navigation)
        self.evidence_scroll = DesktopScrollView(do_scroll_x=False)
        self.rows = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.evidence_scroll.add_widget(self.rows)
        body.add_widget(self.evidence_scroll)
        self.page = body
        return body

    def open(self):
        self.workspace.select("Readiness")
        self.refresh()
        self._render()

    def _render(self):
        self.rows.clear_widgets()
        self.evidence_cards = {}
        counts = {
            state: sum(item.state == state for item in self.items)
            for state in ("measured", "entered", "stale", "unresolved")
        }
        self.state_summary.text = (
            f"{counts['measured']} current operator receipts · {counts['entered']} declared only · "
            f"{counts['stale']} need recheck · {counts['unresolved']} need configuration"
        )
        for item in self.items:
            card = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None)
            card.bind(minimum_height=card.setter("height"))
            self.evidence_cards[item.key] = card
            state_title = {
                "measured": "Current operator receipt",
                "entered": "Declared only",
                "stale": "Recheck needed",
                "unresolved": "Configuration needed",
            }[item.state]
            heading = wrapped(item.title + " · " + state_title, 14, ACCENT if item.state == "measured" else AMBER)
            heading.bold = True
            card.add_widget(heading)
            card.add_widget(wrapped(item.detail))
            if item.receipt:
                timestamp = datetime.fromtimestamp(item.receipt["measured_at"], timezone.utc).isoformat(
                    timespec="minutes"
                )
                expiry = datetime.fromtimestamp(item.receipt["expires_at"], timezone.utc).isoformat(timespec="minutes")
                card.add_widget(
                    wrapped("Measured: " + timestamp + "\nExpires: " + expiry + " · prior receipts retained", 10)
                )
            buttons = AdaptiveGrid(max_cols=2, min_width=160, row_height=48)
            buttons.add_widget(Action("Open " + item.target, lambda item=item: self._navigate(item.target)))
            record = Action("Record measurement…", lambda item=item: self.record_dialog(item.key))
            record.disabled = item.state == "unresolved"
            buttons.add_widget(record)
            if item.receipt and item.state == "measured":
                buttons.add_widget(
                    Action("Invalidate after physical change…", lambda item=item: self.invalidate_dialog(item.key))
                )
            for action in buttons.children:
                action.halign = "center"
                action.valign = "middle"
                action.bind(width=lambda obj, width: setattr(obj, "text_size", (max(dp(1), width - dp(16)), None)))
                action.text_size = (max(dp(1), action.width - dp(16)), None)
            card.add_widget(buttons)
            self.rows.add_widget(card)
        self.rows.add_widget(
            label(
                "Controller-reported position and TLO are live telemetry, separate from these physical measurement receipts.",
                11,
                MUTED,
                48,
            )
        )

    def reveal_section(self, key):
        card = self.evidence_cards.get(key)
        if card is None:
            return
        queue_reveal(
            card,
            active=lambda: (
                self.workspace.inspector_pages.current == "Readiness" and self.evidence_cards.get(key) is card
            ),
            align_top=True,
        )

    def _navigate(self, target):
        self.workspace.select(target)

    def record_dialog(self, group):
        machine_id, snapshots, present = self.snapshot()
        if not machine_id or not present[group]:
            return
        captured = snapshots[group]
        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        grid = AdaptiveGrid(max_cols=2, min_width=220, row_height=62)
        method = planning_field(grid, "Measurement method", "", hint_text="Micrometer / indicator / probing receipt")
        source = planning_field(
            grid, "Receipt / record reference", "", hint_text="Measurement log, photo or probe result ID"
        )
        observed = planning_field(
            grid, "Measured at (UTC ISO date/time)", datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        validity = planning_field(grid, "Valid for hours (operator interval)", "8")
        form_scroll = DesktopScrollView(do_scroll_x=False)
        form_scroll.add_widget(grid)
        body.add_widget(form_scroll)
        note = label(
            "Record only after measuring the physical setup. Geometry changes invalidate dependent receipts.",
            11,
            MUTED,
            60,
        )
        body.add_widget(note)
        dialog = Popup(title="Record " + group + " measurement", content=body, size_hint=(0.85, None), height=dp(340))

        def fit_form(*_args):
            # Popup title/padding plus body padding, note, actions and spacing.
            # The former 180dp overhead left the last field row clipped.
            dialog.height = min(Window.height * 0.9, grid.height + dp(240))

        grid.bind(height=fit_form)
        Window.bind(size=fit_form)
        dialog.bind(on_dismiss=lambda *_args: Window.unbind(size=fit_form))
        fit_form()

        def save():
            try:
                current_id, current, available = self.snapshot()
                if current_id != machine_id or current[group] != captured or not available[group]:
                    raise ValueError("Setup changed while this form was open. Reopen and measure the current setup.")
                measured = datetime.fromisoformat(observed.text.strip().replace("Z", "+00:00"))
                if measured.tzinfo is None:
                    raise ValueError("Include UTC/timezone in the measurement timestamp")
                hours = float(validity.text)
                if not 0 < hours <= 8760:
                    raise ValueError("Validity must be greater than zero and no more than one year")
                if measured.timestamp() > time.time():
                    raise ValueError("Measurement cannot be dated in the future")
                self.store.record(
                    machine_id,
                    group,
                    captured,
                    source.text.strip(),
                    method.text.strip(),
                    measured.timestamp(),
                    measured.timestamp() + hours * 3600,
                )
            except (ValueError, OSError, OverflowError) as exc:
                note.text = str(exc)
                return
            dialog.dismiss()
            self.refresh()
            self._render()

        actions = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(36))
        actions.add_widget(Action("Cancel", dialog.dismiss))
        actions.add_widget(Action("Save measurement receipt", save, primary=True))
        body.add_widget(actions)
        self.record_popup = dialog
        dialog.open()

    def invalidate_dialog(self, group):
        machine_id, snapshots, _present = self.snapshot()
        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        reason = planning_field(
            body, "Physical change / reason", "", hint_text="Reclamped part / replaced identical cutter"
        )
        note = label("Retains the prior measurement; requires a new check for the current setup.", 11, MUTED, 54)
        body.add_widget(note)
        dialog = Popup(title="Invalidate " + group + " evidence", content=body, size_hint=(0.75, None), height=dp(260))

        def invalidate():
            try:
                current_id, current, _available = self.snapshot()
                if current_id != machine_id or current[group] != snapshots[group]:
                    raise ValueError("Setup changed. Reopen this action for the current setup.")
                now = time.time()
                self.store.record(
                    machine_id,
                    group,
                    current[group],
                    reason.text.strip(),
                    "Invalidated after physical change",
                    now - 1,
                    now,
                )
            except (ValueError, OSError) as exc:
                note.text = str(exc)
                return
            dialog.dismiss()
            self.refresh()
            self._render()

        buttons = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(36))
        buttons.add_widget(Action("Cancel", dialog.dismiss))
        buttons.add_widget(Action("Invalidate receipt", invalidate))
        body.add_widget(buttons)
        self.record_popup = dialog
        dialog.open()
