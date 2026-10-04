"""Physical assemblies and explicit raw-report attribution in the workbench."""

from datetime import datetime, timezone

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    AMBER,
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
from carveracontroller.machine.quantities import parse_quantity


def wrapped():
    item = Label(font_name="Roboto", font_size=sp(11), color=MUTED, halign="left", valign="top", size_hint_y=None)
    item.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
    item.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(40), size[1] + dp(12))))
    return item


def stamp(value):
    try:
        return (
            datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value > 0 else "Unknown time"
        )
    except (ValueError, OverflowError, OSError):
        return "Invalid time"


class ToolCustodyPanel(Surface):
    def __init__(self, comparison):
        super().__init__(orientation="vertical", spacing=dp(8), padding=dp(8), size_hint_y=None)
        self.comparison = comparison
        self.selected_id = None
        self._signature = None
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Physical assemblies & saved receipts", 13, height=26, bold=True))
        self.choice = Choice(text="Select an assembly", values=())
        self.choice.bind(text=self.select_assembly)
        self.add_widget(self.choice)
        self.summary = wrapped()
        self.add_widget(self.summary)
        actions = AdaptiveGrid(max_cols=3, min_width=160, row_height=36, spacing=dp(6))
        actions.add_widget(Action("New assembly", self.new_assembly))
        self.assign_button = Action("Declare at selected tool", self.review_assignment)
        actions.add_widget(self.assign_button)
        actions.add_widget(Action("Link a raw receipt", self.review_link))
        self.add_widget(actions)
        self.result = wrapped()
        self.add_widget(self.result)
        self.refresh(force=True)

    @property
    def store(self):
        return self.comparison.workspace.machine.tool_custody

    def selected(self):
        return next((e for e in self.store.events if e["id"] == self.selected_id and e["kind"] == "assembly"), None)

    def select_assembly(self, _choice, value):
        self.selected_id = self.options.get(value)
        self.refresh(force=True)

    def refresh(self, force=False):
        ws = self.comparison.workspace
        events = self.store.events
        machine = ws.selected_machine_profile
        signature = (
            events,
            self.selected_id,
            self.comparison.selected,
            machine,
            self.store.error,
            getattr(ws.machine, "tool_custody_capture_error", None),
        )
        if not force and self._signature == signature:
            return
        self._signature = signature
        self.options = {f"{e['name']} · {e['id'][:8]}": e["id"] for e in events if e["kind"] == "assembly"}
        self.choice.values = tuple(self.options)
        assembly = self.selected()
        selected_number = self.comparison.selected
        self.assign_button.disabled = not (assembly and machine and selected_number)
        linked = {e["report_id"] for e in events if e["kind"] == "link"}
        unassigned = sum(e["kind"] == "report" and e["id"] not in linked for e in events)
        lines = [
            f"{len(self.options)} saved assemblies · {unassigned} unassigned calibration receipts",
            "Local declarations and report links require operator attribution; they do not verify installed hardware.",
        ]
        if assembly:
            lines += [
                f"Assembly ID: {assembly['id']}",
                f"Holder: {assembly['holder'] or 'Unknown'} · declared stickout: {assembly['stickout_mm'] if assembly['stickout_mm'] is not None else 'Unknown'} mm",
            ]
            machine_names = {p["id"]: p["name"] for p in ws.profile_store.data["machines"]} if ws.profile_store else {}
            locations = [
                f"{machine_names.get(key[0], key[0])} / T{key[1]}"
                for key, event in self.store.locations().items()
                if event["assembly_id"] == assembly["id"]
            ]
            lines.append("Declared locations: " + (", ".join(locations) or "None"))
            reports = self.store.assembly_reports(assembly["id"])
            lines.append(f"{len(reports)} attributed calibration receipts · latest 10 shown")
            for event in reversed(reports[-10:]):
                report = event["report"]
                samples = ", ".join(f"{v:.6g}" for v in report["measurements"])
                lines.append(
                    f"{stamp(report['timestamp'])} · T{event['tool_number'] if event['tool_number'] is not None else 'Unknown'} · source {event['endpoint'] or 'Unknown'}\nSamples mm: {samples} · spread {report['max_delta']:.6g} mm · applied TLO {report['applied'] if report['applied'] is not None else 'Unknown'} mm"
                )
            lines.append("Spread is raw repeatability evidence, not a diagnosis of cutter wear or damage.")
        error = self.store.error or getattr(ws.machine, "tool_custody_capture_error", None)
        if error:
            lines.append("Persistence error: " + error)
        self.summary.text = "\n".join(lines)
        self.summary.color = AMBER if error else MUTED

    def dialog(self, title, fields, action, button):
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        scroll = DesktopScrollView()
        content = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        for widget in fields:
            content.add_widget(widget)
        scroll.add_widget(content)
        body.add_widget(scroll)
        error = wrapped()
        body.add_widget(error)
        controls = AdaptiveGrid(max_cols=2, min_width=130, row_height=36, spacing=dp(8))
        popup = Popup(title=title, content=body, size_hint=(0.65, 0.65))

        def apply():
            try:
                action()
                self.refresh(force=True)
                self.result.text = "Saved local custody event. No controller command sent."
                popup.dismiss()
            except (ValueError, OSError) as exc:
                error.text = str(exc)
                error.color = AMBER

        controls.add_widget(Action("Cancel", popup.dismiss))
        controls.add_widget(Action(button, apply, primary=True))
        body.add_widget(controls)
        self.popup, self.popup_apply = popup, apply
        popup.open()

    def new_assembly(self):
        self.name_input = Field(hint_text="e.g. Quarter-inch ball #1")
        self.holder_input = Field(hint_text="e.g. Collet A")
        self.stickout_input = Field(hint_text="e.g. 31 mm or 1/4 in")
        profiles = self.comparison.workspace.profile_store
        designs = {"No cutter design linked": ""}
        if profiles:
            designs.update({f"{p['name']} · {p['id'][:8]}": p["id"] for p in profiles.data["tools"]})
        design = Choice(text="No cutter design linked", values=tuple(designs))
        explanation = wrapped()
        explanation.text = (
            "Create a distinct physical assembly. This does not load a cutter profile or declare a machine location."
        )

        def save():
            value = self.stickout_input.text.strip()
            stickout = parse_quantity(value, "length", minimum=0.001, maximum=1000) if value else None
            assembly = self.store.create_assembly(
                self.name_input.text.strip(), self.holder_input.text.strip(), stickout, designs[design.text]
            )
            self.selected_id = assembly["id"]
            self.refresh(force=True)
            self.choice.text = next(key for key, identity in self.options.items() if identity == assembly["id"])

        form = AdaptiveGrid(max_cols=2, min_width=260, row_height=72, spacing=dp(8))
        for title, field in (
            ("Cutter design reference (optional)", design),
            ("Physical assembly name / inventory tag", self.name_input),
            ("Holder or collet identity (optional)", self.holder_input),
            ("Declared stickout (mm or in; optional)", self.stickout_input),
        ):
            group = BoxLayout(orientation="vertical", spacing=dp(4))
            group.add_widget(label(title, 11, MUTED))
            group.add_widget(field)
            form.add_widget(group)
        self.dialog("New physical assembly", [explanation, form], save, "Create assembly")

    def review_assignment(self):
        ws = self.comparison.workspace
        assembly, machine, slot = self.selected(), ws.selected_machine_profile, self.comparison.selected
        if not assembly or not machine or slot is None:
            self.result.text = "Select a saved machine profile, tool number and physical assembly first."
            return
        previous = self.store.assignment(machine["id"], slot)
        summary = wrapped()
        summary.text = f"Declare {assembly['name']} at {machine['name']} / T{slot}.\nPrevious declaration: {previous['assembly_id'] if previous else 'None'}.\nThis records your installation assertion. Any previous location for this assembly is superseded. Calibration history stays with its assembly. No ATC or offset command is sent."
        self.dialog(
            "Review assembly location",
            [summary],
            lambda: self.store.assign(machine["id"], slot, assembly["id"]),
            "Save declaration",
        )

    def review_link(self):
        assembly = self.selected()
        if not assembly:
            self.result.text = "Select an assembly before attributing a receipt."
            return
        linked = {e["report_id"] for e in self.store.events if e["kind"] == "link"}
        available = {
            f"{stamp(e['report']['timestamp'])} · T{e['tool_number'] if e['tool_number'] is not None else 'Unknown'} · {e['id'][:8]}": e
            for e in reversed(self.store.events)
            if e["kind"] == "report" and e["id"] not in linked
        }
        if not available:
            self.result.text = "No unassigned persistent calibration receipts. New console reports are saved separately from assembly identity."
            return
        choice = Choice(text=next(iter(available)), values=tuple(available))
        preview = wrapped()

        def update(*_):
            event = available[choice.text]
            preview.text = f"Attribute to {assembly['name']} ({assembly['id']}).\nReceipt {event['id']}\nConnection source: {event['endpoint'] or 'Unknown'}\nTool number at receipt: T{event['tool_number'] if event['tool_number'] is not None else 'Unknown'}\nSamples mm: {', '.join(f'{v:.6g}' for v in event['report']['measurements'])}\nReported spread: {event['report']['max_delta']:.6g} mm\nApplied TLO: {event['report']['applied'] if event['report']['applied'] is not None else 'Unknown'} mm\nConfirm the physical identity from your setup records. Slot numbers and connection addresses alone do not establish it."

        choice.bind(text=update)
        update()
        note = Field(hint_text="Required attribution evidence / note")
        self.dialog(
            "Review calibration attribution",
            [choice, preview, note],
            lambda: self.store.link(available[choice.text]["id"], assembly["id"], note.text.strip()),
            "Attribute receipt",
        )
