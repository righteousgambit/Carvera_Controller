"""Task-focused workbench navigation with retained drafts and reading position."""

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    RAISED,
    TEXT,
    Action,
    Choice,
    DesktopScrollView,
    release_screen_focus,
)


class TaskDeck(BoxLayout):
    """Only the selected task participates in layout and focus dispatch."""

    def __init__(self, tasks, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.descriptions = dict(tasks)
        if not self.descriptions:
            raise ValueError("At least one workbench task required")
        self.names = tuple(self.descriptions)
        self.active = None
        self.sections, self.buttons, self.positions = {}, {}, {}
        self.generation = 0
        self.closed = False
        self.restore_event = None
        self.navigation = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self.tabs = BoxLayout(spacing=dp(4))
        self.choice = Choice(text=self.names[0], values=self.names, height=dp(34))
        self.choice.bind(text=self._chosen)
        self.navigation.bind(width=self._reflow)
        self.add_widget(self.navigation)
        self.summary = flowing_text("", 28)
        self.add_widget(self.summary)
        self.host = BoxLayout(orientation="vertical", size_hint_y=None)
        self.host.bind(minimum_height=self.host.setter("height"))
        self.scroll = DesktopScrollView(do_scroll_x=False, bar_width=dp(9))
        self.scroll.add_widget(self.host)
        self.add_widget(self.scroll)
        for name in self.names:
            section = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
            section.bind(minimum_height=section.setter("height"))
            self.sections[name] = section
            button = Action(name, lambda name=name: self.show(name), height=dp(34))
            button.bind(font_size=self._reflow, font_name=self._reflow)
            self.buttons[name] = button
            self.tabs.add_widget(button)
        self._reflow()
        self.show(self.names[0])

    def _reflow(self, *_):
        widths = []
        for button in self.buttons.values():
            caption = CoreLabel(text=button.text, font_name=button.font_name, font_size=button.font_size)
            caption.refresh()
            widths.append(max(dp(64), caption.texture.size[0] + dp(24)))
        required = max(widths, default=0) * len(widths) + dp(4) * max(0, len(widths) - 1)
        target = self.choice if self.navigation.width < required else self.tabs
        if target.parent is self.navigation:
            return
        self.choice.is_open = False
        for child in tuple(self.navigation.children):
            release_screen_focus(child)
            self.navigation.remove_widget(child)
        self.navigation.add_widget(target)

    def _chosen(self, _choice, name):
        if name != self.active:
            self.show(name)

    def show(self, name):
        if name not in self.sections:
            raise ValueError("Unknown workbench task")
        if self.closed or name == self.active:
            return False
        restoring = self.restore_event is not None
        if restoring:
            self.restore_event.cancel()
        if self.active is not None:
            if not restoring:
                self.positions[self.active] = self.scroll.scroll_y
            release_screen_focus(self.sections[self.active])
        self.generation += 1
        generation = self.generation
        self.host.clear_widgets()
        self.host.add_widget(self.sections[name])
        self.active = name
        Animation.cancel_all(self.scroll, "scroll_x", "scroll_y")
        if self.scroll.effect_y is not None:
            self.scroll.effect_y.velocity = 0
        self.scroll.scroll_y = self.positions.get(name, 1)
        self.summary.text = self.descriptions[name]
        self.choice.text = name
        for title, button in self.buttons.items():
            selected = title == name
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()

        def restore(_dt):
            if not self.closed and generation == self.generation:
                self.scroll.scroll_y = self.positions.get(name, 1)
                self.restore_event = None

        # Restore after child geometry and the viewport have settled.
        self.restore_event = Clock.schedule_once(lambda _dt: self._queue_restore(restore, generation), 0)
        return True

    def _queue_restore(self, restore, generation):
        if not self.closed and generation == self.generation:
            self.restore_event = Clock.schedule_once(restore, 0)

    def dispose(self):
        self.closed = True
        self.generation += 1
        if self.restore_event is not None:
            self.restore_event.cancel()
        self.choice.is_open = False
        release_screen_focus(self)
