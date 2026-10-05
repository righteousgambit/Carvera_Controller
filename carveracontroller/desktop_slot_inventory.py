"""Compact configured-pocket review; refresh is an explicit read-only query."""

import threading
import time
from datetime import datetime

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Surface, label
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
        self.show_targets = False
        self.storage_busy = False
        self.saved_receipt = None
        self.saved_page = 0
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Configured ATC positions", 14, height=26, bold=True))
        self.note = content_label("")
        self.add_widget(self.note)
        self.read_button = Action("Read ATC positions", self.query, height=dp(34))
        controls = AdaptiveGrid(max_cols=3, min_width=145, row_height=34, spacing=dp(6))
        self.previous = Action("Previous pockets", lambda: self.change_page(-1), height=dp(34))
        self.next = Action("Next pockets", lambda: self.change_page(1), height=dp(34))
        for button in (self.read_button, self.previous, self.next):
            controls.add_widget(button)
        self.add_widget(controls)
        self.target_button = Action("Show configured targets", self.toggle_targets, height=dp(32))
        self.add_widget(self.target_button)
        self.add_widget(content_label("Six targets per page · nominal CAD frame · G53 axis reference"))
        self.tiles = AdaptiveGrid(max_cols=3, min_width=165, row_height=72, spacing=dp(6))
        self.add_widget(self.tiles)
        exchange = AdaptiveGrid(max_cols=2, min_width=145, row_height=32, spacing=dp(6))
        self.save_button = Action("Save receipt…", self.export_receipt, height=dp(32))
        self.review_button = Action("Review saved receipt…", self.review_saved, height=dp(32))
        exchange.add_widget(self.save_button)
        exchange.add_widget(self.review_button)
        self.add_widget(exchange)
        self.storage_note = content_label("")
        self.add_widget(self.storage_note)
        self.saved_selector = Choice(text="Historical position", values=())
        self.saved_selector.bind(text=lambda *_: self.describe_saved())
        self.saved_selector.size_hint_y = None
        self.saved_selector.height = 0
        self.saved_selector.opacity = 0
        self.saved_selector.disabled = True
        self.add_widget(self.saved_selector)
        self.saved_navigation = AdaptiveGrid(max_cols=2, min_width=145, row_height=32, spacing=dp(6))
        self.saved_previous = Action("Previous saved positions", lambda: self.change_saved_page(-1), height=dp(32))
        self.saved_next = Action("Next saved positions", lambda: self.change_saved_page(1), height=dp(32))
        self.saved_navigation.add_widget(self.saved_previous)
        self.saved_navigation.add_widget(self.saved_next)
        self.saved_note = content_label("")
        self.add_widget(self.saved_note)
        self.add_widget(
            content_label(
                "Configured coordinates only · physical occupancy unknown. Select a pocket to review its declared tool."
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
        self.save_button.disabled = self.storage_busy or receipt is None
        self.review_button.disabled = self.storage_busy
        table = ws.machine.gcode_viewer.library_tool_table_mm
        rows = inventory_rows(receipt, table)
        age = now - receipt.observed_at if receipt else None
        state = "current receipt" if active and age is not None and 0 <= age <= 30 else "historical receipt"
        self.note.text = (
            f"{len(receipt.slots)} configured positions · {state} · {max(0, age):.0f}s ago\nResponse SHA-256 {receipt.response_sha256[:16]}… · session {receipt.generation}"
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

    def toggle_targets(self):
        self.show_targets = not self.show_targets
        self.target_button.text = "Hide configured targets" if self.show_targets else "Show configured targets"

    def overlay_rows(self):
        """Snapshot only this connection's receipt; never queries or trusts stale tile data."""
        if not self.show_targets:
            return ()
        controller = self.workspace.machine.controller
        with controller._adaptive_lock:
            inventory = controller.slot_inventory
            inventory.expire(controller._connection_generation, time.monotonic())
            receipt = inventory.receipt
        if receipt is None:
            return ()
        observed = {slot.number: slot.position for slot in receipt.slots}
        return tuple(
            (row["number"], observed[row["number"]])
            for row in self.rows[self.page * 6 : (self.page + 1) * 6]
            if row["number"] in observed
        )

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
                f"{'T0 · firmware position' if number == 0 else f'T{number}'}\n{position}\nDeclared: {declared}\nContents: unknown",
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

    def storage_job(self, work, done):
        if self.storage_busy:
            return
        self.storage_busy = True
        self.storage_note.text = "Reading receipt bytes…"
        self.refresh()

        def worker():
            result, error = None, None
            try:
                result = work()
            except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
                error = str(exc)

            def deliver(_dt):
                self.storage_busy = False
                if error:
                    self.storage_note.text = error
                else:
                    done(result)
                self.refresh()

            Clock.schedule_once(deliver, 0)

        threading.Thread(target=worker, name="atc-receipt-storage", daemon=True).start()

    def export_receipt(self):
        if self.storage_busy:
            return
        controller = self.workspace.machine.controller
        with controller._adaptive_lock:
            controller.slot_inventory.expire(controller._connection_generation, time.monotonic())
            receipt = controller.slot_inventory.receipt
        if receipt is None:
            self.storage_note.text = "Read a complete configuration receipt before saving"
            return
        from carveracontroller.machine.slot_exchange import export_file

        def saved(result):
            self.workspace.last_atc_export = result
            self.storage_note.text = f"Saved and read back {result['pockets']} positions · SHA-256 {result['sha256']}"

        self.workspace.choose_profile_file(
            lambda path: self.storage_job(lambda: export_file(receipt, path), saved),
            save=True,
            extension=".cvatc",
            title="Save ATC configuration receipt",
        )

    def review_saved(self):
        if self.storage_busy:
            return
        from carveracontroller.machine.slot_exchange import read_file

        def loaded(result):
            value, file_hash = result
            self.saved_receipt = value["payload"]
            self.saved_page = 0
            if self.saved_navigation.parent is None:
                self.add_widget(self.saved_navigation, index=self.children.index(self.saved_selector) + 1)
            self.saved_selector.height = dp(32)
            self.saved_selector.opacity = 1
            self.saved_selector.disabled = False
            self.change_saved_page(0)
            self.storage_note.text = f"Historical receipt · file SHA-256 {file_hash}"
            self.describe_saved()

        self.workspace.choose_profile_file(
            lambda path: self.storage_job(lambda: read_file(path), loaded),
            extension=".cvatc",
            title="Review historical ATC receipt",
        )

    def change_saved_page(self, delta):
        if self.saved_receipt is None:
            return
        slots = self.saved_receipt["slots"]
        last = (len(slots) - 1) // 6
        self.saved_page = max(0, min(last, self.saved_page + delta))
        self.saved_selector.values = tuple(
            f"T{slot['number']}" for slot in slots[self.saved_page * 6 : (self.saved_page + 1) * 6]
        )
        if self.saved_selector.text not in self.saved_selector.values:
            self.saved_selector.text = self.saved_selector.values[0]
        self.saved_previous.disabled = self.saved_page == 0
        self.saved_next.disabled = self.saved_page == last

    def describe_saved(self):
        if self.saved_receipt is None:
            return
        number = self.saved_selector.text
        slot = next((s for s in self.saved_receipt["slots"] if f"T{s['number']}" == number), None)
        if slot is None:
            return
        source = self.saved_receipt["source"]
        position = ", ".join(f"{v:.3f}" for v in slot["position_mm"])
        timestamp = datetime.fromisoformat(self.saved_receipt["completed_at"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.saved_note.text = f"Historical {number} · {position} mm · contents unknown\n{source.get('model', 'Unknown model')} · {source.get('firmware', 'Unknown firmware')} · {source.get('address', 'Unknown address')}\nHost completion: {timestamp}"
