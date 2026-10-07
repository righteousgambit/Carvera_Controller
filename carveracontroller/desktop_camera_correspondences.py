"""Image-linked inspection of a frozen calibration input snapshot."""

from math import dist

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Surface,
    release_screen_focus,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.camera_coverage import review_coverage
from carveracontroller.webcam_view import RegisteredCameraImage, WebcamTexture


class CorrespondenceImage(RegisteredCameraImage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.interactive = True
        self.is_focusable = True
        self.observations = ()
        self.selected_index = 0
        self.select_point = None

    def on_touch_down(self, touch):
        if (
            self.collide_point(*touch.pos)
            and getattr(touch, "button", None) in (None, "left")
            and not getattr(touch, "is_double_tap", False)
            and self.select_point is not None
        ):
            nearby = []
            for index, observation in enumerate(self.observations):
                point = self.image_pixel_to_local(observation.pixel)
                if point is not None and dist(point, touch.pos) <= dp(14):
                    nearby.append(index)
            if nearby:
                current = nearby.index(self.selected_index) if self.selected_index in nearby else -1
                self.select_point(nearby[(current + 1) % len(nearby)])
                return True
        return super().on_touch_down(touch)


def open_camera_correspondences(reference, observations, registration=None):
    observations = tuple(observations)
    if not observations:
        raise ValueError("Enter correspondences before opening image review")
    size = reference.frame.size
    review = review_coverage(observations, size, registration)
    body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
    provenance = content_label(
        f"Frozen frame {reference.frame.sequence} · {size[0]} × {size[1]} px · "
        f"source {reference.source_sha256[:12]}\n"
        "Input snapshot · physical datum, intrinsic accuracy and exposure timing unqualified."
    )
    provenance.color = MUTED
    selector = Choice(
        text=f"1/{len(observations)}",
        values=tuple(f"{index + 1}/{len(observations)}" for index in range(len(observations))),
    )
    controls = AdaptiveGrid(max_cols=3, min_width=50, row_height=30, spacing=dp(6))
    previous = Action("Prev", lambda: select(image.selected_index - 1))
    following = Action("Next", lambda: select(image.selected_index + 1))
    for widget in (previous, selector, following):
        controls.add_widget(widget)
    body.add_widget(controls)
    texture = WebcamTexture()
    texture.update(reference.frame)
    image = texture.new_view(CorrespondenceImage)
    image.observations = observations
    body.add_widget(image)
    detail = content_label("")
    information = DesktopScrollView(do_scroll_x=False, size_hint_y=None, height=dp(72))
    information_content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    information_content.bind(minimum_height=information_content.setter("height"))
    information_content.add_widget(detail)
    information_content.add_widget(provenance)
    information.add_widget(information_content)
    body.add_widget(information)
    footer = AdaptiveGrid(max_cols=3, min_width=50, row_height=30, spacing=dp(6))
    footer.add_widget(Action("Fit", image.reset_framing))
    worst = Action("Max error", lambda: select(max(range(len(observations)), key=review.residuals_px.__getitem__)))
    worst.disabled = not review.residuals_px
    footer.add_widget(worst)
    popup = Popup(title="Point review", content=body, size_hint=(0.9, 0.9))
    footer.add_widget(Action("Close", popup.dismiss))
    body.add_widget(footer)

    def select(index):
        index = min(len(observations) - 1, max(0, index))
        image.selected_index = index
        selector.text = selector.values[index]
        previous.disabled, following.disabled = index == 0, index == len(observations) - 1
        observation = observations[index]
        u, v = observation.pixel
        segments = []

        def bounded(pixel):
            return tuple(min(size[axis], max(0, value)) for axis, value in enumerate(pixel))

        def cross(pixel, radius):
            x, y = pixel
            if 0 <= x < size[0] and 0 <= y < size[1]:
                segments.extend(
                    (
                        (bounded((x - radius, y)), bounded((x + radius, y))),
                        (bounded((x, y - radius)), bounded((x, y + radius))),
                    )
                )

        for point in observations:
            cross(point.pixel, 2)
        box = ((u - 5, v - 5), (u + 5, v - 5), (u + 5, v + 5), (u - 5, v + 5))
        box = tuple(bounded(point) for point in box)
        segments.extend(zip(box, box[1:] + box[:1]))
        details = (
            f"Point {index + 1}/{len(observations)} · measured X Y Z "
            + " / ".join(f"{value:g}" for value in observation.world_mm)
            + f" mm\nImage U {u:.3f} / V {v:.3f} px · square marks selected observation."
        )
        if registration is not None:
            projected = registration.project(observation.world_mm)
            cross(projected, 4)
            segments.append((observation.pixel, projected))
            outside = not (0 <= projected[0] < size[0] and 0 <= projected[1] < size[1])
            details += (
                f"\nFitted U {projected[0]:.3f} / V {projected[1]:.3f} px · "
                f"error {review.residuals_px[index]:.3f} px"
                + (" · projected outside image" if outside else " · cross and line show reprojection")
            )
        else:
            details += "\nNo current fit · residual and projected location unavailable."
        detail.text = details
        information.scroll_y = 1
        image.set_overlay(segments, size)

    def choose(_widget, value):
        index = selector.values.index(value)
        if index != image.selected_index:
            select(index)

    selector.bind(text=choose)
    image.select_point = select
    select(0)
    popup.bind(on_dismiss=lambda *_: release_screen_focus(body))
    popup.correspondence_image = image
    popup.correspondence_selector = selector
    popup.correspondence_detail = detail
    popup.correspondence_information = information
    popup.select_correspondence = select
    popup.largest_residual = worst
    popup.reference_snapshot = reference
    popup.registration_snapshot = registration
    popup.open()
    return popup
