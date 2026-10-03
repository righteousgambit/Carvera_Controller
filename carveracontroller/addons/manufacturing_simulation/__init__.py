"""Bounded, millimetre-based machining geometry independent of hardware control.

Collision results use conservative swept bounding volumes, not mesh clearance
certification. Stock volume is a voxel approximation with a stated resolution.
"""

from .geometry import AABB, CollisionObstacle, CollisionResult, CollisionScene, SweptTool, ToolGeometry, Vec3
from .kinematics import (
    InverseResult,
    Joint,
    MachineKinematics,
    MachinePose,
    Transform,
    inverse_kinematics,
    unwind_rotary,
)
from .planning import SimulationReport, SimulationSegment, simulate
from .stock import RemovalResult, StockVolume

__all__ = [
    "AABB",
    "CollisionObstacle",
    "CollisionResult",
    "CollisionScene",
    "Joint",
    "InverseResult",
    "inverse_kinematics",
    "unwind_rotary",
    "MachineKinematics",
    "MachinePose",
    "RemovalResult",
    "StockVolume",
    "SimulationReport",
    "SimulationSegment",
    "simulate",
    "SweptTool",
    "ToolGeometry",
    "Transform",
    "Vec3",
]
