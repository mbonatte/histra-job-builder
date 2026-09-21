"""Geometric calculations, ellipse transformations, and Quad kinematics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float

    def to_xml_str(self) -> str:
        """Format as semicoloned string for HRX attribute."""
        def _fmt(val: float) -> str:
            if abs(val - round(val)) < 1e-6:
                return str(int(round(val)))
            return f"{val:.6f}".rstrip("0").rstrip(".")

        return f"{_fmt(self.x)};{_fmt(self.y)};{_fmt(self.z)}"

    def distance_to(self, other: Point3D) -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2)

    def __add__(self, other: Point3D) -> Point3D:
        return Point3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Point3D) -> Point3D:
        return Point3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Point3D:
        return Point3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Point3D:
        return self.__mul__(scalar)


def dot(u: Tuple[float, float, float], v: Tuple[float, float, float]) -> float:
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def cross(u: Tuple[float, float, float], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )


def norm(u: Tuple[float, float, float]) -> float:
    return math.sqrt(dot(u, u))


def normalize(u: Tuple[float, float, float], default: Tuple[float, float, float] = (1.0, 0.0, 0.0)) -> Tuple[float, float, float]:
    n = norm(u)
    if n < 1e-12:
        return default
    return (u[0] / n, u[1] / n, u[2] / n)


def ellipse_arch_point(
    x_center: float,
    z_center: float,
    a: float,
    b: float,
    t_springer: float,
    t_crown: float,
    theta: float,
    y: float = 0.0,
) -> Tuple[Point3D, Point3D]:
    """Compute intrados and extrados 3D points for an arch at parametric angle theta.

    theta varies from 0 (left springer) through pi/2 (crown) to pi (right springer).
    Intrados coordinates:
        x = x_center - a * cos(theta)
        z = z_center + b * sin(theta)
    Outward normal is directed away from ellipse interior.
    Extrados = Intrados + normal * thickness(theta).
    """
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # Intrados point
    xi = x_center - a * cos_t
    zi = z_center + b * sin_t

    # Normal vector components from ellipse gradient grad( (x-xc)^2/a^2 + (z-zc)^2/b^2 - 1 )
    # grad_x = 2*(xi - xc)/a^2 = -2*cos_t/a
    # grad_z = 2*(zi - zc)/b^2 =  2*sin_t/b
    nx = -cos_t / a
    nz = sin_t / b
    mag = math.sqrt(nx * nx + nz * nz)
    if mag > 1e-12:
        nx /= mag
        nz /= mag
    else:
        nx, nz = 0.0, 1.0

    # Variable thickness: linear with sin(theta) from springer to crown
    thick = t_springer + (t_crown - t_springer) * sin_t

    # Extrados point
    xe = xi + nx * thick
    ze = zi + nz * thick

    p_int = Point3D(xi, y, zi)
    p_ext = Point3D(xe, y, ze)
    return p_int, p_ext


def signed_area_xz(points: Sequence[Point3D]) -> float:
    """Calculate 2D signed area in X-Z plane via shoelace formula."""
    n = len(points)
    return 0.5 * sum(
        points[i].x * points[(i + 1) % n].z - points[(i + 1) % n].x * points[i].z
        for i in range(n)
    )


@dataclass
class QuadKinematics:
    """Exact geometric quantities required for HiStrA Quad computational element."""

    lengths: list[float]
    diagonals: list[float]
    cosines: list[float]
    sines: list[float]
    thicknesses: list[float]
    normals: list[Point3D]
    centroid: Point3D
    ref_e1: Tuple[float, float, float]
    ref_e2: Tuple[float, float, float]
    ref_e3: Tuple[float, float, float]
    ref_origin: Point3D
    signed_area: float


def compute_quad_kinematics(
    nodes: Sequence[Point3D],
    thickness: float = 100.0,
    out_of_plane_normal: Tuple[float, float, float] = (0.0, 1.0, 0.0),
) -> QuadKinematics:
    """Compute all geometric parameters for a 4-node quadrilateral element.

    Node order: 0, 1, 2, 3 (counter-clockwise in X-Z plane).
    """
    if len(nodes) != 4:
        raise ValueError(f"Quad requires exactly 4 nodes, got {len(nodes)}")

    p0, p1, p2, p3 = nodes

    # Edge lengths
    l0 = p0.distance_to(p1)
    l1 = p1.distance_to(p2)
    l2 = p2.distance_to(p3)
    l3 = p3.distance_to(p0)
    lengths = [l0, l1, l2, l3]

    for idx, l in enumerate(lengths):
        if l < 1e-4:
            raise ValueError(f"Quad edge {idx} has zero length: {l}")

    # Diagonal lengths
    d0 = p0.distance_to(p2)
    d1 = p1.distance_to(p3)
    diagonals = [d0, d1]

    # Corner cosines via law of cosines (matching C# Quad.SetGeometry)
    cos0 = (l0 * l0 + l3 * l3 - d1 * d1) / (2.0 * l0 * l3)
    cos1 = (l0 * l0 + l1 * l1 - d0 * d0) / (2.0 * l0 * l1)
    cos2 = (l1 * l1 + l2 * l2 - d1 * d1) / (2.0 * l1 * l2)
    cos3 = (l2 * l2 + l3 * l3 - d0 * d0) / (2.0 * l2 * l3)

    raw_cosines = [cos0, cos1, cos2, cos3]
    cosines = [max(-1.0, min(1.0, c)) for c in raw_cosines]
    sines = [math.sqrt(max(0.0, 1.0 - c * c)) for c in cosines]

    # Centroid
    gx = (p0.x + p1.x + p2.x + p3.x) / 4.0
    gy = (p0.y + p1.y + p2.y + p3.y) / 4.0
    gz = (p0.z + p1.z + p2.z + p3.z) / 4.0
    centroid = Point3D(gx, gy, gz)

    # Reference system:
    # e1 = normalize(p1 - p0)
    # e3 = normalize(cross(e1, p2 - p0))
    # e2 = cross(e3, e1)
    v10 = (p1.x - p0.x, p1.y - p0.y, p1.z - p0.z)
    v20 = (p2.x - p0.x, p2.y - p0.y, p2.z - p0.z)

    e1 = normalize(v10, (1.0, 0.0, 0.0))
    cr = cross(e1, v20)
    e3 = normalize(cr, (0.0, -1.0, 0.0))
    e2 = cross(e3, e1)
    ref_origin = p0

    thicknesses = [thickness] * 4
    norm_pt = Point3D(out_of_plane_normal[0], out_of_plane_normal[1], out_of_plane_normal[2])
    normals = [norm_pt] * 4

    area = signed_area_xz(nodes)

    return QuadKinematics(
        lengths=lengths,
        diagonals=diagonals,
        cosines=cosines,
        sines=sines,
        thicknesses=thicknesses,
        normals=normals,
        centroid=centroid,
        ref_e1=e1,
        ref_e2=e2,
        ref_e3=e3,
        ref_origin=ref_origin,
        signed_area=area,
    )
