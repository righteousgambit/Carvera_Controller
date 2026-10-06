"""Concentrated Program tasks with retained local workflow state."""

from kivy.animation import Animation
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    release_screen_focus,
)


class ProgramTasks(BoxLayout):
    names = ("Operations", "Simulation", "View & playback", "Run record", "Job package")

    def __init__(self, on_choice=None, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.sections = {}
        self.buttons = {}
        self.active = None
        self.before_change = self.after_change = None
        self.generation = 0
        self.on_choice = on_choice
        self.tabs = AdaptiveGrid(max_cols=5, min_width=110, row_height=32, spacing=dp(5))
        self.add_widget(self.tabs)
        self.host = BoxLayout(orientation="vertical", size_hint_y=None)
        self.host.bind(minimum_height=self.host.setter("height"))
        self.scroll = DesktopScrollView(do_scroll_x=False, bar_width=dp(9))
        self.scroll.add_widget(self.host)
        self.add_widget(self.scroll)
        for name in self.names:
            section = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
            section.bind(minimum_height=section.setter("height"))
            self.sections[name] = section
            button = Action(name, lambda name=name: self.choose(name), height=dp(32))
            self.buttons[name] = button
            button.bind(font_size=self._size_tab_captions, font_name=self._size_tab_captions)
            self.tabs.add_widget(button)
        self._size_tab_captions()
        self.show(self.names[0])

    def _size_tab_captions(self, *_):
        widths = []
        for button in self.buttons.values():
            caption = CoreLabel(text=button.text, font_name=button.font_name, font_size=button.font_size)
            caption.refresh()
            widths.append(caption.texture.size[0] + dp(24))
        self.tabs.min_width = max(dp(110), *widths)
        self.tabs._reflow()

    def choose(self, name):
        """Keep the selector reachable after a deliberate task change."""
        self.show(name)
        if self.on_choice is not None:
            self.on_choice()

    def show(self, name):
        if name not in self.sections:
            raise ValueError("Unknown Program task")
        if name == self.active:
            return False
        if self.before_change is not None:
            self.before_change()
        if self.active is not None:
            release_screen_focus(self.sections[self.active])
        self.host.clear_widgets()
        self.host.add_widget(self.sections[name])
        Animation.cancel_all(self.scroll, "scroll_x", "scroll_y")
        self.scroll.scroll_y = 1
        if self.scroll.effect_y is not None:
            self.scroll.effect_y.velocity = 0
        self.active = name
        self.generation += 1
        for title, button in self.buttons.items():
            selected = title == name
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()
        if self.after_change is not None:
            self.after_change()
        return True

    def show_for(self, widget):
        """Route a retained child to its task before attempting scroll/reveal."""
        current = widget
        visited = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            if current is self.tabs:
                return True
            for name, section in self.sections.items():
                if current is section:
                    self.show(name)
                    return True
            current = current.parent
        return False
