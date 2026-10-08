"""Compact cutter browsing controls with explicit units and atomic application."""

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, DesktopScrollView, Field, label
from carveracontroller.machine.library_browser import CutterFilter
from carveracontroller.machine.quantities import QuantityError


class CutterFilterDialog(Popup):
    def __init__(self, library, **kwargs):
        self.library = library
        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        super().__init__(title="Find cutters", content=body, size_hint=(None, None), **kwargs)
        self._fit_window()
        self.bind(on_pre_open=lambda *_: Window.bind(size=self._fit_window))
        self.bind(on_dismiss=lambda *_: Window.unbind(size=self._fit_window))
        scroll = DesktopScrollView(do_scroll_x=False)
        self.form_scroll = scroll
        form = BoxLayout(orientation="vertical", spacing=dp(10), padding=(0, 0, dp(12), 0), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        scroll.add_widget(form)
        body.add_widget(scroll)
        form.add_widget(
            label("Blank dimensions match any size. Use mm, inches or expressions such as 1/4 in.", 12, height=48)
        )
        grid = AdaptiveGrid(max_cols=2, min_width=225, row_height=72, spacing=dp(8))
        self.filter_grid = grid
        form.add_widget(grid)
        saved = library.filter_values
        self.fields = {}
        self.shapes = {"Any shape": "", **{item.value.replace("_", " ").title(): item.value for item in ToolType}}
        definitions = (
            ("shape", "Cutter shape", Choice(text=saved.get("shape", "Any shape"), values=tuple(self.shapes))),
            ("vendor", "Vendor contains", Field(text=saved.get("vendor", ""), hint_text="Any vendor", multiline=False)),
            (
                "minimum",
                "Minimum cutting diameter · mm",
                Field(text=saved.get("minimum", ""), hint_text="e.g. 1/8 in", multiline=False),
            ),
            (
                "maximum",
                "Maximum cutting diameter · mm",
                Field(text=saved.get("maximum", ""), hint_text="e.g. 1/4 in", multiline=False),
            ),
            (
                "shank",
                "Exact nominal shank diameter · mm",
                Field(text=saved.get("shank", ""), hint_text="e.g. 1/4 in", multiline=False),
            ),
            (
                "assets",
                "Attached assets",
                Choice(
                    text=saved.get("assets", "All assets"),
                    values=("All assets", "CAD reference", "Drawing reference", "Dimensions only"),
                ),
            ),
        )
        for key, title, control in definitions:
            row = BoxLayout(orientation="vertical", spacing=dp(4))
            row.add_widget(label(title, 12, height=24))
            row.add_widget(control)
            grid.add_widget(row)
            self.fields[key] = control
        form.add_widget(
            label(
                "CAD and drawing filters mean a saved reference is attached. They do not verify that the file exists, its identity or physical tool measurements.",
                12,
                height=72,
            )
        )
        self.message = label(
            "Filters affect the saved library list. Your editor draft and active machine stay unchanged.", 12, height=64
        )
        body.add_widget(self.message)
        actions = AdaptiveGrid(max_cols=3, min_width=100, row_height=36, spacing=dp(8))
        self.clear_action = Action("Clear filters", self.clear)
        self.apply_action = Action("Apply filters", self.apply, primary=True)
        actions.add_widget(self.clear_action)
        actions.add_widget(Action("Cancel", self.dismiss))
        actions.add_widget(self.apply_action)
        body.add_widget(actions)

    def _fit_window(self, *_):
        self.size = (min(dp(760), Window.width * 0.88), min(dp(600), Window.height * 0.86))

    def apply(self):
        raw = {key: field.text for key, field in self.fields.items()}
        values = dict(raw, shape=self.shapes[raw["shape"]])
        try:
            selected = CutterFilter.from_text(**values)
        except QuantityError as exc:
            self.message.text = str(exc) + ". Previous filters are unchanged."
            return
        self.library.cutter_filter = selected
        self.library.filter_values = raw
        self.library._refresh_list()
        self.dismiss()

    def clear(self):
        self.library.cutter_filter = CutterFilter()
        self.library.filter_values = {}
        self.library._refresh_list()
        self.dismiss()
