"""Compact configured-pocket review; refresh is an explicit read-only query."""

import time

from kivy.metrics import dp

from carveracontroller.desktop_components import Action, AdaptiveGrid, Surface, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.slot_inventory import inventory_rows


class SlotInventoryPanel(Surface):
    def __init__(self, workspace):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None)
        self.workspace = workspace
        self.signature = None
        self.page = 0
        self.rows = ()
        self.query_error = ""
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Configured ATC pockets", 14, height=26, bold=True))
        self.note = content_label("")
        self.add_widget(self.note)
        self.read_button = Action("Read pocket coordinates", self.query, height=dp(34))
        controls = AdaptiveGrid(max_cols=3, min_width=145, row_height=34, spacing=dp(6))
        self.previous = Action("Previous pockets", lambda: self.change_page(-1), height=dp(34))
        self.next = Action("Next pockets", lambda: self.change_page(1), height=dp(34))
        for button in (self.read_button, self.previous, self.next):
            controls.add_widget(button)
        self.add_widget(controls)
        self.tiles = AdaptiveGrid(max_cols=3, min_width=165, row_height=72, spacing=dp(6))
        self.add_widget(self.tiles)
        self.add_widget(
            content_label(
                "M889 reports configured coordinates. Pocket occupancy and installed cutter identity remain unknown. Local tool numbers are declarations; no tool change or slot write is offered here."
            )
        )
        self.refresh()

    def query(self):
        self.query_error = ""
        try:
            self.workspace.machine.controller.query_slot_inventory()
        except ValueError as exc:
            self.query_error = str(exc)
            self.refresh()
            return
        self.refresh()

    def refresh(self):
        ws = self.workspace
        controller = ws.machine.controller
        now = time.monotonic()
        with controller._adaptive_lock:
            inventory = controller.slot_inventory
            inventory.expire(controller._connection_generation, now)
            receipt, pending, error = inventory.receipt, inventory.pending, inventory.error
            pose = controller.observed_pose
        active = ws.connected and pose is not None and pose.fresh(now) and pose.state == "Idle"
        self.read_button.disabled = pending or not active
        table = ws.machine.gcode_viewer.library_tool_table_mm
        rows = inventory_rows(receipt, table)
        age = now - receipt.observed_at if receipt else None
        state = "current receipt" if active and age is not None and 0 <= age <= 30 else "historical receipt"
        self.note.text = (
            f"{len(receipt.slots)} configured pockets · {state} · {max(0, age):.0f}s ago\nResponse SHA-256 {receipt.response_sha256[:16]}… · session {receipt.generation}"
            if receipt
            else error
        )
        if self.query_error:
            self.note.text = f"Query unavailable: {self.query_error}\n" + self.note.text
        signature = (rows, pending, error, state)
        if signature == self.signature:
            return
        self.signature = signature
        self.rows = rows
        self.page = min(self.page, max(0, (len(rows) - 1) // 6))
        self.render()

    def change_page(self, delta):
        self.page = max(0, min(self.page + delta, max(0, (len(self.rows) - 1) // 6)))
        self.render()

    def render(self):
        self.tiles.clear_widgets()
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 6 >= len(self.rows)
        for row in self.rows[self.page * 6 : (self.page + 1) * 6]:
            number = row["number"]
            position = (
                ", ".join(f"{v:.3f}" for v in row["position"]) + " mm"
                if row["position"] is not None
                else "Coordinates unobserved"
            )
            declared = row["declared_name"] or ("Unnamed local tool" if row["declared"] else "No local assignment")
            tile = Action(
                f"T{number}\n{position}\nDeclared: {declared}\nContents: unknown",
                lambda n=number: self.review_tool(n),
                height=dp(72),
            )
            tile.halign = "left"
            tile.valign = "middle"
            tile.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0] - dp(12), size[1])))
            self.tiles.add_widget(tile)

    def review_tool(self, number):
        comparison = self.workspace.tool_comparison
        comparison.focus()
        comparison.choose(number)
