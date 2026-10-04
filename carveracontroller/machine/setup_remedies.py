"""Compare declared remedies against identical captured path/stock inputs.

No setup, source stock or machine state is changed. Missing registration remains
unknown even if conservative contact candidates disappear.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import islice

from carveracontroller.addons.manufacturing_simulation import AABB, SimulationReport, ToolGeometry, Vec3, simulate


@dataclass(frozen=True)
class Remedy:
    title: str
    tool_id: str | None = None
    replacement: ToolGeometry | None = None
    obstacle: str | None = None
    shift: Vec3 | None = None

    def __post_init__(self):
        tool_change = self.tool_id is not None and isinstance(self.replacement, ToolGeometry)
        placement_change = self.obstacle is not None and isinstance(self.shift, Vec3)
        if tool_change == placement_change or not self.title.strip():
            raise ValueError("Choose exactly one tool or obstacle remedy")
        if tool_change and (self.obstacle is not None or self.shift is not None):
            raise ValueError("Tool remedy cannot also move an obstacle")
        if placement_change and (self.tool_id is not None or self.replacement is not None):
            raise ValueError("Placement remedy cannot also replace a tool")


@dataclass(frozen=True)
class RemedyComparison:
    title: str
    baseline: SimulationReport
    candidate: SimulationReport
    removed_contacts: tuple
    new_contacts: tuple
    removal_delta_mm3: float | None
    complete: bool
    warnings: tuple[str, ...]


def compare_remedy(segments, tools, scene, stock, remedy, *, cancelled=None, max_segments=20_000):
    if not isinstance(max_segments, int) or isinstance(max_segments, bool) or not 1 <= max_segments <= 20_000:
        raise ValueError("Comparison needs an integer segment budget from 1 to 20000")
    segments = tuple(islice(segments, max_segments + 1))
    if not segments or len(segments) > max_segments:
        raise ValueError("Select an operation within the comparison segment budget")
    candidate_tools = dict(tools)
    candidate_scene = scene
    warnings = ["Software geometry comparison; registration, travel and physical clearance remain unqualified."]
    if remedy.tool_id is not None:
        if remedy.tool_id not in tools or not any(s.tool_id == remedy.tool_id for s in segments):
            raise ValueError("Replacement tool is not used in the captured path")
        previous = tools[remedy.tool_id]
        candidate_tools[remedy.tool_id] = remedy.replacement
        if previous.diameter_mm != remedy.replacement.diameter_mm or previous.shape != remedy.replacement.shape:
            warnings.append(
                "Cutting shape or diameter changes: unchanged CAM may produce different feature dimensions; repost and inspect."
            )
        if previous.overall_length_mm != remedy.replacement.overall_length_mm:
            warnings.append(
                "Exposed length changes: stiffness, seating, offsets and holder geometry require separate review."
            )
        warnings.extend(remedy.replacement.clearance_notes)
    else:
        if not any(o.name == remedy.obstacle for o in scene.obstacles):
            raise ValueError("Obstacle is absent from captured geometry")
        candidate_scene = replace(
            scene,
            obstacles=tuple(
                replace(o, bounds=AABB(o.bounds.minimum + remedy.shift, o.bounds.maximum + remedy.shift))
                if o.name == remedy.obstacle
                else o
                for o in scene.obstacles
            ),
        )
        warnings.append(
            "Only the selected obstacle bounds move in program coordinates; stock/path stay fixed. Grip, mounting and coordinate registration require review."
        )
    baseline = simulate(segments, tools, stock.clone(), scene, cancelled=cancelled, max_segments=max_segments)
    candidate = simulate(
        segments, candidate_tools, stock.clone(), candidate_scene, cancelled=cancelled, max_segments=max_segments
    )
    complete = not baseline.cancelled and not candidate.cancelled
    before, after = set(baseline.candidates), set(candidate.candidates)
    return RemedyComparison(
        remedy.title,
        baseline,
        candidate,
        tuple(sorted(before - after)) if complete else (),
        tuple(sorted(after - before)) if complete else (),
        candidate.removed_volume_mm3 - baseline.removed_volume_mm3 if complete else None,
        complete,
        tuple(warnings),
    )
