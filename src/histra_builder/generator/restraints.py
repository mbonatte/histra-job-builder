"""Foundation boundary restraint generation conforming to HiStrA Quad invariants."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple
from .geometry import Point3D


@dataclass
class GeneratedNodeC:
    key: int
    node_key: int
    is_independent: bool = True
    master_element_key: int = 0
    master_element_type: str = "None"


@dataclass
class GeneratedRestraint:
    key: int
    name: str
    node_key1: int
    node_key2: int
    node_c_key1: int
    node_c_key2: int
    computational_element_key: int
    computational_element_type: str = "Quad"
    computational_element_edge: int = 0
    material_key: int = 0
    layer_key: int = 0
    zg: float = 0.0
    parent_key: int = 1
    parent_type_element: str = "GeometryLineRestraint"
    k: Tuple[float, float, float, float, float, float] = (-1.0, -1.0, -1.0, -1.0, -1.0, -1.0)
    g: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 0.0))
    point1: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 0.0))
    point2: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 0.0))
    point3: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 0.0))
    point4: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 0.0))
    foundation_tag: str = ""


def create_foundation_edge_restraint(
    restraint_key: int,
    quad_key: int,
    n0_key: int,
    n1_key: int,
    p0: Point3D,
    p1: Point3D,
    node_c_map: dict[int, int],
    next_node_c_key: int,
    node_cs: list[GeneratedNodeC],
    thickness: float = 100.0,
    out_of_plane_normal: Tuple[float, float, float] = (0.0, 1.0, 0.0),
    foundation_tag: str = "",
) -> Tuple[GeneratedRestraint, int]:
    """Create a boundary Restraint and associated NodeCs for a foundation bottom Quad edge.

    Ensures exact 4-point tributary contact footprint:
        V1 = P0 - normal * (thickness / 2)
        V2 = P1 - normal * (thickness / 2)
        V3 = P1 + normal * (thickness / 2)
        V4 = P0 + normal * (thickness / 2)
    and fully fixed boundary conditions:
        k = (-1, -1, -1, -1, -1, -1)
    """
    # Obtain or create NodeC for n0
    if n0_key not in node_c_map:
        nc0_key = next_node_c_key
        next_node_c_key += 1
        node_c_map[n0_key] = nc0_key
        node_cs.append(GeneratedNodeC(key=nc0_key, node_key=n0_key))
    else:
        nc0_key = node_c_map[n0_key]

    # Obtain or create NodeC for n1
    if n1_key not in node_c_map:
        nc1_key = next_node_c_key
        next_node_c_key += 1
        node_c_map[n1_key] = nc1_key
        node_cs.append(GeneratedNodeC(key=nc1_key, node_key=n1_key))
    else:
        nc1_key = node_c_map[n1_key]

    nx, ny, nz = out_of_plane_normal
    half_t = thickness / 2.0
    offset_x = nx * half_t
    offset_y = ny * half_t
    offset_z = nz * half_t

    pt1 = Point3D(p0.x - offset_x, p0.y - offset_y, p0.z - offset_z)
    pt2 = Point3D(p1.x - offset_x, p1.y - offset_y, p1.z - offset_z)
    pt3 = Point3D(p1.x + offset_x, p1.y + offset_y, p1.z + offset_z)
    pt4 = Point3D(p0.x + offset_x, p0.y + offset_y, p0.z + offset_z)

    gx = (p0.x + p1.x) / 2.0
    gy = (p0.y + p1.y) / 2.0
    gz = (p0.z + p1.z) / 2.0
    centroid = Point3D(gx, gy, gz)

    restraint = GeneratedRestraint(
        key=restraint_key,
        name=str(restraint_key),
        node_key1=n0_key,
        node_key2=n1_key,
        node_c_key1=nc0_key,
        node_c_key2=nc1_key,
        computational_element_key=quad_key,
        computational_element_type="Quad",
        computational_element_edge=0,
        k=(-1.0, -1.0, -1.0, -1.0, -1.0, -1.0),
        g=centroid,
        point1=pt1,
        point2=pt2,
        point3=pt3,
        point4=pt4,
        foundation_tag=foundation_tag,
    )
    return restraint, next_node_c_key
