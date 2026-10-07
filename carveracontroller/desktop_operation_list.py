"""Bounded operation rows; selection inspects the current local analysis only."""

from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior

from carveracontroller.desktop_components import ACCENT, BG, RAISED, TEXT, Action


class OperationRow(RecycleDataViewBehavior, Action):
    owner = ObjectProperty(None)
    operation = ObjectProperty(None)
    program = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__("", self.inspect, halign="left", valign="middle", padding=(dp(10), dp(6)), **kwargs)
        self.bind(size=lambda obj, size: setattr(obj, "text_size", (max(dp(40), size[0] - dp(20)), size[1])))

    def refresh_view_attrs(self, rv, index, data):
        if self.operation is not data["operation"] or self.program is not data["program"]:
            self.focus = False
        result = super().refresh_view_attrs(rv, index, data)
        selected = self.owner.selected_operation is self.operation
        self.base_color = ACCENT if selected else RAISED
        self.color = BG if selected else TEXT
        self._paint()
        return result

    def inspect(self):
        # A recycled or detached row must never route into an older analysis.
        if self.owner is not None and self.owner.program is self.program and self.operation is not None:
            self.owner.select(self.operation)


class OperationList(RecycleView):
    ROW_HEIGHT = 80
    GAP = 5

    def __init__(self, owner, **kwargs):
        self.owner = owner
        self.indices = {}
        super().__init__(size_hint_y=None, height=0, do_scroll_x=False, bar_width=dp(9), **kwargs)
        layout = RecycleBoxLayout(
            default_size=(None, dp(self.ROW_HEIGHT)),
            default_size_hint=(1, None),
            size_hint_y=None,
            orientation="vertical",
            spacing=dp(self.GAP),
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)
        self.viewclass = OperationRow

    @property
    def rows(self):
        return [(row.operation, row) for _, row in sorted(self.view_adapter.views.items())]

    def load(self, program):
        for _operation, row in self.rows:
            row.focus = False
        self.indices = {}
        rows = []
        for index, operation in enumerate(program.operations if program is not None else (), 1):
            tools = ", ".join(f"T{number}" for number in operation.tool_ids) or "No tool selected"
            duration = (
                f"{operation.estimated_seconds / 60:.1f} min nominal"
                if operation.estimated_seconds is not None
                else "Time unknown"
            )
            warning = f" · {len(operation.warnings)} warnings" if operation.warnings else ""
            rows.append(
                {
                    "owner": self.owner,
                    "program": program,
                    "operation": operation,
                    "text": f"{index:02d}  {operation.name}\n{tools} · {duration}\n"
                    f"Lines {operation.start_line}–{operation.end_line}{warning}",
                }
            )
            self.indices[operation.id] = index - 1
        self.height = min(dp(240), len(rows) * dp(self.ROW_HEIGHT + self.GAP))
        self.scroll_y = 1
        self.data = rows

    def scroll_to(self, widget, padding=10, animate=True):
        # Kivy ScrollView assumes Layout._trigger_layout is a ClockEvent;
        # RecycleLayout uses a method. Reveal by data identity instead.
        if getattr(widget, "program", None) is self.owner.program:
            operation = getattr(widget, "operation", None)
            if operation is not None:
                self._reveal_operation(operation)

    def _reveal_operation(self, operation):
        index = self.indices.get(operation.id)
        if index is None:
            return
        stride = dp(self.ROW_HEIGHT + self.GAP)
        overflow = max(0, len(self.data) * stride - dp(self.GAP) - self.height)
        if overflow:
            self.scroll_y = 1 - min(1, max(0, (index * stride + stride / 2 - self.height / 2) / overflow))

    def select(self, operation):
        self._reveal_operation(operation)
        self.refresh_from_data()
