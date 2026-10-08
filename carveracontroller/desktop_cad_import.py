"""Explicit CAD registration and offline conversion for local preview assets."""

import threading
import uuid
from pathlib import Path

from kivy.clock import Clock
from kivy.config import Config
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Choice, Field, label


def open_cad_import(source, callback, holder=False):
    source = Path(source).expanduser()
    body = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    body.add_widget(label(source.name, 16, height=28))
    note = label(
        "Register the CAD axis and tip (or holder collet face) explicitly.\nSTEP units are resolved to mm; STL/OBJ units must be selected.",
        12,
        MUTED,
        56,
    )
    body.add_widget(note)
    grid = AdaptiveGrid(max_cols=2, min_width=160, row_height=60, spacing=dp(8))
    controls = {}
    for key, title, choices, value in (
        ("units", "Source units", ("mm", "in"), "mm"),
        ("axis", "From tip toward shank", ("+Z", "-Z", "+X", "-X", "+Y", "-Y"), "+Z"),
        ("x", "Tip / collet origin X", None, "0"),
        ("y", "Tip / collet origin Y", None, "0"),
        ("z", "Tip / collet origin Z", None, "0"),
    ):
        row = BoxLayout(orientation="vertical")
        row.add_widget(label(title, 11, MUTED, 24))
        control = Choice(text=value, values=choices) if choices else Field(text=value)
        controls[key] = control
        row.add_widget(control)
        grid.add_widget(row)
    body.add_widget(grid)
    body.add_widget(label("CAD conversion Python (with cadquery-ocp for STEP)", 11, MUTED, 24))
    python = Field(
        text=Config.get("carvera", "tool_cad_python", fallback=""), hint_text="Path to CAD Python interpreter"
    )
    body.add_widget(python)
    popup = Popup(
        title="Import holder CAD" if holder else "Import cutter CAD",
        content=body,
        size_hint=(0.8, None),
        height=dp(490),
    )
    actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
    import_button = Action("Convert & inspect", None, primary=True)
    cancelled = threading.Event()
    state = {"running": False, "closed": False}

    def cancel_conversion():
        if state["running"]:
            cancelled.set()
            cancel.disabled = True
            note.text = "Cancelling local CAD conversion…"
        else:
            popup.dismiss()

    cancel = Action("Cancel", cancel_conversion)
    actions.add_widget(import_button)
    actions.add_widget(cancel)
    body.add_widget(actions)

    def convert():
        try:
            import math

            tip = [float(controls[key].text) for key in ("x", "y", "z")]
            if not all(math.isfinite(v) for v in tip):
                raise ValueError("Enter finite origin coordinates")
            executable = Path(python.text).expanduser()
            if not executable.is_file():
                raise ValueError("Select an existing CAD Python interpreter")
            from carveracontroller.addons.tool_visualization import converter
            from carveracontroller.addons.tool_visualization.conversion_process import converter_script

            script = converter_script(converter.__file__)
            output = Path.home() / ".carvera/tool-assets" / (str(uuid.uuid4()) + ".json.gz")
            command = [
                str(executable),
                str(script),
                str(source),
                "--output",
                str(output),
                "--units",
                controls["units"].text,
                "--axis=" + controls["axis"].text,
                "--tip",
                *(str(v) for v in tip),
                "--origin",
                "collet" if holder else "tip",
            ]
        except (ValueError, OSError) as exc:
            note.text = str(exc)
            return
        if state["running"] or state["closed"]:
            return
        state["running"] = True
        cancelled.clear()
        import_button.disabled = True
        for control in (*controls.values(), python):
            control.disabled = True
        note.text = "Converting local CAD…"

        def finish(error, was_cancelled=False):
            state["running"] = False
            if state["closed"]:
                return
            import_button.disabled = cancel.disabled = False
            for control in (*controls.values(), python):
                control.disabled = False
            if was_cancelled or cancelled.is_set():
                note.text = "CAD conversion cancelled; no tool asset applied."
                return
            if error:
                note.text = error
            else:
                callback(str(output))
                popup.dismiss()

        try:
            Config.set("carvera", "tool_cad_python", str(executable))
            Config.write()
        except OSError:
            finish("CAD Python preference could not be saved; no conversion started.")
            return

        def work():
            try:
                from carveracontroller.addons.tool_visualization.conversion_process import convert_process

                convert_process(command, output, cancelled.is_set)
                error = None
                was_cancelled = False
            except InterruptedError:
                error, was_cancelled = None, True
            except (ValueError, TimeoutError) as exc:
                error = str(exc)
                was_cancelled = False
            except OSError:
                error, was_cancelled = "CAD conversion could not run; check the selected CAD Python interpreter.", False
            Clock.schedule_once(lambda _dt, error=error, was_cancelled=was_cancelled: finish(error, was_cancelled), 0)

        try:
            threading.Thread(target=work, daemon=True, name="tool-cad-conversion").start()
        except (RuntimeError, OSError):
            finish("CAD conversion worker could not start; no tool asset applied.")

    def dismissed(*_args):
        state["closed"] = True
        cancelled.set()

    import_button.bind(on_release=lambda *_: convert())
    popup.bind(on_dismiss=dismissed)
    popup.open()
    return popup
