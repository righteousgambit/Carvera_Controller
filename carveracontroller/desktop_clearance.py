"""Compact, selectable clearance trace without modifying stencil ownership."""

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Canvas, Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stencilview import StencilView

from carveracontroller.desktop_components import (
    ACCENT,
    AMBER,
    BORDER,
    DANGER,
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    Surface,
    label,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.clearance_groups import group_clearance_candidates

COLORS = {"cutter": AMBER, "shank": (0.40, 0.65, 0.98, 1), "holder": ACCENT}


class ClearanceCandidates(Surface):
    """Search all captured contacts while bounding the number of rendered rows."""

    page_size = 12

    def __init__(self, inspect, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.inspect_candidate = inspect
        self.candidates = ()
        self.matches = ()
        self.page = 0
        self.causes = ()
        self.filtered_causes = ()
        self.capture_labels = {}
        self.expanded_cause = None
        self.contact_page = 0
        self.query = Field(hint_text="Find line, tool, operation or obstacle")
        self.component = Choice(text="All components", values=("All components",))
        self.view = Choice(text="By physical cause", values=("By physical cause", "Individual contacts"))
        self.status = content_label("No calculated clearance candidates.")
        filters = AdaptiveGrid(max_cols=3, min_width=150, row_height=36)
        filters.add_widget(self.query)
        filters.add_widget(self.component)
        filters.add_widget(self.view)
        self.add_widget(filters)
        self.add_widget(self.status)
        self.rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.add_widget(self.rows)
        self.pages = AdaptiveGrid(max_cols=2, min_width=100, row_height=32)
        self.previous = Action("Previous results", lambda: self.turn_page(-1), disabled=True)
        self.next = Action("Next results", lambda: self.turn_page(1), disabled=True)
        self.pages.add_widget(self.previous)
        self.pages.add_widget(self.next)
        self._filter_trigger = Clock.create_trigger(lambda _dt: self.filter(), 0.15)
        self.query.bind(text=lambda *_: self._filter_trigger())
        self.component.bind(text=lambda *_: self._filter_trigger())
        self.view.bind(text=lambda *_: self._filter_trigger())

    def set_candidates(self, candidates, *, contacts=(), segments=(), operations=()):
        self._filter_trigger.cancel()
        self.candidates = tuple(dict.fromkeys(candidates))
        self.causes = group_clearance_candidates(
            self.candidates, contacts=contacts, segments=segments, operations=operations
        )
        families = {}
        for cause in self.causes:
            families.setdefault(cause.key[:4], []).append(cause)
        self.capture_labels = {
            cause.key: f"Captured shape {index + 1}/{len(family)}"
            for family in families.values()
            if len(family) > 1
            for index, cause in enumerate(family)
        }
        self._search_text = {}
        for cause in self.causes:
            for candidate in cause.candidates:
                self._search_text.setdefault(candidate, []).append(
                    f"{cause.operation} {' '.join('T' + tool for tool in cause.tools)}"
                )
        self.component.values = ("All components", *sorted({candidate[1] for candidate in self.candidates}))
        self.component.text = "All components"
        self.query.text = ""
        self.filter()

    def filter(self):
        self._filter_trigger.cancel()
        terms = self.query.text.casefold().split()
        self.matches = tuple(
            candidate
            for candidate in self.candidates
            if (self.component.text == "All components" or candidate[1] == self.component.text)
            and all(
                term
                in (
                    f"line {candidate[0]} {candidate[1]} {candidate[2]} "
                    + " ".join(self._search_text.get(candidate, ()))
                ).casefold()
                for term in terms
            )
        )
        matching = set(self.matches)
        self.filtered_causes = tuple(
            (cause, tuple(candidate for candidate in cause.candidates if candidate in matching))
            for cause in self.causes
            if any(candidate in matching for candidate in cause.candidates)
        )
        self.expanded_cause = None
        self.contact_page = 0
        self.page = 0
        self.render()

    def turn_page(self, delta):
        results = self.filtered_causes if self.view.text == "By physical cause" else self.matches
        maximum = max(0, (len(results) - 1) // self.page_size)
        self.page = max(0, min(maximum, self.page + delta))
        self.expanded_cause = None
        self.contact_page = 0
        self.render()

    def toggle_cause(self, key):
        self.expanded_cause = None if self.expanded_cause == key else key
        self.contact_page = 0
        self.render()

    def turn_contact_page(self, delta, count):
        self.contact_page = max(0, min((count - 1) // self.page_size, self.contact_page + delta))
        self.render()

    @staticmethod
    def readable_action(text, callback):
        action = Action(text, callback, height=dp(44), halign="left", valign="middle")
        action.bind(width=lambda obj, width: setattr(obj, "text_size", (max(1, width - dp(20)), None)))
        action.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(44), size[1] + dp(16))))
        return action

    def contact_action(self, candidate):
        line, component, obstacle = candidate
        return self.readable_action(
            f"Line {line} · {component} near {obstacle}",
            lambda: self.inspect_candidate(*candidate),
        )

    def render(self):
        self.rows.clear_widgets()
        start = self.page * self.page_size
        grouped = self.view.text == "By physical cause"
        results = self.filtered_causes if grouped else self.matches
        visible = results[start : start + self.page_size]
        self.status.text = (
            (
                f"Causes {start + 1}–{start + len(visible)} of {len(results)} · "
                f"{len(self.matches)} matching contacts / {len(self.candidates)} total\n"
                "Conservative captures · physical contact unverified."
                if grouped
                else f"Candidates {start + 1}–{start + len(visible)} of {len(self.matches)} matching · {len(self.candidates)} total"
            )
            if visible
            else "No matching candidates. Clear the search or change the component."
            if self.candidates
            else "No calculated clearance candidates. Missing geometry can still leave clearance unknown."
        )
        self.previous.disabled = self.page == 0
        self.next.disabled = start + self.page_size >= len(results)
        if len(results) > self.page_size and self.pages.parent is None:
            self.add_widget(self.pages)
        elif len(results) <= self.page_size and self.pages.parent is self:
            self.remove_widget(self.pages)
        if not grouped:
            for candidate in visible:
                self.rows.add_widget(self.contact_action(candidate))
            return
        for cause, candidates in visible:
            expanded = self.expanded_cause == cause.key
            tools = ", ".join("T" + tool for tool in cause.tools) or "Tool unresolved"
            low, high = min(c[0] for c in candidates), max(c[0] for c in candidates)
            lines = f"line {low}" if low == high else f"lines {low}–{high}"
            motions = "1 motion" if len(candidates) == 1 else f"{len(candidates)} motions"
            capture_label = self.capture_labels.get(cause.key, "")
            self.rows.add_widget(
                self.readable_action(
                    f"{'−' if expanded else '+'}  {cause.component} near {cause.obstacle} · {motions}\n"
                    f"{cause.operation} · {tools} · {lines}" + (f"\n{capture_label}" if capture_label else ""),
                    lambda key=cause.key: self.toggle_cause(key),
                )
            )
            if expanded:
                first = self.contact_page * self.page_size
                contacts = candidates[first : first + self.page_size]
                self.rows.add_widget(
                    content_label(
                        self.capture_description(cause)
                        + f"\nMotions {first + 1}–{first + len(contacts)} of {len(candidates)}"
                    )
                )
                for candidate in contacts:
                    self.rows.add_widget(self.contact_action(candidate))
                if len(candidates) <= self.page_size:
                    continue
                navigation = AdaptiveGrid(max_cols=2, min_width=100, row_height=32)
                count = len(candidates)
                navigation.add_widget(
                    Action(
                        "Previous motions",
                        lambda count=count: self.turn_contact_page(-1, count),
                        disabled=self.contact_page == 0,
                    )
                )
                navigation.add_widget(
                    Action(
                        "Next motions",
                        lambda count=count: self.turn_contact_page(1, count),
                        disabled=first + self.page_size >= len(candidates),
                    )
                )
                self.rows.add_widget(navigation)

    def capture_description(self, cause):
        """Explain otherwise identical headings without merging their evidence."""
        geometry = cause.key[-1]
        text = f"Captured method: {cause.method}"
        if cause.key in self.capture_labels and len(geometry) == 4:
            _, minimum, maximum, sections = geometry
            low = ", ".join(f"{value:.6g}" for value in minimum)
            high = ", ".join(f"{value:.6g}" for value in maximum)
            text += f"\n{self.capture_labels[cause.key]} · obstacle XYZ bounds ({low}) to ({high}) mm"
            if sections:
                text += "\nBody sections from tool tip · " + "; ".join(
                    f"Z {section.low_mm:.6g}–{section.high_mm:.6g} mm, radius {section.radius_mm:.6g} mm"
                    for section in sections
                )
        return text


class ClearancePlot(StencilView):
    def __init__(self, on_select, **kwargs):
        super().__init__(size_hint_y=None, height=dp(190), **kwargs)
        self.report = None
        self.component = "All"
        self.visible_points = None
        self.scale_mm = 25
        self.y_maximum = 25
        self.selected = None
        self.rendered = ()
        self._bin_key = None
        self._bin_owners = None
        self._extent = 1
        self._automatic_maximum = 1
        self.on_select = on_select
        self.ink = Canvas()
        self.canvas.add(self.ink)
        self.bind(pos=lambda *_: self.paint(), size=lambda *_: self.paint())

    def plot_bounds(self):
        gutter, edge = min(dp(42), self.width * 0.2), min(dp(6), self.width * 0.05)
        return self.x + gutter, self.y + dp(12), max(1, self.width - gutter - edge), max(1, self.height - dp(24))

    def paint(self):
        self.ink.clear()
        if not self.report:
            self.rendered = ()
            self._bin_key = self._bin_owners = None
            return
        left, bottom, width, height = self.plot_bounds()
        count = min(800, max(1, int(width / dp(2))))
        key = (id(self.report), id(self.visible_points), self.component, count)
        if key != self._bin_key:
            points = [
                p
                for p in (self.report.points if self.visible_points is None else self.visible_points)
                if p.upper_mm is not None and (self.component == "All" or p.component == self.component)
            ]
            self._extent = max((p.end_distance_mm for p in self.report.points), default=1) or 1
            self._automatic_maximum = max((p.upper_mm for p in points), default=1) or 1
            # Only geometry/filter/bucket changes scan the full captured report.
            # Selection, translation, scale and height repaint the retained bins.
            bins = {}
            for point in points:
                center = (point.start_distance_mm + point.end_distance_mm) / 2
                bucket = min(count - 1, int(center / self._extent * count))
                bucket_key = (point.component, bucket)
                if bucket_key not in bins or point.lower_mm < bins[bucket_key].lower_mm:
                    bins[bucket_key] = point
            self.rendered = tuple(bins.values())
            self._bin_key = key
            self._bin_owners = (self.report, self.visible_points)  # Prevent identity reuse while cached.
        extent = self._extent
        maximum = self.scale_mm or self._automatic_maximum
        self.y_maximum = maximum
        with self.ink:
            Color(*BORDER)
            for fraction in (0, 0.25, 0.5, 0.75, 1):
                y = bottom + height * fraction
                Color(*BORDER)
                Line(points=[left, y, left + width, y], width=0.7)
                tick = CoreLabel(text=f"{maximum * fraction:g}", font_name="Roboto", font_size=dp(10), color=MUTED)
                tick.refresh()
                Color(1, 1, 1, 1)
                Rectangle(
                    texture=tick.texture, pos=(self.x + dp(3), y - tick.texture.size[1] / 2), size=tick.texture.size
                )
            for point in self.rendered:
                x0 = left + width * point.start_distance_mm / extent
                x1 = left + width * point.end_distance_mm / extent
                y0 = bottom + height * min(maximum, point.lower_mm) / maximum
                y1 = bottom + height * min(maximum, point.upper_mm) / maximum
                Color(*(DANGER if point.upper_mm == 0 else AMBER if point.lower_mm == 0 else COLORS[point.component]))
                Line(points=[x0, y0, max(x0 + dp(1), x1), y0], width=1.4)
                Line(points=[(x0 + x1) / 2, y0, (x0 + x1) / 2, y1], width=1)
            if self.selected:
                middle = (self.selected.start_distance_mm + self.selected.end_distance_mm) / 2
                x = left + width * middle / extent
                Color(*MUTED)
                Line(points=[x, self.y, x, self.top], width=1.1)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.rendered:
            extent = self._extent
            left, bottom, width, height = self.plot_bounds()
            maximum = self.y_maximum

            def screen_distance(point):
                x0 = left + width * point.start_distance_mm / extent
                x1 = left + width * point.end_distance_mm / extent
                y = bottom + height * min(maximum, point.lower_mm) / maximum
                dx = max(x0 - touch.x, touch.x - x1, 0)
                return dx * dx + (y - touch.pos[1]) ** 2

            point = min(self.rendered, key=lambda p: (screen_distance(p), p.lower_mm))
            self.selected = point
            self.paint()
            self.on_select(point)
            return True
        return super().on_touch_down(touch)


class ClearanceCard(Surface):
    def __init__(self, seek, on_selected=None, on_source=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.seek = seek
        self.on_selected = on_selected
        self.report = None
        self.review_points = ()
        self.review_position = None
        header = AdaptiveGrid(max_cols=2, min_width=150, row_height=34, spacing=dp(6))
        self.title = label("Motion minima · mm", 13, height=34, bold=True)
        self.title.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        header.add_widget(self.title)
        self.model_action = Action("Model details", self.toggle_model, height=dp(34))
        header.add_widget(self.model_action)
        self.add_widget(header)
        self.headline = content_label("Calculate material removal, then review the captured setup.")
        self.add_widget(self.headline)
        self.summary = content_label("Calculate material removal, then review clearances to plot the captured setup.")
        self.model_open = False
        self.model_body = BoxLayout(orientation="vertical", size_hint_y=None)
        self.model_body.bind(minimum_height=self.model_body.setter("height"))
        controls = AdaptiveGrid(max_cols=3, min_width=140, row_height=34, spacing=dp(6))
        self.component = Choice(text="All", values=("All", "cutter", "shank", "holder"))
        self.scale = Choice(text="25 mm", values=("5 mm", "25 mm", "Auto"))
        self.review = Choice(
            text="All intervals",
            values=("All intervals", "Contact / near-contact", "Precision unresolved", "Positive separation"),
        )
        controls.add_widget(self.component)
        controls.add_widget(self.review)
        controls.add_widget(self.scale)
        self.add_widget(controls)
        self.plot = ClearancePlot(self.select)
        self.add_widget(self.plot)
        self.axes = content_label(
            "Y: 0–25 mm · X: cumulative resolved motion distance · cutter amber / body blue / holder teal"
        )
        self.add_widget(self.axes)
        self.review_status = content_label("No captured intervals.")
        self.add_widget(self.review_status)
        navigation = AdaptiveGrid(max_cols=2, min_width=130, row_height=34, spacing=dp(6))
        self.previous_interval = Action("Previous interval", lambda: self.navigate(-1), disabled=True)
        self.next_interval = Action("Next interval", lambda: self.navigate(1), disabled=True)
        navigation.add_widget(self.previous_interval)
        navigation.add_widget(self.next_interval)
        self.add_widget(navigation)
        self.details = content_label(
            "Select a motion interval. Each horizontal mark is the minimum over that entire motion; it is not an instantaneous position trace."
        )
        self.add_widget(self.details)
        footer = AdaptiveGrid(max_cols=2, min_width=130, row_height=34, spacing=dp(6))
        self.inspect = Action(
            "Show motion in preview", lambda: self.seek(self.plot.selected), height=dp(34), disabled=True
        )
        footer.add_widget(self.inspect)
        self.source_action = Action(
            "Source details", lambda: on_source() if on_source else None, height=dp(34), disabled=True
        )
        footer.add_widget(self.source_action)
        self.add_widget(footer)
        self.component.bind(text=lambda *_: self.update_plot())
        self.review.bind(text=lambda *_: self.update_plot())
        self.scale.bind(text=lambda *_: self.update_plot())

    def toggle_model(self):
        self.model_open = not self.model_open
        if self.model_open:
            self.model_body.add_widget(self.summary)
            self.add_widget(self.model_body, index=len(self.children) - 2)
        else:
            self.remove_widget(self.model_body)
            self.model_body.remove_widget(self.summary)
        self.model_action.text = "Hide details" if self.model_open else "Model details"

    def set_report(self, report):
        self.report = self.plot.report = report
        self.plot.selected = None
        self.review_position = None
        self.inspect.disabled = True
        self.source_action.disabled = True
        unknown = sum(p.upper_mm is None for p in report.points)
        unresolved = sum(
            p.upper_mm is not None and p.upper_mm - p.lower_mm > report.tolerance_mm for p in report.points
        )
        near = sum(p.lower_mm == 0 and p.upper_mm is not None and p.upper_mm > 0 for p in report.points)
        coverage = f"{report.processed_segments}/{report.total_segments} motions examined"
        if report.scope_lines:
            coverage += f" · lines {report.scope_lines[0]}–{report.scope_lines[1]}"
        if report.cancelled or report.budget_exhausted:
            coverage += " · PARTIAL: " + ("cancelled" if report.cancelled else "calculation budget reached")
        grid = (
            f" · stock grid {report.stock_resolution_mm:g} mm"
            if report.stock_resolution_mm is not None
            else " · initial stock bounds"
        )
        self.headline.text = (
            f"{coverage}{grid}\nNumerical target {report.tolerance_mm:g} mm · Above target: {unresolved} · Near-contact: {near}"
            f"\nPhysical clearance unqualified · Missing model/reference items: {len(report.unknown_components)}"
        )
        if unknown:
            self.headline.text += f" · No upper bound: {unknown}"
        self.summary.text = f"{coverage} · numerical tolerance {report.tolerance_mm:g} mm\n{unresolved} intervals above numerical target; {near} contact/near-contact intervals; {unknown} intervals lack upper bounds. {report.qualification}.\n{report.stock_basis}."
        if report.stock_resolution_mm is not None:
            self.summary.text += f" · stock grid {report.stock_resolution_mm:g} mm; numerical tolerance does not bound stock-model error."
        if report.unknown_components:
            self.summary.text += "\nUnknown: " + "; ".join(report.unknown_components)
        self.details.text = (
            "Select a plotted motion interval to inspect its source and assembly section."
            if report.points
            else "No modeled obstacle pairs were available; clearance is unknown."
        )
        self.update_plot()

    def update_plot(self):
        self.plot.component = self.component.text
        points = self.report.points if self.report else ()
        tolerance = self.report.tolerance_mm if self.report else 0
        self.review_points = tuple(
            p
            for p in points
            if (self.component.text == "All" or p.component == self.component.text)
            and (
                self.review.text == "All intervals"
                or self.review.text == "Contact / near-contact"
                and p.lower_mm == 0
                or self.review.text == "Precision unresolved"
                and (p.upper_mm is None or p.upper_mm - p.lower_mm > tolerance)
                or self.review.text == "Positive separation"
                and p.lower_mm > 0
            )
        )
        self.plot.visible_points = self.review_points
        if self.plot.selected and not any(p is self.plot.selected for p in self.review_points):
            self.plot.selected = None
            self.review_position = None
            self.details.text = "Selection is outside this filter. Choose a matching interval."
            self.inspect.disabled = True
            self.source_action.disabled = True
        self.plot.scale_mm = None if self.scale.text == "Auto" else float(self.scale.text.split()[0])
        self.plot.paint()
        if self.report and not self.plot.rendered:
            self.details.text = (
                "No intervals match this filter. Missing model evidence remains separate."
                if not self.review_points and self.report.points
                else "Matching intervals lack upper bounds. Use Next interval to inspect their source; numeric clearance remains unknown."
                if self.review_points
                else "No numeric trace for this selection: geometry, orientation or obstacle inputs are missing. Clearance remains unknown."
            )
        points = self.report.points if self.report else ()
        extent = max((p.end_distance_mm for p in points), default=0)
        maximum = self.plot.y_maximum
        self.axes.text = f"Y: 0–{maximum:g} mm · X: 0–{extent:,.2f} mm resolved motion\nCutter amber · body blue · holder teal · contact red · possible near-contact amber. Values above the Y range are clipped; selection retains exact values. Display bins retain their smallest lower bound."

        self.refresh_navigation()

    def refresh_navigation(self):
        selected = self.plot.selected
        if selected is None:
            self.review_position = None
        elif (
            self.review_position is None
            or not 0 <= self.review_position < len(self.review_points)
            or self.review_points[self.review_position] is not selected
        ):
            self.review_position = next((i for i, p in enumerate(self.review_points) if p is selected), None)
        total = len(self.report.points) if self.report else 0
        count = len(self.review_points)
        position = self.review_position
        self.review_status.text = f"{count}/{total} matching intervals · " + (
            f"selected {position + 1}/{count}" if position is not None else "none selected"
        )
        self.previous_interval.disabled = not count or position == 0
        self.next_interval.disabled = not count or position == count - 1

    def navigate(self, delta):
        if not self.review_points:
            return
        self.refresh_navigation()
        index = (
            (0 if delta > 0 else len(self.review_points) - 1)
            if self.review_position is None
            else self.review_position + delta
        )
        if 0 <= index < len(self.review_points):
            self.select(self.review_points[index], review_index=index)

    def select(self, point, *, review_index=None):
        if review_index is None:
            review_index = next((i for i, p in enumerate(self.review_points) if p is point), None)
        if (
            review_index is None
            or not 0 <= review_index < len(self.review_points)
            or self.review_points[review_index] is not point
        ):
            return  # A detached plot result must not retarget the current source.
        self.review_position = review_index
        self.plot.selected = point
        self.inspect.disabled = False
        self.source_action.disabled = False
        value = (
            f"{point.lower_mm:.4f}–{point.upper_mm:.4f} mm"
            if point.upper_mm is not None
            else f"≥ {point.lower_mm:.4f} mm lower bound; exact clearance unknown"
        )
        interval_state = (
            "Model separation has a positive lower bound"
            if point.lower_mm > 0
            else "Envelope contact/near-contact remains possible"
        )
        if point.upper_mm is None or point.upper_mm - point.lower_mm > self.report.tolerance_mm:
            interval_state += " · numerical target unresolved"
        section = point.section
        self.details.text = f"Line {point.line} · T{point.tool_id} · {point.component} near {point.obstacle}\nClearance: {value}\n{interval_state}\n{point.method}\nSection: tip +{section.low_mm:.3f}–{section.high_mm:.3f} mm · radius {section.radius_mm:.3f} mm\n{section.source}"
        if point.upper_mm == 0:
            self.details.text += "\nPotential envelope contact; contact position within this motion is not localized."
        if point.fraction is not None:
            self.details.text += f"\nDistance witness at {100 * point.fraction:.2f}% of this resolved motion; not a measured contact position."
        self.plot.paint()
        if self.on_selected:
            self.on_selected(point)
        self.refresh_navigation()
