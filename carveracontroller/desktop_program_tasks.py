"""Concentrated Program tasks with retained local workflow state."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import ACCENT, BG, RAISED, TEXT, Action, AdaptiveGrid


class ProgramTasks(BoxLayout):
    names = ("Operations", "Simulation", "View & playback", "Job package")

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.sections = {}
        self.buttons = {}
        self.active = None
        self.generation = 0
        self.tabs = AdaptiveGrid(max_cols=4, min_width=130, row_height=32, spacing=dp(5))
        self.add_widget(self.tabs)
        self.host = BoxLayout(orientation="vertical", size_hint_y=None)
        self.host.bind(minimum_height=self.host.setter("height"))
        self.add_widget(self.host)
        for name in self.names:
            section = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
            section.bind(minimum_height=section.setter("height"))
            self.sections[name] = section
            button = Action(name, lambda name=name: self.show(name), height=dp(32))
            self.buttons[name] = button
            self.tabs.add_widget(button)
        self.show(self.names[0])

    def show(self, name):
        if name not in self.sections:
            raise ValueError("Unknown Program task")
        if name == self.active:
            return False
        if self.active is not None:
            for control in self.sections[self.active].walk():
                if hasattr(control, "focus"):
                    control.focus = False
        self.host.clear_widgets()
        self.host.add_widget(self.sections[name])
        self.active = name
        self.generation += 1
        for title, button in self.buttons.items():
            selected = title == name
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()
        return True

    def show_for(self, widget):
        """Route a retained child to its task before attempting scroll/reveal."""
        current = widget
        while current is not None:
            for name, section in self.sections.items():
                if current is section:
                    self.show(name)
                    return True
            current = current.parent
        return False
