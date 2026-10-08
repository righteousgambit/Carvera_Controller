"""Cancellable residual import/export with exact context and atomic publication."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import zlib
from copy import deepcopy
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.desktop_components import Action, Surface
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.geometry_changes import (
    asset_problems,
    capture_context,
    digest_context,
    verify_context_assets,
)
from carveracontroller.machine.simulation_preview import stock_geometry


class StockTransfer(Popup):
    """Workers own bytes; the UI grants a checked publication decision once."""

    limit = 16 * 1024 * 1024

    def __init__(self, panel, path, *, save):
        self.panel, self.path, self.save = panel, Path(path), save
        self.closed, self.decision = threading.Event(), threading.Event()
        self.active, self.publishing, self.approved = True, False, False
        self.stock = panel.rest_stock
        self.baseline = deepcopy(panel.rest_context)
        self.identity = panel.rest_identity
        self.context = capture_context(
            panel.workspace.machine.gcode_viewer, panel.workspace.operation_panel.program, verify_assets=False
        )
        self.definition_identity = self.context["program"], digest_context(self.context)
        content = Surface(orientation="vertical", padding=dp(12), spacing=dp(10))
        super().__init__(
            title="Save residual stock" if save else "Load residual stock",
            content=content,
            size_hint=(0.75, None),
            height=dp(210),
            auto_dismiss=False,
        )
        self.status = content_label("Verifying CAD and preparing snapshot… Previous results are retained.")
        content.add_widget(self.status)
        self.cancel = Action("Cancel", self.dismiss, height=dp(36))
        content.add_widget(self.cancel)
        self.bind(on_dismiss=self._close)
        panel.artifact_transfer = self
        panel.refresh_controls()
        self.open()
        try:
            threading.Thread(target=self._run, daemon=True, name="residual-stock-transfer").start()
        except (RuntimeError, OSError):
            self._finish(None, "Snapshot worker could not start; previous results and destination retained.")

    def _close(self, *_args):
        self.closed.set()
        self.decision.set()
        self.active = False
        if self.panel.artifact_transfer is self:
            self.panel.artifact_transfer = None
        self.panel.refresh_controls()

    def _check_cancel(self):
        if self.closed.is_set():
            raise InterruptedError("Snapshot transfer cancelled")

    def _verify(self):
        current = verify_context_assets(self.context, cancelled=self.closed.is_set)
        problems = asset_problems(current)
        if problems:
            raise ValueError("\n".join(problems))
        identity = current["program"], digest_context(current)
        if identity != self.definition_identity:
            raise ValueError("Current CAD bytes do not match the loaded definitions; reload and recompute")
        return identity

    def _load(self, identity):
        raw = bytearray()
        with self.path.open("rb") as source:
            while True:
                self._check_cancel()
                chunk = source.read(min(65536, self.limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > self.limit:
                    raise ValueError("Rest-stock snapshot exceeds 16 MB")
        self._check_cancel()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Rest-stock snapshot must be an object")
        if data.get("schema") != 2:
            raise ValueError("Legacy snapshot has no tool/setup identity; recompute from initial stock")
        context = data["context"]
        if digest_context(context) != data.get("context_sha256"):
            raise ValueError("Snapshot context digest differs from its recorded inputs")
        if (data.get("program_sha256"), data["context_sha256"]) != identity:
            raise ValueError("Snapshot does not match current program, stock, tools, workholding or CAD bytes")
        if asset_problems(context):
            raise ValueError("Snapshot contains unresolved CAD bytes")
        if not isinstance(data["stock"], dict):
            raise ValueError("Snapshot stock must be an object")
        stock = StockVolume.from_snapshot(data["stock"], cancelled=self.closed.is_set)
        placement = self.context["stock"]
        origin, size = self._coordinates(placement["origin_mm"]), self._coordinates(placement["size_mm"])
        expected = AABB(Vec3(*origin), Vec3(*(a + b for a, b in zip(origin, size))))
        if (
            stock.grid_bounds != expected
            or stock.rotation_deg != placement["rotation_deg"]
            or stock.pivot != (expected.minimum + expected.maximum).scaled(0.5)
        ):
            raise ValueError("Snapshot stock placement differs from current setup")
        geometry = stock_geometry(stock, cancelled=self.closed.is_set)
        return stock, context, geometry

    @staticmethod
    def _coordinates(value: object) -> tuple[float, float, float]:
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 3
            or any(type(number) not in (int, float) for number in value)
        ):
            raise ValueError("Stock placement requires three numerical coordinates")
        return float(value[0]), float(value[1]), float(value[2])

    def _destination_identity(self):
        """Observe destination bytes without using a timestamp-only proxy."""
        digest = hashlib.sha256()
        try:
            with self.path.open("rb") as source:
                count = 0
                while True:
                    self._check_cancel()
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > self.limit:
                        raise ValueError("Existing destination exceeds 16 MB; choose another file")
                    digest.update(chunk)
        except FileNotFoundError:
            return None
        return digest.hexdigest()

    def _save(self, identity):
        if self.stock is None or not self.baseline or self.identity != identity:
            raise ValueError("Residual result is older or lacks its context; recompute before saving")
        data = {
            "schema": 2,
            "program_sha256": identity[0],
            "context": self.baseline,
            "context_sha256": identity[1],
            "stock": self.stock.snapshot(cancelled=self.closed.is_set),
        }
        descriptor, name = tempfile.mkstemp(prefix=".carvera-residual-", suffix=".pending", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                count = 0
                for chunk in json.JSONEncoder(allow_nan=False).iterencode(data):
                    self._check_cancel()
                    encoded = chunk.encode()
                    count += len(encoded)
                    if count > self.limit:
                        raise ValueError("Rest-stock snapshot exceeds 16 MB")
                    for start in range(0, len(encoded), 65536):
                        self._check_cancel()
                        output.write(encoded[start : start + 65536])
                output.flush()
                os.fsync(output.fileno())
            return temporary
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def _still_current(self):
        return (
            self.panel.artifact_transfer is self
            and not self.closed.is_set()
            and not self.panel.running
            and not self.panel.workspace.repeat_parts_panel.calculating
            and self.definition_identity == self.panel._definition_identity()
            and self.stock is self.panel.rest_stock
            and self.identity == self.panel.rest_identity
            and digest_context(self.baseline) == digest_context(self.panel.rest_context)
        )

    def _approve(self):
        try:
            if self._still_current():
                self.publishing, self.approved = True, True
                self.cancel.disabled = True
                self.status.text = "Publishing prepared snapshot…"
        except (ValueError, TypeError, ArithmeticError):
            self.approved = False
        finally:
            self.decision.set()

    def _run(self):
        temporary, result, error = None, None, None
        try:
            identity = self._verify()
            destination = self._destination_identity() if self.save else None
            result = self._save(identity) if self.save else self._load(identity)
            if self.save:
                temporary = result
            if self._verify() != identity:
                raise ValueError("CAD changed while preparing snapshot; previous results retained")
            self._check_cancel()
            if self.save:
                if self._destination_identity() != destination:
                    raise ValueError("Destination changed while preparing snapshot; choose it again")
                Clock.schedule_once(lambda _dt: self._approve(), 0)
                while not self.decision.wait(0.05):
                    self._check_cancel()
                self._check_cancel()
                if not self.approved:
                    raise ValueError("Setup or residual changed while preparing snapshot; destination retained")
                # Cancellation is disabled after the UI's checked commit decision.
                # Atomic replacement is worker-owned; success means bytes published.
                assert temporary is not None
                os.replace(temporary, self.path)
                temporary = None
                result = str(self.path)
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError, zlib.error) as exc:
            error = str(exc)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    error = "Prepared snapshot cleanup failed: " + str(exc)
        Clock.schedule_once(lambda _dt: self._finish(result, error), 0)

    def _finish(self, result, error):
        if self.closed.is_set():
            return
        if not error and not self.save:
            try:
                current = self._still_current()
            except (ValueError, TypeError, ArithmeticError):
                current = False
            if not current:
                error = "Setup or residual changed while loading snapshot; previous result retained"
        self.active = False
        self.cancel.disabled = False
        self.cancel.text = "Close"
        self.panel.refresh_controls()
        if error:
            self.status.text = "Snapshot not applied: " + error
            self.panel.artifact_status.text = self.status.text
            self.panel.note.text = self.status.text
            return
        if self.save:
            self.panel.artifact_status.text = "Saved rest stock · " + result
        else:
            stock, context, geometry = result
            self.panel.workspace.machine.gcode_viewer.set_rest_stock_geometry(geometry)
            self.panel.rest_stock, self.panel.rest_identity = stock, self.definition_identity
            self.panel.rest_context = context
            if self.panel.clearance_inputs is not None:
                self.panel._invalidate_clearance()
            self.panel.stock_source.text = "Continue rest stock"
            self.panel.note.text = (
                f"Loaded rest stock · {stock.remaining_volume_mm3:,.1f} mm³ · physical setup unverified"
            )
        self.dismiss()
