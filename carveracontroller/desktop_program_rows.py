"""Recycled program rows; activation resolves the current listing identity."""

from kivy.properties import ObjectProperty

from carveracontroller.desktop_file_picker import ArtifactList, ArtifactRow


class ProgramList(ArtifactList):
    pass


class ProgramRow(ArtifactRow):
    listing_token = ObjectProperty(None, allownone=True)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        # A focused recycled widget may now represent a different entry. List
        # navigation and Enter must resolve the browser cursor, never that row.
        if keycode[0] in (13, 271, 273, 274, 278, 279, 280, 281):
            if self.browser is not None:
                self.browser.keydown(window, keycode[0], None, text, modifiers)
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)

    def activate(self):
        if self.browser is not None and self.entry is not None:
            self.browser.activate_row(self.entry, self.listing_token)
