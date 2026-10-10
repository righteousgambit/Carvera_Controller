"""Ordered, detached remaining-material estimates beside exact initial CAD review."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from math import isfinite, prod
from types import MappingProxyType
from typing import Any, cast

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel, initial_stock
from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, ToolGeometry, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope, CollisionContact
from carveracontroller.machine.joint_clearance import bodies_from_record
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance
from carveracontroller.machine.repeat_parts import vector
from carveracontroller.machine.rotating_shape import cutting_sections
from carveracontroller.machine.scene_joint_clearance import SceneClearanceCapture
from carveracontroller.machine.simulation_preview import simulation_tools

MAX_CELLS = 2_000_000
MAX_CELL_WORK = 50_000_000
QUALIFICATION = (
    "Ordered stock estimate from retained initial cell occupancy, at each stock's explicit WCS placement. "
    "Rapid cutters and non-cutting assembly cylinders are checked against occupied cell envelopes before each move cuts. "
    "Cutting profiles remove cell centers, not complete physical cells; empty cells do not prove clearance. "
    "Rotated cells use enclosing axis-aligned boxes. Original CAD surface results still describe initial material. "
    "Curve chords with nonzero error bounds retain material instead of subtracting an uncertified sweep. "
    "Unresolved commands, ATC travel, manufactured flutes, backend motion and measured registration remain gaps. "
    "The initial occupancy is a detached declaration, not independently proven CAD provenance or prior physical stock."
)


@dataclass(frozen=True)
class StockEvolutionInput:
    stocks: Mapping[str, tuple[tuple[float, float, float], Mapping[str, Any]]]
    tools: Mapping[int, ToolGeometry]


@dataclass(frozen=True)
class StockEvolutionStep:
    segment_index: int
    line: int
    tool: int
    first: str
    second: str
    before_mm3: float
    removed_mm3: float
    remaining_mm3: float
    state: str
    contacts: tuple[CollisionContact, ...]


@dataclass(frozen=True)
class StockEvolution:
    inputs: StockEvolutionInput
    steps: tuple[StockEvolutionStep, ...]
    final_snapshots: Mapping[str, Mapping[str, Any]]
    cell_work: int
    qualification: str = QUALIFICATION


def capture_stock_inputs(
    captures: Mapping[int, SceneClearanceCapture],
    resolution_mm: float,
    *,
    cancelled: Callable[[], bool],
) -> StockEvolutionInput:
    if type(resolution_mm) not in (int, float) or not isfinite(resolution_mm) or not 0.05 <= resolution_mm <= 100:
        raise ValueError("Ordered stock resolution must be 0.05..100 mm")
    capture = next(iter(captures.values()))
    setups = []
    if capture.repeat_plan is None:
        setups.append(("stock G54 · Current stock", capture.setup))
    else:
        for part in capture.repeat_plan.parts:
            model = (
                StockModel.from_reference(part.stock_source.reference, cancelled=cancelled)
                if part.stock_source
                else None
            )
            setups.append(
                (
                    f"stock {part.wcs} · {part.name}"[:80],
                    MachineSetup(
                        work_offset_mm=part.work_offset_mm,
                        stock_origin_mm=part.stock_origin_mm,
                        stock_size_mm=part.stock_size_mm,
                        stock_model=model,
                        stock_rotation_deg=part.stock_orientation_deg[2],
                        stock_tilt_deg=part.stock_orientation_deg[:2],
                    ),
                )
            )
    stocks: dict[str, tuple[tuple[float, float, float], Mapping[str, Any]]] = {}
    cells = 0
    for name, setup in setups:
        if name in stocks:
            raise ValueError("Ordered stock requires unique retained stock names")
        stock = initial_stock(setup, resolution_mm, cancelled=cancelled)
        cells += prod(stock.shape)
        if cells > MAX_CELLS:
            raise ValueError("Ordered stock exceeds shared two-million-cell budget; increase resolution")
        stocks[name] = (setup.work_offset_mm, MappingProxyType(stock.snapshot(cancelled=cancelled)))
    tools = {tool: simulation_tools({tool: c.definition}, {str(tool)})[str(tool)] for tool, c in captures.items()}
    return StockEvolutionInput(MappingProxyType(stocks), MappingProxyType(tools))


def input_record(inputs: StockEvolutionInput) -> dict[str, Any]:
    return {
        "stocks": {
            name: {"offset_mm": offset, "initial": dict(snapshot)} for name, (offset, snapshot) in inputs.stocks.items()
        },
        "tools": {str(tool): asdict(geometry) for tool, geometry in inputs.tools.items()},
    }


def restore_inputs(value: Any) -> StockEvolutionInput:
    if not isinstance(value, dict) or set(value) != {"stocks", "tools"}:
        raise ValueError("Ordered stock requires complete initial occupancy and cutting declarations")
    stocks, tools = value["stocks"], value["tools"]
    if (
        not isinstance(stocks, dict)
        or not 1 <= len(stocks) <= 32
        or not isinstance(tools, dict)
        or not 1 <= len(tools) <= 32
    ):
        raise ValueError("Ordered stock declarations exceed bounded instance/tool contract")
    restored_stocks = {}
    for name, row in stocks.items():
        if (
            not isinstance(name, str)
            or len(name) > 80
            or not isinstance(row, dict)
            or set(row) != {"offset_mm", "initial"}
        ):
            raise ValueError("Ordered stock needs an explicit body identity, datum and initial cells")
        if not isinstance(row["initial"], dict):
            raise ValueError("Ordered stock needs complete initial occupancy")
        restored_stocks[name] = (
            vector(row["offset_mm"]),
            MappingProxyType({key: tuple(v) if isinstance(v, list) else v for key, v in row["initial"].items()}),
        )
    restored_tools = {}
    fields = set(ToolGeometry.__dataclass_fields__)
    for identifier, row in tools.items():
        if (
            not isinstance(identifier, str)
            or not identifier.isdecimal()
            or str(int(identifier)) != identifier
            or not isinstance(row, dict)
            or set(row) != fields
        ):
            raise ValueError("Ordered stock needs complete canonical tool declarations")
        data = dict(row)
        if not isinstance(data["noncutting_sections"], (list, tuple)) or len(data["noncutting_sections"]) > 256:
            raise ValueError("Ordered stock assembly sections exceed bounded contract")
        sections = []
        for section in data["noncutting_sections"]:
            if not isinstance(section, dict) or set(section) != set(AxialEnvelope.__dataclass_fields__):
                raise ValueError("Ordered stock assembly section fields differ")
            if (
                any(
                    type(section[k]) not in (int, float) or not isfinite(section[k]) or abs(section[k]) > 10000
                    for k in ("low_mm", "high_mm", "radius_mm")
                )
                or not isinstance(section["source"], str)
                or len(section["source"]) > 512
            ):
                raise ValueError("Ordered stock assembly needs finite bounded dimensions and source")
            sections.append(AxialEnvelope(**section))
        for key in fields - {"shape", "noncutting_sections", "clearance_notes"}:
            if type(data[key]) not in (int, float) or not isfinite(data[key]) or abs(data[key]) > 10000:
                raise ValueError("Ordered stock tool dimensions must be finite bounded numbers")
        notes = data["clearance_notes"]
        if (
            not isinstance(notes, (tuple, list))
            or len(notes) > 256
            or any(not isinstance(n, str) or len(n) > 512 for n in notes)
        ):
            raise ValueError("Ordered stock notes exceed bounded contract")
        data["noncutting_sections"], data["clearance_notes"] = tuple(sections), tuple(notes)
        restored_tools[int(identifier)] = ToolGeometry(**data)
    return StockEvolutionInput(MappingProxyType(restored_stocks), MappingProxyType(restored_tools))


def review_stock_evolution(
    body: ProgramBodyClearance,
    inputs: StockEvolutionInput,
    envelopes: Mapping[int, Mapping[str, Sequence[AxialEnvelope]]],
    *,
    cancelled: Callable[[], bool] = lambda: False,
    max_cell_work: int = MAX_CELL_WORK,
) -> StockEvolution:
    """Full ordered source range only; clone retained declarations, publish all or none."""
    if body.start_line != 1:
        raise ValueError(
            "Ordered stock needs a program review from line 1; selected operations lack preceding material history"
        )
    if type(max_cell_work) is not int or not 1 <= max_cell_work <= MAX_CELL_WORK:
        raise ValueError("Ordered stock work budget must be 1..50000000")
    if set(inputs.tools) != set(body.records) or set(envelopes) != set(body.records):
        raise ValueError("Ordered stock must bind every reviewed tool")
    stocks: dict[str, tuple[Vec3, StockVolume]] = {}
    cells = 0
    for name, (offset, snapshot) in inputs.stocks.items():
        if cancelled():
            raise InterruptedError("Ordered stock review cancelled; no partial report")
        # Admission precedes the bounded grid allocation. Reject bool/nonfinite dimensions.
        schema = snapshot.get("schema")
        fields = {"schema", "units", "minimum", "maximum", "resolution_mm", "occupancy_zlib_base64", "occupancy_sha256"}
        if type(schema) is not int or schema not in (1, 2, 3, 4):
            raise ValueError("Ordered stock initial snapshot schema differs")
        if schema >= 2:
            fields |= {"rotation_deg", "pivot_mm"}
        if schema >= 3:
            fields.add("initial_occupied_voxels")
        if schema == 4:
            fields.add("tilt_deg")
        if set(snapshot) != fields:
            raise ValueError("Ordered stock initial snapshot fields differ from its schema")
        low, high = snapshot.get("minimum"), snapshot.get("maximum")
        resolution = snapshot.get("resolution_mm")
        if (
            not isinstance(resolution, (int, float))
            or isinstance(resolution, bool)
            or not isfinite(resolution)
            or not 0.05 <= resolution <= 100
        ):
            raise ValueError("Ordered stock resolution must be 0.05..100 mm")
        for point in (low, high, *([snapshot["pivot_mm"]] if schema >= 2 else [])):
            if (
                not isinstance(point, (tuple, list))
                or len(point) != 3
                or any(type(v) not in (int, float) or not isfinite(v) or abs(v) > 100000 for v in point)
            ):
                raise ValueError("Ordered stock bounds must be finite millimetres")
        if schema >= 2 and (
            type(snapshot["rotation_deg"]) not in (int, float) or not isfinite(snapshot["rotation_deg"])
        ):
            raise ValueError("Ordered stock rotation must be finite degrees")
        if schema == 4 and (
            not isinstance(snapshot["tilt_deg"], (list, tuple))
            or len(snapshot["tilt_deg"]) != 2
            or any(type(v) not in (int, float) or not isfinite(v) for v in snapshot["tilt_deg"])
        ):
            raise ValueError("Ordered stock tilt must retain two finite angles")
        from math import ceil

        count = prod(
            max(1, ceil((b - a) / resolution)) for a, b in zip(cast(Sequence[float], low), cast(Sequence[float], high))
        )
        cells += count
        if cells > MAX_CELLS:
            raise ValueError("Ordered stock exceeds shared two-million-cell budget")
        stocks[name] = (Vec3(*vector(offset)), StockVolume.from_snapshot(snapshot, cancelled=cancelled))
    for tool, record in body.records.items():
        machine = machine_from_record(record)
        bodies, _ = bodies_from_record(record, machine)
        stock_bodies = {b.name: b for b in bodies if b.name.startswith("stock ")}
        if set(stock_bodies) != set(stocks):
            raise ValueError("Ordered stock must retain every reviewed stock body")
        for name, (offset_vector, stock) in stocks.items():
            box = stock_bodies[name]
            low, high = stock.bounds.minimum + offset_vector, stock.bounds.maximum + offset_vector
            if (
                box.frame != "work"
                or box.joint_count != 1
                or any(
                    abs(a - b) > 1e-6
                    for a, b in zip((*low.tuple, *high.tuple), (*box.bounds.minimum.tuple, *box.bounds.maximum.tuple))
                )
            ):
                raise ValueError("Ordered stock placement differs from its retained C1 body")
        geometry = inputs.tools[tool]
        generated = cutting_sections(geometry) + tuple(
            s for s in SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), geometry).sections() if s.component != "cutter"
        )
        declared = {
            f"T{tool} {component}": tuple(s for s in generated if s.component == component)
            for component in ("cutter", "shank", "holder")
            if any(s.component == component for s in generated)
        }
        if declared != dict(envelopes[tool]):
            raise ValueError("Ordered stock cutting/assembly dimensions differ from exact surface declarations")
    steps = []
    work = contacts_count = 0
    curved = {line for line, _command, error in body.curve_enclosures if error > 0} | set(body.curved_lines)
    for index, segment in enumerate(body.segments):
        for name, (offset_vector, stock) in stocks.items():
            if cancelled():
                raise InterruptedError("Ordered stock review cancelled; no partial report")
            geometry = inputs.tools[int(segment.tool_id)]
            sweep = SweptTool(segment.start - offset_vector, segment.end - offset_vector, geometry, segment.axis)
            work += prod(stock.shape) * (len(sweep.sections()) + 1)
            if work > max_cell_work or len(steps) >= 100_000:
                raise ValueError(
                    f"Ordered stock exhausted shared work budget at source line {segment.line}; no partial report"
                )
            held = segment.line in curved
            before = stock.remaining_volume_mm3
            contacts = tuple(
                replace(
                    c,
                    obstacle=name,
                    source_ratio=(
                        segment.source_start_ratio
                        + (segment.source_end_ratio - segment.source_start_ratio) * c.first_fraction
                        if c.first_fraction is not None
                        else None
                    ),
                )
                for c in stock.collision_contacts(sweep, cutting=segment.cutting and not held, cancelled=cancelled)
            )
            contacts_count += len(contacts)
            if contacts_count > 100_000:
                raise ValueError("Ordered stock exceeds complete contact budget; no partial report")
            if segment.cutting and not held:
                stock.subtract(sweep, cancelled=cancelled)
            steps.append(
                StockEvolutionStep(
                    index,
                    segment.line,
                    int(segment.tool_id),
                    f"T{segment.tool_id} assembly",
                    name,
                    before,
                    before - stock.remaining_volume_mm3,
                    stock.remaining_volume_mm3,
                    "curve material retained" if held else "cutting estimate" if segment.cutting else "rapid estimate",
                    contacts,
                )
            )
    final = {name: MappingProxyType(stock.snapshot(cancelled=cancelled)) for name, (_offset, stock) in stocks.items()}
    if cancelled():
        raise InterruptedError("Ordered stock review cancelled; no partial report")
    return StockEvolution(inputs, tuple(steps), MappingProxyType(final), work)


def evolution_record(result: StockEvolution, *, cancelled: Callable[[], bool] = lambda: False) -> dict[str, Any]:
    rows = []
    for index, step in enumerate(result.steps):
        if index % 64 == 0 and cancelled():
            raise InterruptedError("Ordered stock exchange cancelled; previous review retained")
        rows.append(asdict(step))
    return {
        "steps": rows,
        "final": {name: dict(snapshot) for name, snapshot in result.final_snapshots.items()},
        "cell_work": result.cell_work,
        "qualification": result.qualification,
    }
