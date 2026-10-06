"""Physical assemblies and explicit raw-report attribution in the workbench."""

import math
import threading
from datetime import datetime, timezone

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    AMBER,
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.tool_passport import SECTIONS, passport_sections


def wrapped(*, collapse_empty=False):
    item = Label(font_name="Roboto", font_size=sp(11), color=MUTED, halign="left", valign="top", size_hint_y=None)
    item.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))

    def fit(obj, *_):
        obj.height = 0 if collapse_empty and not obj.text else max(dp(40), obj.texture_size[1] + dp(12))

    item.bind(texture_size=fit, text=fit)
    fit(item)
    return item


def stamp(value):
    try:
        return (
            datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value > 0 else "Unknown time"
        )
    except (ValueError, OverflowError, OSError):
        return "Invalid time"


class ToolCustodyPanel(Surface):
    def __init__(self, comparison):
        super().__init__(orientation="vertical", spacing=dp(8), padding=dp(8), size_hint_y=None)
        self.comparison = comparison
        self.selected_id = None
        self._signature = None
        self._recipe_request = 0
        self.selected_recipe_id = None
        self._passport_view_identity = None
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Physical assemblies & saved receipts", 13, height=26, bold=True))
        self.choice = Choice(text="Select an assembly", values=())
        self.choice.bind(text=self.select_assembly)
        self.add_widget(self.choice)
        self.passport_section = Choice(text="Overview", values=SECTIONS)
        self.passport_section.bind(text=lambda *_: self.render_passport())
        self.add_widget(self.passport_section)
        self.recipe_choice = Choice(text="No linked process recipes", values=())
        self.recipe_choice.bind(text=self.select_recipe)
        self.passport_view = DesktopScrollView(size_hint_y=None, height=dp(240), do_scroll_x=False)
        self.passport_content = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.passport_content.bind(minimum_height=self.passport_content.setter("height"))
        self.summary = wrapped()
        self.passport_content.add_widget(self.summary)
        self.passport_view.add_widget(self.passport_content)
        self.add_widget(self.passport_view)
        self.bind(width=self._size_passport_view)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        actions.add_widget(Action("New assembly", self.new_assembly))
        self.assign_button = Action("Declare at selected tool", self.review_assignment)
        actions.add_widget(self.assign_button)
        actions.add_widget(Action("Link a raw receipt", self.review_link))
        self.edit_button = Action("Edit assembly", self.edit_assembly)
        self.release_button = Action("Remove declaration", self.review_release)
        self.profile_button = Action("Open cutter design", self.open_profile)
        actions.add_widget(self.edit_button)
        actions.add_widget(self.release_button)
        actions.add_widget(self.profile_button)
        self.preview_button = Action("Preview assembly", self.preview_assembly)
        actions.add_widget(self.preview_button)
        actions.add_widget(Action("Clear assembly preview", self.clear_preview))
        self.history_button = Action("View history", self.show_history)
        actions.add_widget(self.history_button)
        actions.add_widget(Action("Calibration bench", self.comparison.open_calibration_bench))
        self.drawing_button = Action("Inspect dimensions", self.inspect_dimensions)
        actions.add_widget(self.drawing_button)
        self.recipe_button = Action("Link facing recipe", self.review_recipe)
        self.restore_recipe_button = Action("Restore selected recipe", self.restore_recipe)
        actions.add_widget(self.recipe_button)
        actions.add_widget(self.restore_recipe_button)
        self.hole_recipe_button = Action("Link hole/thread recipe", self.review_hole_recipe)
        actions.add_widget(self.hole_recipe_button)
        self.lifecycle_buttons = [
            Action("Record cutting use", self.record_use),
            Action("Record inspection", self.record_inspection),
            Action("Declare replacement", self.record_replacement),
            Action("View lifecycle", self.show_lifecycle),
        ]
        for button in self.lifecycle_buttons:
            actions.add_widget(button)
        self.actions = actions
        self._action_buttons = {button.text: button for button in reversed(actions.children)}
        self.action_slot = DesktopScrollView(size_hint_y=None, do_scroll_x=False)
        self.action_slot.add_widget(actions)
        actions.bind(cols=self._size_action_slot)
        self.add_widget(self.action_slot)
        self._size_action_slot()
        self.result = wrapped()
        self.add_widget(self.result)
        self.refresh(force=True)

    def _size_passport_view(self, _panel, width):
        # Section length must not resize the surrounding Setup viewport. Keep
        # selectors/actions in place while evidence scrolls in its own pane.
        self.passport_view.height = max(dp(160), min(dp(240), width * 0.3))

    def _size_action_slot(self, *_):
        rows = min(3, math.ceil(6 / self.actions.cols))
        self.action_slot.height = rows * self.actions.row_height + (rows - 1) * dp(6)

    def _show_section_actions(self, section):
        groups = {
            "Overview": (
                "New assembly",
                "Edit assembly",
                "Preview assembly",
                "Clear assembly preview",
                "Inspect dimensions",
                "Open cutter design",
            ),
            "Geometry": ("Edit assembly", "Inspect dimensions", "Preview assembly", "Clear assembly preview"),
            "Assets": ("Edit assembly", "Open cutter design", "Inspect dimensions"),
            "Measurements": ("Calibration bench", "Link a raw receipt", "View history"),
            "Recipes": ("Link facing recipe", "Link hole/thread recipe", "Restore selected recipe"),
            "Locations": ("Declare at selected tool", "Remove declaration"),
            "Revisions": ("Edit assembly", "View history"),
            "Lifecycle": ("Record cutting use", "Record inspection", "Declare replacement", "View lifecycle"),
        }
        wanted = groups.get(section, groups["Overview"])
        current = tuple(button.text for button in reversed(self.actions.children))
        if current != wanted:
            self.actions.clear_widgets()
            for title in wanted:
                self.actions.add_widget(self._action_buttons[title])
            self.action_slot.scroll_y = 1

    @property
    def store(self):
        return self.comparison.workspace.machine.tool_custody

    def selected(self):
        return self.store.assembly(self.selected_id)

    def select_assembly(self, _choice, value):
        self.selected_id = self.options.get(value)
        self.refresh(force=True)

    def select_recipe(self, _choice, value):
        self.selected_recipe_id = self.recipe_options.get(value)
        self._recipe_request += 1

    def refresh(self, force=False):
        ws = self.comparison.workspace
        machine = ws.selected_machine_profile
        signature = (
            id(self.store),
            self.store.generation,
            self.selected_id,
            self.comparison.selected,
            machine,
            self.store.error,
            getattr(ws.machine, "tool_custody_capture_error", None),
            repr(ws.machine.gcode_viewer.assembly_preview_binding),
            (id(ws.profile_store), ws.profile_store.generation) if ws.profile_store else None,
        )
        if not force and self._signature == signature:
            return
        self._signature = signature
        events = self.store.events
        self.options = {f"{e['name']} · {e['id'][:8]}": e["id"] for e in self.store.assemblies()}
        self.choice.values = tuple(self.options)
        assembly = self.selected()
        caption = next(
            (title for title, identity in self.options.items() if identity == self.selected_id), "Select an assembly"
        )
        if self.choice.text != caption:
            self.choice.text = caption
        selected_number = self.comparison.selected
        retired_ids = {e["assembly_id"] for e in events if e["kind"] == "replacement"}
        self.assign_button.disabled = not (assembly and machine and selected_number) or self.selected_id in retired_ids
        self.preview_button.disabled = not assembly or not assembly["profile_id"]
        self.drawing_button.disabled = not assembly or not assembly["profile_id"]
        self.edit_button.disabled = not assembly
        self.history_button.disabled = not assembly
        for button in self.lifecycle_buttons:
            button.disabled = not assembly or (button.text == "Declare replacement" and self.selected_id in retired_ids)
        self.release_button.disabled = not assembly or not any(
            e["assembly_id"] == assembly["id"] for e in self.store.locations().values()
        )
        self.profile_button.disabled = not assembly or not assembly["profile_id"]
        self.recipe_button.disabled = not assembly or not assembly["profile_id"]
        self.hole_recipe_button.disabled = self.recipe_button.disabled
        recipes = [
            e
            for e in reversed(events)
            if e["kind"] in {"facing_recipe", "hole_recipe"} and assembly and e["assembly_id"] == assembly["id"]
        ]
        self.recipe_options = {
            f"{e['recipe'].get('material', e['recipe'].get('thread', 'Recipe'))} · {e['recipe'].get('stage', 'facing')} · {stamp(e['at'])} · {e['id'][:8]}": e[
                "id"
            ]
            for e in recipes
        }
        self.recipe_choice.values = tuple(self.recipe_options)
        self.recipe_choice.text = next(
            (title for title, identity in self.recipe_options.items() if identity == self.selected_recipe_id),
            next(iter(self.recipe_options), "No linked process recipes"),
        )
        self.recipe_choice.disabled = not recipes
        self.restore_recipe_button.disabled = not recipes
        linked = {e["report_id"] for e in events if e["kind"] == "link"}
        unassigned = sum(e["kind"] == "report" and e["id"] not in linked for e in events)
        lines = [
            f"{len(self.options)} saved assemblies · {unassigned} unassigned calibration receipts",
            "Local declarations and report links require operator attribution; they do not verify installed hardware.",
        ]
        if assembly:
            from carveracontroller.machine.tool_lifecycle import summary as lifecycle_summary

            lines.extend(lifecycle_summary(self.store, assembly["id"])[:4])
            lines += [
                f"Assembly ID: {assembly['id']} · revision {assembly['revision_count']} ({assembly['revision_id'][:8]})",
                f"Holder: {assembly['holder'] or 'Unknown'} · declared stickout: {assembly['stickout_mm'] if assembly['stickout_mm'] is not None else 'Unknown'} mm",
            ]
            lines.append(
                "Assembly holder CAD: "
                + (assembly.get("holder_geometry_path") or "Missing; holder clearance cannot be established")
            )
            binding = ws.machine.gcode_viewer.assembly_preview_binding
            if binding and binding["assembly_id"] == assembly["id"]:
                from carveracontroller.machine.assembly_preview import design_fingerprint

                profile = (
                    next((p for p in ws.profile_store.data["tools"] if p["id"] == binding["profile_id"]), None)
                    if ws.profile_store
                    else None
                )
                current = (
                    binding["revision_id"] == assembly["revision_id"]
                    and profile is not None
                    and design_fingerprint(profile) == binding["design_fingerprint"]
                )
                lines.append(
                    f"Rendered at T{binding['number']}: "
                    + (
                        "current declared definition"
                        if current
                        else "OLDER assembly or cutter design; preview again to update"
                    )
                )
            machine_names = {p["id"]: p["name"] for p in ws.profile_store.data["machines"]} if ws.profile_store else {}
            if machine:
                machine_names[machine["id"]] = machine["name"]
            locations = [
                f"{machine_names.get(key[0], key[0])} / T{key[1]} ({'current definition' if event.get('revision_id') == assembly['revision_id'] else 'older or unversioned definition; reconcile'})"
                for key, event in self.store.locations().items()
                if event["assembly_id"] == assembly["id"]
            ]
            lines.append("Declared locations: " + (", ".join(locations) or "None"))
            reports = self.store.assembly_reports(assembly["id"])
            lines.append(
                f"{len(reports)} attributed calibration receipts · latest shown below; View history for earlier evidence"
            )
            history_lines = []
            attributions = {e["report_id"]: e for e in events if e["kind"] == "link"}
            for event in reversed(reports[-10:]):
                revision = attributions[event["id"]].get("revision_id")
                association = (
                    "current definition"
                    if revision == assembly["revision_id"]
                    else "older definition"
                    if revision
                    else "unversioned attribution"
                )
                history_lines.append(
                    f"Calibration attribution: {association} · {revision[:8] if revision else 'revision unknown'}"
                )
                report = event["report"]
                samples = ", ".join(f"{v:.6g}" for v in report["measurements"])
                history_lines.append(
                    f"{stamp(report['timestamp'])} · T{event['tool_number'] if event['tool_number'] is not None else 'Unknown'} · source {event['endpoint'] or 'Unknown'}\nSamples mm: {samples} · spread {report['max_delta']:.6g} mm · applied TLO {report['applied'] if report['applied'] is not None else 'Unknown'} mm"
                )
            lines.extend(history_lines[:2])
            lines.append("Spread is raw repeatability evidence, not a diagnosis of cutter wear or damage.")
            history_lines.append("Definition history · latest 10 shown")
            for revision in reversed(self.store.revisions(assembly["id"])[-10:]):
                history_lines.append(
                    f"{stamp(revision['at'])} · {revision['id'][:8]} · {revision['name']} · holder {revision['holder'] or 'Unknown'} · stickout {revision['stickout_mm']} mm · design {revision['profile_id'] or 'None'}\n{revision.get('note', 'Initial definition')}"
                )
            history_lines.append("Declared location history · latest 10 shown")
            moves = [e for e in events if e["kind"] in ("assignment", "release") and e["assembly_id"] == assembly["id"]]
            for move in reversed(moves[-10:]):
                place = f"{machine_names.get(move['machine_id'], move['machine_id'])} / T{move['slot']}"
                detail = (
                    f"Declared at {place}"
                    if move["kind"] == "assignment"
                    else f"Declaration removed from {place} · {move['note']}"
                )
                history_lines.append(f"{stamp(move['at'])} · {detail}")
            self.history_text = "\n".join(history_lines)
        error = self.store.error or getattr(ws.machine, "tool_custody_capture_error", None)
        if error:
            lines.append("Persistence error: " + error)
        self.summary.text = "\n".join(lines)
        self.summary.color = AMBER if error else MUTED
        self._overview_text = self.summary.text
        self._passport = passport_sections(
            self.store, self.selected_id, ws.profile_store.data if ws.profile_store else {}
        )
        self.render_passport()

    def render_passport(self):
        if not hasattr(self, "_passport"):
            return
        section = self.passport_section.text
        self._show_section_actions(section)
        if section == "Recipes" and self.recipe_choice.parent is None:
            self.passport_content.add_widget(self.recipe_choice, index=1)
        elif section != "Recipes" and self.recipe_choice.parent is self.passport_content:
            self.passport_content.remove_widget(self.recipe_choice)
        self.summary.text = (
            self._overview_text if section == "Overview" else "\n\n".join(self._passport.get(section, []))
        )
        identity = (self.selected_id, section)
        if identity != self._passport_view_identity:
            self._passport_view_identity = identity
            self.passport_view.scroll_y = 1

    def _recipe_context(self):
        assembly = self.selected()
        profiles = self.comparison.workspace.profile_store
        design = (
            next((p for p in profiles.data["tools"] if assembly and p["id"] == assembly["profile_id"]), None)
            if profiles
            else None
        )
        if assembly is None or design is None:
            raise ValueError("Select an assembly with a linked cutter design")
        return assembly, design

    def _recipe_worker(self, action, completed, failed=None, persistent=False):
        self._recipe_request += 1
        request = self._recipe_request
        self.result.text = "Reading recipe in the background…"

        def run():
            try:
                value, error = action(), None
            except (ValueError, OSError, KeyError, TypeError) as exc:
                value, error = None, str(exc)

            def deliver(_dt):
                if request != self._recipe_request and not persistent:
                    return
                if error:
                    self.result.text = "Recipe not ready: " + error
                    if failed:
                        failed(error)
                else:
                    try:
                        completed(value)
                    except (ValueError, KeyError, TypeError) as exc:
                        self.result.text = "Recipe context changed: " + str(exc)

            Clock.schedule_once(deliver, 0)

        threading.Thread(target=run, daemon=True).start()

    def review_hole_recipe(self):
        from carveracontroller.machine.tool_process import HOLE_STAGE_SHAPES

        stage = Choice(text="Choose operation stage", values=tuple(HOLE_STAGE_SHAPES))
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        body.add_widget(label("Select this assembly's role in the saved workflow", 12))
        body.add_widget(stage)
        popup = Popup(title="Link hole/thread recipe", content=body, size_hint=(0.65, None), height=dp(240))

        def choose():
            if stage.text not in HOLE_STAGE_SHAPES:
                return
            popup.dismiss()
            self.review_recipe("hole_recipe", stage.text)

        choose_button = Action("Choose recipe file", choose, primary=True)
        choose_button.disabled = True
        stage.bind(text=lambda *_: setattr(choose_button, "disabled", stage.text not in HOLE_STAGE_SHAPES))
        body.add_widget(choose_button)
        body.add_widget(Action("Cancel", popup.dismiss))
        popup.open()
        return popup

    def review_recipe(self, kind="facing_recipe", stage=None):
        try:
            assembly, design = self._recipe_context()
        except ValueError as exc:
            self.result.text = str(exc)
            return
        from carveracontroller.machine.tool_process import review_facing_recipe, review_hole_recipe

        def selected(path):
            self._recipe_worker(
                lambda: (
                    review_hole_recipe(path, assembly, design, stage)
                    if kind == "hole_recipe"
                    else review_facing_recipe(path, assembly, design)
                ),
                lambda recipe: self._show_recipe_review(assembly, design, recipe, kind),
            )

        self.comparison.workspace.choose_profile_file(
            selected,
            extension=".cvholes" if kind == "hole_recipe" else ".cvface",
            title="Link process recipe to assembly",
        )

    def _show_recipe_review(self, assembly, design, recipe, kind="facing_recipe"):
        from carveracontroller.machine.assembly_preview import design_fingerprint
        from carveracontroller.machine.tool_process import recipe_description

        current, current_design = self._recipe_context()
        if (
            current["revision_id"] != assembly["revision_id"]
            or design_fingerprint(current_design) != recipe["design_fingerprint"]
        ):
            self.result.text = "Assembly or cutter changed during review; reopen the recipe"
            return None
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        detail = wrapped()
        detail.text = f"Link to {assembly['name']} · r{assembly['revision_count']}\n{recipe['path']}\n{recipe_description(recipe)}\nSource tool {recipe['tool_id']} / {recipe['wcs']} · dimensions match declared assembly\nThis records preparation, not a successful cut. Restoring still requires matching loaded tool geometry. Other workflow tools are not attributed by this link."
        scroll = DesktopScrollView()
        scroll.add_widget(detail)
        body.add_widget(scroll)
        note = Field(hint_text="Required reason / process provenance")
        body.add_widget(note)
        status = wrapped()
        body.add_widget(status)
        controls = AdaptiveGrid(max_cols=2, min_width=130, row_height=36, spacing=dp(8))
        popup = Popup(title="Review process recipe link", content=body, size_hint=(0.75, 0.7))
        store = self.store

        def save():
            if not note.text.strip():
                status.text = "Add the process provenance or reason for linking this recipe"
                return
            try:
                current, current_design = self._recipe_context()
            except ValueError as exc:
                status.text = str(exc)
                return
            if (
                current["revision_id"] != assembly["revision_id"]
                or design_fingerprint(current_design) != recipe["design_fingerprint"]
            ):
                status.text = "Assembly or cutter changed; reopen review"
                return
            save_button.disabled = True
            close_button.disabled = True
            reason = note.text.strip()

            def persist():
                from carveracontroller.machine.tool_process import review_facing_recipe, review_hole_recipe

                if kind == "hole_recipe":
                    checked = review_hole_recipe(recipe["path"], assembly, design, recipe["stage"], recipe["sha256"])
                    return store.link_hole_recipe(assembly["id"], assembly["revision_id"], checked, reason)
                checked = review_facing_recipe(recipe["path"], assembly, design, recipe["sha256"])
                return store.link_facing_recipe(assembly["id"], assembly["revision_id"], checked, reason)

            def saved(_event):
                popup.dismiss()
                self.refresh(force=True)
                self.passport_section.text = "Recipes"
                self.result.text = "Recipe linked locally to the reviewed assembly revision"

            def failed(error):
                status.text = error
                save_button.disabled = False
                close_button.disabled = False

            self._recipe_worker(persist, saved, failed=failed, persistent=True)

        save_button = Action("Save recipe link", save)
        controls.add_widget(save_button)
        close_button = Action("Close", popup.dismiss)
        controls.add_widget(close_button)
        body.add_widget(controls)
        popup.open()
        return popup

    def restore_recipe(self):
        try:
            assembly, design = self._recipe_context()
            from carveracontroller.machine.assembly_preview import design_fingerprint
            from carveracontroller.machine.tool_process import review_facing_recipe, review_hole_recipe

            event = next(
                e
                for e in reversed(self.store.events)
                if e["kind"] in {"facing_recipe", "hole_recipe"}
                and e["assembly_id"] == assembly["id"]
                and e["id"] == self.selected_recipe_id
            )
            recipe = event["recipe"]
            if event["revision_id"] != assembly["revision_id"] or recipe["design_fingerprint"] != design_fingerprint(
                design
            ):
                raise ValueError(
                    "Linked recipe belongs to an older assembly or cutter definition; review and link again"
                )

            def restored(prepared):
                current, current_design = self._recipe_context()
                if (
                    current["revision_id"] != assembly["revision_id"]
                    or design_fingerprint(current_design) != recipe["design_fingerprint"]
                    or self.selected_recipe_id != event["id"]
                ):
                    self.result.text = "Selection changed during recipe read; restore again"
                    return
                ws = self.comparison.workspace
                panel = ws.hole_planning_panel if event["kind"] == "hole_recipe" else ws.surface_planning_panel
                if event["kind"] == "hole_recipe":
                    panel.restore_reviewed_recipe(prepared[1])
                else:
                    panel.restore_reviewed_recipe(prepared[1], prepared[2], prepared[3])
                ws.select("Setup")
                if event["kind"] == "hole_recipe":
                    if not panel.details_open:
                        panel.toggle_details()
                elif not panel.expanded:
                    panel.toggle()
                self.result.text = panel.note.text

            self._recipe_worker(
                lambda: (
                    review_hole_recipe(
                        recipe["path"], assembly, design, recipe["stage"], recipe["sha256"], prepared=True
                    )
                    if event["kind"] == "hole_recipe"
                    else review_facing_recipe(recipe["path"], assembly, design, recipe["sha256"], prepared=True)
                ),
                restored,
            )
        except (ValueError, StopIteration) as exc:
            self.result.text = str(exc) or "No linked process recipe"

    def dialog(self, title, fields, action, button, *, background=False):
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        scroll = DesktopScrollView(do_scroll_x=False)
        content = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, padding=(0, 0, dp(14), 0))
        content.bind(minimum_height=content.setter("height"))
        for widget in fields:
            content.add_widget(widget)
        scroll.add_widget(content)
        body.add_widget(scroll)
        navigation = BoxLayout(size_hint_y=None, height=0, spacing=dp(8))
        previous = Action("Scroll up", lambda: scroll.scroll_page(1), height=dp(28))
        following = Action("Scroll down", lambda: scroll.scroll_page(-1), height=dp(28))
        navigation.add_widget(previous)
        navigation.add_widget(following)
        body.add_widget(navigation)

        def update_navigation(*_):
            overflow = content.height > scroll.height + dp(1)
            navigation.height = dp(28) if overflow else 0
            navigation.opacity = 1 if overflow else 0
            navigation.disabled = not overflow
            previous.disabled = not overflow or scroll.scroll_y >= 1 - 1e-6
            following.disabled = not overflow or scroll.scroll_y <= 1e-6

        scroll.bind(height=update_navigation, scroll_y=update_navigation)
        content.bind(height=update_navigation)
        error = wrapped(collapse_empty=True)
        body.add_widget(error)
        controls = AdaptiveGrid(max_cols=2, min_width=130, row_height=36, spacing=dp(8))
        popup = Popup(title=title, content=body, size_hint=(0.72, None))

        def resize(*_):
            popup.height = min(
                Window.height * 0.85, max(dp(260), content.height + error.height + navigation.height + dp(154))
            )

        content.bind(height=resize)
        error.bind(height=resize)
        navigation.bind(height=resize)
        popup.bind(width=resize)
        resize()

        pending = [False]

        def apply():
            if pending[0]:
                return
            if action is None:
                popup.dismiss()
                return
            try:
                owner_store = self.store
                work = action()
                if background:
                    # Validation/snapshot happen on the UI thread; disk work is
                    # owned by this exact prepared store, not a later selection.
                    pending[0] = True
                    controls.disabled = True
                    content.disabled = True
                    popup.auto_dismiss = False
                    error.text = "Saving lifecycle receipt in the background…"

                    def run():
                        try:
                            work()
                            message = None
                        except (ValueError, OSError, KeyError, TypeError) as exc:
                            message = str(exc)

                        def finish(_dt):
                            pending[0] = False
                            controls.disabled = content.disabled = False
                            if self.store is owner_store:
                                self.refresh(force=True)
                            if message:
                                error.text = message
                                error.color = AMBER
                            else:
                                if self.store is owner_store:
                                    self.result.text = "Saved attributed lifecycle receipt. No controller command sent."
                                popup.dismiss()

                        Clock.schedule_once(finish, 0)

                    threading.Thread(target=run, daemon=True).start()
                    return
                self.refresh(force=True)
                self.result.text = "Saved local custody event. No controller command sent."
                popup.dismiss()
            except (ValueError, OSError) as exc:
                self.refresh(force=True)
                error.text = str(exc)
                error.color = AMBER

        if action is not None:
            controls.add_widget(Action("Cancel", popup.dismiss))
        controls.add_widget(Action(button, apply, primary=True))
        body.add_widget(controls)
        self.popup, self.popup_apply = popup, apply
        popup.open()

    def show_history(self):
        self.refresh(force=True)
        if not self.selected():
            return
        history = wrapped()
        history.text = self.history_text
        self.dialog("Assembly definition & calibration history", [history], None, "Close")

    def _lifecycle_fields(self, assembly):
        explanation = wrapped()
        explanation.text = (
            f"{assembly['name']} · definition {assembly['revision_id'][:8]}\n"
            "Record attributed evidence for this physical identity. No machine command or automatic wear diagnosis."
        )
        self.lifecycle_time = Field(
            text=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            hint_text="Observation time · ISO UTC with timezone",
        )
        self.lifecycle_source = Field(hint_text="Run log / photo / instrument receipt")
        self.lifecycle_note = Field(hint_text="Observation / outcome / reason")
        fields = [
            explanation,
            label("Observation time · UTC", 11),
            self.lifecycle_time,
            label("Evidence source", 11),
            self.lifecycle_source,
            label("Observation / outcome", 11),
            self.lifecycle_note,
        ]
        return fields

    def _lifecycle_values(self):
        try:
            date = datetime.fromisoformat(self.lifecycle_time.text.strip().replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("Include a timezone in the observation time")
            occurred = date.timestamp()
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("Enter a valid ISO observation time with timezone") from exc
        return {
            "occurred_at": occurred,
            "source": self.lifecycle_source.text.strip(),
            "note": self.lifecycle_note.text.strip(),
        }

    def record_use(self):
        assembly = self.selected()
        if not assembly:
            return
        fields = self._lifecycle_fields(assembly)
        self.use_minutes = Field(hint_text="e.g. 12.5 or 3/2")
        self.use_material = Field(hint_text="Material / stock designation")
        self.use_reference = Field(hint_text="e.g. job-42/pocket-2")
        fields += [
            label("Cutting time · minutes", 11),
            self.use_minutes,
            label("Material", 11),
            self.use_material,
            label("Run / interval reference", 11),
            self.use_reference,
        ]

        def save():
            minutes = parse_quantity(self.use_minutes.text, "scalar", minimum=0.000001, maximum=525960)
            save_receipt = self.store.record_use
            fields = {
                "seconds": minutes * 60,
                "material": self.use_material.text.strip(),
                "reference": self.use_reference.text.strip(),
                **self._lifecycle_values(),
            }
            return lambda: save_receipt(
                assembly["id"],
                assembly["revision_id"],
                **fields,
            )

        self.dialog("Record physical cutter use", fields, save, "Save interval", background=True)

    def record_inspection(self):
        assembly = self.selected()
        if not assembly:
            return
        fields = self._lifecycle_fields(assembly)
        self.inspection_condition = Choice(text="unknown", values=("unknown", "serviceable", "monitor", "remove"))
        self.inspection_method = Field(hint_text="Visual / microscope / micrometer")
        self.inspection_diameter = Field(hint_text="e.g. 6.30 mm or 1/4 in")
        fields += [
            label("Operator condition", 11),
            self.inspection_condition,
            label("Inspection method", 11),
            self.inspection_method,
            label("Measured cutting diameter · optional", 11),
            self.inspection_diameter,
        ]

        def save():
            measured = self.inspection_diameter.text.strip()
            value = parse_quantity(measured, "length", minimum=0.000001, maximum=1000) if measured else None
            save_receipt = self.store.record_inspection
            fields = {
                "condition": self.inspection_condition.text,
                "measured_diameter_mm": value,
                "method": self.inspection_method.text.strip(),
                **self._lifecycle_values(),
            }
            return lambda: save_receipt(
                assembly["id"],
                assembly["revision_id"],
                **fields,
            )

        self.dialog("Record cutter inspection", fields, save, "Save inspection", background=True)

    def record_replacement(self):
        assembly = self.selected()
        if not assembly:
            return
        fields = self._lifecycle_fields(assembly)
        retired_ids = {e["assembly_id"] for e in self.store.events if e["kind"] == "replacement"}
        replacement_ids = {e["replacement_id"] for e in self.store.events if e["kind"] == "replacement"}
        candidates = {
            f"{item['name']} · {item['id'][:8]}": item
            for item in self.store.assemblies()
            if item["id"] != assembly["id"] and item["id"] not in retired_ids | replacement_ids
        }
        self.replacement_choice = Choice(text="Choose a distinct replacement", values=tuple(candidates))
        note = wrapped()
        note.text = (
            "Create a New assembly first for a new physical cutter. This retires the old identity locally; "
            "its use, measurements and location history stay intact. Existing location declarations remain "
            "unreconciled until you explicitly remove or replace them."
        )
        fields += [label("Replacement physical identity", 11), self.replacement_choice, note]

        def save():
            replacement = candidates.get(self.replacement_choice.text)
            if not replacement:
                raise ValueError("Choose a distinct replacement assembly")
            save_receipt = self.store.record_replacement
            fields = self._lifecycle_values()
            return lambda: save_receipt(
                assembly["id"],
                assembly["revision_id"],
                replacement["id"],
                replacement["revision_id"],
                **fields,
            )

        self.dialog("Declare physical cutter replacement", fields, save, "Record replacement", background=True)

    def show_lifecycle(self):
        from carveracontroller.machine.tool_lifecycle import describe, page

        assembly = self.selected()
        if not assembly:
            return
        identity = assembly["id"]
        self.lifecycle_page = 0
        text = wrapped()
        status = wrapped()
        navigation = AdaptiveGrid(max_cols=2, min_width=130, row_height=36, spacing=dp(6))

        def render():
            rows, pages = page(self.store, identity, self.lifecycle_page)
            self.lifecycle_page = max(0, min(self.lifecycle_page, pages - 1))
            status.text = (
                f"{assembly['name']} · page {self.lifecycle_page + 1}/{pages} · observation order, newest first"
            )
            text.text = "\n\n".join(describe(row) for row in rows) or "No lifecycle receipts recorded."
            previous.disabled = self.lifecycle_page == 0
            following.disabled = self.lifecycle_page >= pages - 1
            if text.parent and text.parent.parent:
                text.parent.parent.scroll_y = 1

        def move(delta):
            self.lifecycle_page += delta
            render()

        previous = Action("Newer receipts", lambda: move(-1))
        following = Action("Older receipts", lambda: move(1))
        navigation.add_widget(previous)
        navigation.add_widget(following)
        self.dialog("Physical cutter lifecycle receipts", [status, navigation, text], None, "Close")
        render()

    def new_assembly(self):
        self.assembly_editor()

    def edit_assembly(self):
        assembly = self.selected()
        if assembly:
            self.assembly_editor(assembly)

    def assembly_editor(self, assembly=None):
        current = assembly or {}
        self.name_input = Field(text=current.get("name", ""), hint_text="e.g. Quarter-inch ball #1")
        self.holder_input = Field(text=current.get("holder", ""), hint_text="e.g. Collet A")
        stickout = current.get("stickout_mm")
        self.stickout_input = Field(
            text=f"{stickout:g} mm" if stickout is not None else "", hint_text="e.g. 31 mm or 1/4 in"
        )
        self.note_input = Field(hint_text="Required change reason / physical work performed")
        self.holder_asset_input = Field(
            text=current.get("holder_geometry_path", ""), hint_text="Converted holder CAD (optional)"
        )
        profiles = self.comparison.workspace.profile_store
        designs = {"No cutter design linked": ""}
        if profiles:
            designs.update({f"{p['name']} · {p['id'][:8]}": p["id"] for p in profiles.data["tools"]})
        profile_id = current.get("profile_id", "")
        if profile_id and profile_id not in designs.values():
            designs[f"Missing design · {profile_id[:8]}"] = profile_id
        self.design_input = design = Choice(
            text=next(key for key, identity in designs.items() if identity == profile_id), values=tuple(designs)
        )
        explanation = wrapped()
        explanation.text = (
            f"Edit {assembly['name']} · revision {assembly['revision_count']}. Save appends a definition; previous measurements and location declarations retain their original revision."
            if assembly
            else "Create a distinct physical assembly. This does not load a cutter profile or declare a machine location."
        )

        def save():
            value = self.stickout_input.text.strip()
            stickout = parse_quantity(value, "length", minimum=0.001, maximum=1000) if value else None
            fields = {
                "name": self.name_input.text.strip(),
                "holder": self.holder_input.text.strip(),
                "stickout_mm": stickout,
                "profile_id": designs[design.text],
                "holder_geometry_path": self.holder_asset_input.text.strip(),
            }
            if fields["holder_geometry_path"]:
                from carveracontroller.addons.tool_visualization.cad_assets import asset_summary

                summary = asset_summary(fields["holder_geometry_path"])
                if summary["origin"] != "collet":
                    raise ValueError("Holder CAD must use the collet origin")
            if assembly:
                self.store.revise(assembly["id"], assembly["revision_id"], **fields, note=self.note_input.text.strip())
                self.selected_id = assembly["id"]
            else:
                self.selected_id = self.store.create_assembly(**fields)["id"]
            self.refresh(force=True)
            self.choice.text = next(key for key, identity in self.options.items() if identity == self.selected_id)

        form = AdaptiveGrid(max_cols=2, min_width=260, row_height=72, spacing=dp(8))
        for title, field in (
            ("Cutter design reference (optional)", design),
            ("Physical assembly name / inventory tag", self.name_input),
            ("Holder or collet identity (optional)", self.holder_input),
            ("Declared stickout (mm or in; optional)", self.stickout_input),
        ):
            group = BoxLayout(orientation="vertical", spacing=dp(4))
            group.add_widget(label(title, 11, MUTED))
            group.add_widget(field)
            form.add_widget(group)
        holder_row = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(36))
        holder_row.add_widget(self.holder_asset_input)
        holder_row.add_widget(
            Action(
                "Choose holder CAD",
                lambda: self.comparison.workspace.choose_asset_file(
                    lambda path: setattr(self.holder_asset_input, "text", str(path))
                ),
                size_hint_x=0.3,
            )
        )
        fields = [
            explanation,
            form,
            label("Assembly holder geometry · converted JSON with collet origin", 11, MUTED, height=24),
            holder_row,
        ]
        if assembly:
            fields += [label("Reason for revision", 11, MUTED, height=24), self.note_input]
        self.dialog(
            "Edit physical assembly" if assembly else "New physical assembly",
            fields,
            save,
            "Save revision" if assembly else "Create assembly",
        )

    def preview_assembly(self):
        assembly = self.selected()
        if not assembly:
            return
        selected_id, revision = assembly["id"], assembly["revision_id"]

        def finished(ok, error):
            current = self.selected()
            if current is None or current["id"] != selected_id or current["revision_id"] != revision:
                return
            binding = self.comparison.workspace.machine.gcode_viewer.assembly_preview_binding
            self.result.text = (
                f"Assembly shown at preview T{binding['number']}. Saved designs, controller offsets and physical tooling are unchanged."
                if ok
                else "Assembly preview not loaded: " + error
            )
            self.refresh(force=True)

        try:
            self.result.text = "Preparing cutter and holder geometry… Previous preview retained."
            self.comparison.workspace.request_assembly_preview(selected_id, self.comparison.selected, finished)
        except (ValueError, OSError) as exc:
            self.result.text = str(exc)

    def clear_preview(self):
        def finished(ok, error):
            self.result.text = "Previous local tooling restored." if ok else "Preview not cleared: " + error
            self.refresh(force=True)

        self.result.text = "Restoring previous local tooling…"
        self.comparison.workspace.request_clear_assembly_preview(finished)

    def open_profile(self):
        assembly = self.selected()
        ws = self.comparison.workspace
        if not assembly or not assembly["profile_id"] or not ws.profile_store:
            return
        if not any(p["id"] == assembly["profile_id"] for p in ws.profile_store.data["tools"]):
            self.result.text = (
                "Linked cutter design is missing. Edit the assembly to relink; its historical reference is retained."
            )
            return
        ws._open_profiles()
        ws.profile_library.select_record("tools", assembly["profile_id"])

    def inspect_dimensions(self):
        assembly = self.selected()
        ws = self.comparison.workspace
        if not assembly or not ws.profile_store:
            return None
        try:
            from carveracontroller.desktop_tool_preview import ToolPreview
            from carveracontroller.machine.assembly_preview import assembly_definition

            profile = next((p for p in ws.profile_store.data["tools"] if p["id"] == assembly["profile_id"]), None)
            if profile is None:
                raise ValueError("Linked cutter design is missing; relink the assembly before inspecting it")
            preview = ToolPreview(assembly_definition(assembly, profile), on_close=lambda: popup.dismiss())
            popup = Popup(
                title=f"Assembly dimensions · {assembly['name']} · r{assembly['revision_count']}",
                content=preview,
                size_hint=(0.85, 0.85),
            )
            popup.bind(on_dismiss=lambda *_: preview.dispose())
            preview.mode.text = "Dimensioned drawing"
            popup.open()
            return popup
        except (ValueError, OSError) as exc:
            self.result.text = str(exc)
            return None

    def review_release(self):
        assembly = self.selected()
        if not assembly:
            return
        ws = self.comparison.workspace
        names = {p["id"]: p["name"] for p in ws.profile_store.data["machines"]} if ws.profile_store else {}
        if ws.selected_machine_profile:
            names[ws.selected_machine_profile["id"]] = ws.selected_machine_profile["name"]
        available = {
            f"{names.get(key[0], key[0])} / T{key[1]}": e
            for key, e in self.store.locations().items()
            if e["assembly_id"] == assembly["id"]
        }
        if not available:
            self.result.text = "This assembly has no declared location."
            return
        location = Choice(text=next(iter(available)), values=tuple(available))
        note = Field(hint_text="Required reason / where the assembly was moved")
        summary = wrapped()
        summary.text = f"Remove the declared location for {assembly['name']}. The physical assembly, revisions and calibration evidence remain in history. This records your assertion and sends no tool-change command."

        def remove():
            previous = available[location.text]
            self.store.release(
                previous["machine_id"], previous["slot"], assembly["id"], previous["id"], note.text.strip()
            )

        self.dialog("Review declaration removal", [summary, location, note], remove, "Remove declaration")

    def review_assignment(self):
        ws = self.comparison.workspace
        assembly, machine, slot = self.selected(), ws.selected_machine_profile, self.comparison.selected
        if not assembly or not machine or slot is None:
            self.result.text = "Select a saved machine profile, tool number and physical assembly first."
            return
        previous = self.store.assignment(machine["id"], slot)
        summary = wrapped()
        summary.text = f"Declare {assembly['name']} at {machine['name']} / T{slot}.\nPrevious declaration: {previous['assembly_id'] if previous else 'None'}.\nThis records your installation assertion. Any previous location for this assembly is superseded. Calibration history stays with its assembly. No ATC or offset command is sent."
        self.dialog(
            "Review assembly location",
            [summary],
            lambda: self.store.assign(
                machine["id"],
                slot,
                assembly["id"],
                assembly["revision_id"],
                expected_assignment_id=previous["id"] if previous else None,
            ),
            "Save declaration",
        )

    def review_link(self):
        assembly = self.selected()
        if not assembly:
            self.result.text = "Select an assembly before attributing a receipt."
            return
        linked = {e["report_id"] for e in self.store.events if e["kind"] == "link"}
        available = {
            f"{stamp(e['report']['timestamp'])} · T{e['tool_number'] if e['tool_number'] is not None else 'Unknown'} · {e['id'][:8]}": e
            for e in reversed(self.store.events)
            if e["kind"] == "report" and e["id"] not in linked
        }
        if not available:
            self.result.text = "No unassigned persistent calibration receipts. New console reports are saved separately from assembly identity."
            return
        choice = Choice(text=next(iter(available)), values=tuple(available))
        preview = wrapped()

        def update(*_):
            event = available[choice.text]
            preview.text = f"Attribute to {assembly['name']} ({assembly['id']}) · definition {assembly['revision_id'][:8]}.\nReceipt {event['id']}\nConnection source: {event['endpoint'] or 'Unknown'}\nTool number at receipt: T{event['tool_number'] if event['tool_number'] is not None else 'Unknown'}\nSamples mm: {', '.join(f'{v:.6g}' for v in event['report']['measurements'])}\nReported spread: {event['report']['max_delta']:.6g} mm\nApplied TLO: {event['report']['applied'] if event['report']['applied'] is not None else 'Unknown'} mm\nConfirm the physical identity from your setup records. Slot numbers and connection addresses alone do not establish it."

        choice.bind(text=update)
        update()
        note = Field(hint_text="Required attribution evidence / note")
        self.dialog(
            "Review calibration attribution",
            [choice, preview, note],
            lambda: self.store.link(
                available[choice.text]["id"], assembly["id"], note.text.strip(), assembly["revision_id"]
            ),
            "Attribute receipt",
        )
