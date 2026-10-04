"""Physical assemblies and explicit raw-report attribution in the workbench."""

from datetime import datetime, timezone

from kivy.core.window import Window
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
        self.edit_button = Action("Edit assembly", self.edit_assembly)
        self.release_button = Action("Remove declaration", self.review_release)
        self.profile_button = Action("Open cutter design", self.open_profile)
        actions.add_widget(self.edit_button)
        actions.add_widget(self.release_button)
        actions.add_widget(self.profile_button)
        self.history_button = Action("View history", self.show_history)
        actions.add_widget(self.history_button)
        self.add_widget(actions)
        self.result = wrapped()
        self.add_widget(self.result)
        self.refresh(force=True)

    @property
    def store(self):
        return self.comparison.workspace.machine.tool_custody

    def selected(self):
        return self.store.assembly(self.selected_id)

    def select_assembly(self, _choice, value):
        self.selected_id = self.options.get(value)
        self.refresh(force=True)

    def refresh(self, force=False):
        ws = self.comparison.workspace
        machine = ws.selected_machine_profile
        signature = (
            id(self.store),
            self.store.generation,
            self.selected_id,
            self.comparison.selected,
            machine,
            self.store.error,
            getattr(ws.machine, "tool_custody_capture_error", None),
        )
        if not force and self._signature == signature:
            return
        self._signature = signature
        events = self.store.events
        self.options = {f"{e['name']} · {e['id'][:8]}": e["id"] for e in self.store.assemblies()}
        self.choice.values = tuple(self.options)
        assembly = self.selected()
        selected_number = self.comparison.selected
        self.assign_button.disabled = not (assembly and machine and selected_number)
        self.edit_button.disabled = not assembly
        self.history_button.disabled = not assembly
        self.release_button.disabled = not assembly or not any(
            e["assembly_id"] == assembly["id"] for e in self.store.locations().values()
        )
        self.profile_button.disabled = not assembly or not assembly["profile_id"]
        linked = {e["report_id"] for e in events if e["kind"] == "link"}
        unassigned = sum(e["kind"] == "report" and e["id"] not in linked for e in events)
        lines = [
            f"{len(self.options)} saved assemblies · {unassigned} unassigned calibration receipts",
            "Local declarations and report links require operator attribution; they do not verify installed hardware.",
        ]
        if assembly:
            lines += [
                f"Assembly ID: {assembly['id']} · revision {assembly['revision_count']} ({assembly['revision_id'][:8]})",
                f"Holder: {assembly['holder'] or 'Unknown'} · declared stickout: {assembly['stickout_mm'] if assembly['stickout_mm'] is not None else 'Unknown'} mm",
            ]
            machine_names = {p["id"]: p["name"] for p in ws.profile_store.data["machines"]} if ws.profile_store else {}
            locations = [
                f"{machine_names.get(key[0], key[0])} / T{key[1]} ({'current definition' if event.get('revision_id') == assembly['revision_id'] else 'older or unversioned definition; reconcile'})"
                for key, event in self.store.locations().items()
                if event["assembly_id"] == assembly["id"]
            ]
            lines.append("Declared locations: " + (", ".join(locations) or "None"))
            reports = self.store.assembly_reports(assembly["id"])
            lines.append(
                f"{len(reports)} attributed calibration receipts · latest shown below; View history for earlier evidence"
            )
            history_lines = []
            attributions = {e["report_id"]: e for e in events if e["kind"] == "link"}
            for event in reversed(reports[-10:]):
                revision = attributions[event["id"]].get("revision_id")
                association = (
                    "current definition"
                    if revision == assembly["revision_id"]
                    else "older definition"
                    if revision
                    else "unversioned attribution"
                )
                history_lines.append(
                    f"Calibration attribution: {association} · {revision[:8] if revision else 'revision unknown'}"
                )
                report = event["report"]
                samples = ", ".join(f"{v:.6g}" for v in report["measurements"])
                history_lines.append(
                    f"{stamp(report['timestamp'])} · T{event['tool_number'] if event['tool_number'] is not None else 'Unknown'} · source {event['endpoint'] or 'Unknown'}\nSamples mm: {samples} · spread {report['max_delta']:.6g} mm · applied TLO {report['applied'] if report['applied'] is not None else 'Unknown'} mm"
                )
            lines.extend(history_lines[:2])
            lines.append("Spread is raw repeatability evidence, not a diagnosis of cutter wear or damage.")
            history_lines.append("Definition history · latest 10 shown")
            for revision in reversed(self.store.revisions(assembly["id"])[-10:]):
                history_lines.append(
                    f"{stamp(revision['at'])} · {revision['id'][:8]} · {revision['name']} · holder {revision['holder'] or 'Unknown'} · stickout {revision['stickout_mm']} mm · design {revision['profile_id'] or 'None'}\n{revision.get('note', 'Initial definition')}"
                )
            history_lines.append("Declared location history · latest 10 shown")
            moves = [e for e in events if e["kind"] in ("assignment", "release") and e["assembly_id"] == assembly["id"]]
            for move in reversed(moves[-10:]):
                place = f"{machine_names.get(move['machine_id'], move['machine_id'])} / T{move['slot']}"
                detail = (
                    f"Declared at {place}"
                    if move["kind"] == "assignment"
                    else f"Declaration removed from {place} · {move['note']}"
                )
                history_lines.append(f"{stamp(move['at'])} · {detail}")
            self.history_text = "\n".join(history_lines)
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
        popup = Popup(title=title, content=body, size_hint=(0.72, None))

        def resize(*_):
            popup.height = min(Window.height * 0.85, max(dp(260), content.height + error.height + dp(154)))

        content.bind(height=resize)
        error.bind(height=resize)
        popup.bind(width=resize)
        resize()

        def apply():
            if action is None:
                popup.dismiss()
                return
            try:
                action()
                self.refresh(force=True)
                self.result.text = "Saved local custody event. No controller command sent."
                popup.dismiss()
            except (ValueError, OSError) as exc:
                error.text = str(exc)
                error.color = AMBER

        if action is not None:
            controls.add_widget(Action("Cancel", popup.dismiss))
        controls.add_widget(Action(button, apply, primary=True))
        body.add_widget(controls)
        self.popup, self.popup_apply = popup, apply
        popup.open()

    def show_history(self):
        self.refresh(force=True)
        if not self.selected():
            return
        history = wrapped()
        history.text = self.history_text
        self.dialog("Assembly definition & calibration history", [history], None, "Close")

    def new_assembly(self):
        self.assembly_editor()

    def edit_assembly(self):
        assembly = self.selected()
        if assembly:
            self.assembly_editor(assembly)

    def assembly_editor(self, assembly=None):
        current = assembly or {}
        self.name_input = Field(text=current.get("name", ""), hint_text="e.g. Quarter-inch ball #1")
        self.holder_input = Field(text=current.get("holder", ""), hint_text="e.g. Collet A")
        stickout = current.get("stickout_mm")
        self.stickout_input = Field(
            text=f"{stickout:g} mm" if stickout is not None else "", hint_text="e.g. 31 mm or 1/4 in"
        )
        self.note_input = Field(hint_text="Required change reason / physical work performed")
        profiles = self.comparison.workspace.profile_store
        designs = {"No cutter design linked": ""}
        if profiles:
            designs.update({f"{p['name']} · {p['id'][:8]}": p["id"] for p in profiles.data["tools"]})
        profile_id = current.get("profile_id", "")
        if profile_id and profile_id not in designs.values():
            designs[f"Missing design · {profile_id[:8]}"] = profile_id
        self.design_input = design = Choice(
            text=next(key for key, identity in designs.items() if identity == profile_id), values=tuple(designs)
        )
        explanation = wrapped()
        explanation.text = (
            f"Edit {assembly['name']} · revision {assembly['revision_count']}. Save appends a definition; previous measurements and location declarations retain their original revision."
            if assembly
            else "Create a distinct physical assembly. This does not load a cutter profile or declare a machine location."
        )

        def save():
            value = self.stickout_input.text.strip()
            stickout = parse_quantity(value, "length", minimum=0.001, maximum=1000) if value else None
            fields = {
                "name": self.name_input.text.strip(),
                "holder": self.holder_input.text.strip(),
                "stickout_mm": stickout,
                "profile_id": designs[design.text],
            }
            if assembly:
                self.store.revise(assembly["id"], assembly["revision_id"], **fields, note=self.note_input.text.strip())
                self.selected_id = assembly["id"]
            else:
                self.selected_id = self.store.create_assembly(**fields)["id"]
            self.refresh(force=True)
            self.choice.text = next(key for key, identity in self.options.items() if identity == self.selected_id)

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
        fields = [explanation, form]
        if assembly:
            fields += [label("Reason for revision", 11, MUTED, height=24), self.note_input]
        self.dialog(
            "Edit physical assembly" if assembly else "New physical assembly",
            fields,
            save,
            "Save revision" if assembly else "Create assembly",
        )

    def open_profile(self):
        assembly = self.selected()
        ws = self.comparison.workspace
        if not assembly or not assembly["profile_id"] or not ws.profile_store:
            return
        if not any(p["id"] == assembly["profile_id"] for p in ws.profile_store.data["tools"]):
            self.result.text = (
                "Linked cutter design is missing. Edit the assembly to relink; its historical reference is retained."
            )
            return
        ws._open_profiles()
        ws.profile_library.select_record("tools", assembly["profile_id"])

    def review_release(self):
        assembly = self.selected()
        if not assembly:
            return
        available = {
            f"{key[0]} / T{key[1]}": e
            for key, e in self.store.locations().items()
            if e["assembly_id"] == assembly["id"]
        }
        if not available:
            self.result.text = "This assembly has no declared location."
            return
        location = Choice(text=next(iter(available)), values=tuple(available))
        note = Field(hint_text="Required reason / where the assembly was moved")
        summary = wrapped()
        summary.text = f"Remove the declared location for {assembly['name']}. The physical assembly, revisions and calibration evidence remain in history. This records your assertion and sends no tool-change command."

        def remove():
            previous = available[location.text]
            self.store.release(
                previous["machine_id"], previous["slot"], assembly["id"], previous["id"], note.text.strip()
            )

        self.dialog("Review declaration removal", [summary, location, note], remove, "Remove declaration")

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
            lambda: self.store.assign(
                machine["id"],
                slot,
                assembly["id"],
                assembly["revision_id"],
                expected_assignment_id=previous["id"] if previous else None,
            ),
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
            preview.text = f"Attribute to {assembly['name']} ({assembly['id']}) · definition {assembly['revision_id'][:8]}.\nReceipt {event['id']}\nConnection source: {event['endpoint'] or 'Unknown'}\nTool number at receipt: T{event['tool_number'] if event['tool_number'] is not None else 'Unknown'}\nSamples mm: {', '.join(f'{v:.6g}' for v in event['report']['measurements'])}\nReported spread: {event['report']['max_delta']:.6g} mm\nApplied TLO: {event['report']['applied'] if event['report']['applied'] is not None else 'Unknown'} mm\nConfirm the physical identity from your setup records. Slot numbers and connection addresses alone do not establish it."

        choice.bind(text=update)
        update()
        note = Field(hint_text="Required attribution evidence / note")
        self.dialog(
            "Review calibration attribution",
            [choice, preview, note],
            lambda: self.store.link(
                available[choice.text]["id"], assembly["id"], note.text.strip(), assembly["revision_id"]
            ),
            "Attribute receipt",
        )
