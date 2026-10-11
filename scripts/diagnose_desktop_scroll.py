#!/usr/bin/env python3
"""Observe native wheel delivery without importing the controller or hardware.

Run with the controller's Python environment and --output <evidence directory>.
Configuration is isolated; the bounded trace contains event types and positions,
never key presses, user text, programs or machine commands.
"""

import argparse
import collections
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Evidence directory; otherwise create a fresh temporary directory")
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(tempfile.mkdtemp(prefix="carvera-scroll-evidence-"))
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["KIVY_HOME"] = tempfile.mkdtemp(prefix="carvera-scroll-diagnostic-")
    os.environ["KIVY_NO_FILELOG"] = "1"
    os.environ["KIVY_NO_ARGS"] = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from kivy.config import Config

    Config.set("graphics", "width", "1200")
    Config.set("graphics", "height", "780")
    Config.set("input", "mouse", "mouse,multitouch_on_demand")

    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.textinput import TextInput

    from carveracontroller.desktop_components import BG, MUTED, Action, DesktopScrollView, Surface, label

    events = collections.deque(maxlen=2000)
    counts = collections.Counter()

    def record(stage, **fields):
        counts[stage] += 1
        events.append({"at": time.monotonic(), "stage": stage, **fields})

    class ObservedScroll(DesktopScrollView):
        def on_scroll_start(self, touch, check_children=True):
            before = self.scroll_y
            result = super().on_scroll_start(touch, check_children)
            record(
                "viewport",
                button=getattr(touch, "button", ""),
                x=touch.x,
                y=touch.y,
                before=before,
                after=self.scroll_y,
                handled=bool(result),
            )
            return result

    class SourceText(TextInput):
        def on_touch_down(self, touch):
            if getattr(touch, "button", "") in ("scrollup", "scrolldown"):
                return False
            return super().on_touch_down(touch)

    class ScrollDiagnostic(App):
        title = "Carvera Scroll Diagnostics"

        def build(self):
            Window.clearcolor = BG
            Window.bind(on_mouse_down=self.mouse_down, on_mouse_up=self.mouse_up, on_motion=self.motion)
            root = Surface(orientation="vertical", padding=dp(20), spacing=dp(12))
            root.add_widget(label("Native scroll diagnostics", size=20, height=42))
            root.add_widget(label("Scroll over the text. Drag the bar as a control. No machine connection.", height=30))
            root.add_widget(label(str(args.output), size=11, color=MUTED, height=24, shorten=True))
            self.status = label("Waiting for input", color=MUTED, height=36)
            root.add_widget(self.status)
            self.view = ObservedScroll(do_scroll_x=False)
            content = BoxLayout(orientation="vertical", size_hint_y=None)
            content.bind(minimum_height=content.setter("height"))
            source = SourceText(
                readonly=True,
                size_hint_y=None,
                font_size=dp(16),
                background_color=BG,
                foreground_color=MUTED,
                text="\n".join(f"Inspection row {i:02d}: sample source text" for i in range(1, 61)),
            )
            source.bind(minimum_height=lambda widget, value: setattr(widget, "height", value))
            content.add_widget(source)
            self.view.add_widget(content)
            root.add_widget(self.view)
            controls = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(12))
            controls.add_widget(Action("Mark attempt", lambda: record("mark", scroll_y=self.view.scroll_y)))
            controls.add_widget(Action("Reset to middle", self.reset))
            controls.add_widget(Action("Test program picker", self.open_picker))
            controls.add_widget(Action("Close diagnostics", self.stop))
            root.add_widget(controls)
            self.flush_event = Clock.schedule_interval(self.flush, 0.25)
            return root

        def open_picker(self):
            from carveracontroller import desktop_components
            from carveracontroller.addons.machine_simulation.model import MachineSetup
            from carveracontroller.desktop_program_picker import ProgramBrowser

            if getattr(self, "browser", None) is not None:
                self.browser.open()
                return
            samples = args.output / "synthetic-programs"
            samples.mkdir(exist_ok=True)
            program = samples / "scroll-inspection.nc"
            program.write_text(
                "G21 G90 G17 G94 G54\nT99 M6\nG0 Z10\n" + "\n".join(f"G1 X{i} Y{i % 7} F100" for i in range(100))
            )
            machine = SimpleNamespace(
                controller=None,
                file_popup=SimpleNamespace(
                    local_rv=SimpleNamespace(curr_dir=str(samples)), remote_rv=SimpleNamespace(curr_dir="/sd/gcodes")
                ),
                gcode_viewer=SimpleNamespace(library_tool_table_mm={}, machine_setup=MachineSetup()),
            )
            workspace = SimpleNamespace(
                machine=machine,
                connected=False,
                app=SimpleNamespace(state="Idle"),
                selected_machine_profile=None,
                loaded_toolset=None,
            )

            class InspectionBrowser(ProgramBrowser):
                def _sync_actions(self):
                    super()._sync_actions()
                    self.preview_button.disabled = True
                    self.upload_button.disabled = True

                def preview(self):
                    record("blocked_action", action="preview")

                def upload(self):
                    record("blocked_action", action="upload")

                def review_dependencies(self):
                    record("blocked_action", action="review_dependencies")

            self.browser = InspectionBrowser(workspace)
            original = desktop_components.DesktopScrollView
            try:
                desktop_components.DesktopScrollView = ObservedScroll
                self.browser._build()
            finally:
                desktop_components.DesktopScrollView = original
            # Synthetic inspection only. No transfer/preview/machine callbacks exist.
            self.browser.open()
            record("picker_open")
            attempts = 0

            def select_when_ready(_dt):
                nonlocal attempts
                if not self.browser.popup._is_open:
                    return
                attempts += 1
                if self.browser.entries:
                    self.browser.select(self.browser.entries[0])
                    record("picker_selected")
                elif attempts < 100:
                    Clock.schedule_once(select_when_ready, 0.05)
                else:
                    record("picker_list_timeout")

            Clock.schedule_once(select_when_ready, 0)

        def reset(self):
            self.view.scroll_y = 0.5
            self.view._update_effect_y_bounds()
            record("reset", scroll_y=self.view.scroll_y)

        def mouse_down(self, _window, x, y, button, _modifiers):
            record("window_down", x=x, y=y, button=button)
            return False

        def mouse_up(self, _window, x, y, button, _modifiers):
            record("window_up", x=x, y=y, button=button)
            return False

        def motion(self, _window, kind, event):
            record(
                "motion", kind=kind, button=getattr(event, "button", ""), sx=event.sx, sy=event.sy, device=event.device
            )
            return False

        def flush(self, *_):
            self.status.text = f"Window: {counts['window_down']} · Motion: {counts['motion']} · Viewport: {counts['viewport']} · Position: {self.view.scroll_y:.3f}"
            data = {
                "counts": dict(counts),
                "scroll_y": self.view.scroll_y,
                "window_size": list(Window.size),
                "system_size": list(Window.system_size),
                "density": Window._density,
                "events": list(events),
            }
            browser = getattr(self, "browser", None)
            if browser is not None:
                data["picker"] = {
                    "scroll_y": browser.detail_scroll.scroll_y,
                    "viewport_pos": list(browser.detail_scroll.pos),
                    "viewport_size": list(browser.detail_scroll.size),
                    "open": browser.popup._is_open,
                }
            temporary = args.output / "scroll-trace.tmp"
            temporary.write_text(json.dumps(data, indent=2) + "\n")
            temporary.replace(args.output / "scroll-trace.json")

        def on_stop(self):
            browser = getattr(self, "browser", None)
            if browser is not None:
                browser.dismiss()
            self.flush_event.cancel()
            self.flush()
            Window.unbind(on_mouse_down=self.mouse_down, on_mouse_up=self.mouse_up, on_motion=self.motion)

    ScrollDiagnostic().run()


if __name__ == "__main__":
    main()
