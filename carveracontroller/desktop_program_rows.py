"""Recycled program rows; activation resolves the current listing identity."""

from kivy.properties import ObjectProperty

from carveracontroller.desktop_file_picker import ArtifactList, ArtifactRow


class ProgramList(ArtifactList):
    pass


class ProgramRow(ArtifactRow):
    listing_token = ObjectProperty(None, allownone=True)

    def activate(self):
        if self.browser is not None and self.entry is not None:
            self.browser.activate_row(self.entry, self.listing_token)
