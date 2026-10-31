"""C#-parity bridge mesher for the straight wizard path.

This is the first verified slice of ``BridgeMesher.AddBridge1``:

* ``AddBridgeRow1`` / ``AddSemiArcoSx1`` / ``AddSemiArcoDx1``
* ``AddMesh4`` / ``AddMesh3`` convex-quad subdivision
* ``AddMeshArco1`` arch ring and springing pulvino
* ``AddSpallePile`` pier shaft generation for ``Hf = 0``

It intentionally works with :class:`CSharpBridgeSpec` instead of the previous
generic ``BridgeSpec`` so every C# dimension has a real home.  Later tasks add
foundation/GLR generation, multi-layer elevations, inclination/slope/curvature
and the native HRX writer.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .csharp_arch import (
    EllipseParams,
    get_intradosso_arch_ellipse,
    get_points_in_ellipse_equi_spaced,
    half_arch_params,
)
from .geometry import Point3D, compute_quad_kinematics, signed_area_xz
from .mesher import GeneratedQuad
from .csharp_model import (
    Abutment,
    BridgeDefinition,
    CSharpBridgeSpec,
    Elevations,
    Pier,
    Span,
)


def _normalise(v) -> Point3D:
    vx, vy, vz = _xyz(v)
    n = math.sqrt(vx * vx + vy * vy + vz * vz)
    if n < 1.0e-15:
        return Point3D(1.0, 0.0, 0.0)
    return Point3D(vx / n, vy / n, vz / n)


def _xyz(value) -> Tuple[float, float, float]:
    if isinstance(value, Point3D):
        return (value.x, value.y, value.z)
    return (float(value[0]), float(value[1]), float(value[2]))


def _dist(a, b) -> float:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _sub(a, b) -> Point3D:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return Point3D(ax - bx, ay - by, az - bz)


def _add(a, b) -> Point3D:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return Point3D(ax + bx, ay + by, az + bz)


def _dot(a, b) -> float:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return ax * bx + ay * by + az * bz


def _lerp(a, b, t: float) -> Point3D:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return Point3D(
        ax + (bx - ax) * t,
        ay + (by - ay) * t,
        az + (bz - az) * t,
    )


def _arrotonda(value: float) -> int:
    """C# ``Operations.Arrotonda``: round up unless the value is integral."""
    floor = math.floor(value)
    return int(floor + 1.0) if abs(value - floor) > 0.0 else int(floor)


@dataclass
class CSharpBridgeMesh:
    """Structural mesh produced by the C#-parity mesher."""

    spec: CSharpBridgeSpec
    nodes: Dict[int, Point3D]
    quads: Dict[int, GeneratedQuad]
    deck_z: float
    total_length: float


class CSharpMesher:
    """Port of the straight ``BridgeMesher.AddBridge1`` path."""

    def __init__(self, spec: CSharpBridgeSpec) -> None:
        self.spec = spec
        self.nodes: Dict[int, Point3D] = {}
        self._node_index: Dict[Tuple[float, float, float], int] = {}
        self.quads: Dict[int, GeneratedQuad] = {}
        self._next_node_key = 1
        self._next_quad_key = 1
        self._deck_z = 0.0
        self._total_length = 0.0

    # -- geometric primitives -------------------------------------------------

    def _node(self, point: Sequence[float]) -> int:
        key = (round(point[0], 4), round(point[1], 4), round(point[2], 4))
        existing = self._node_index.get(key)
        if existing is not None:
            return existing
        node_key = self._next_node_key
        self._next_node_key += 1
        self._node_index[key] = node_key
        self.nodes[node_key] = Point3D(key[0], key[1], key[2])
        return node_key

    def _quad(self, points: Sequence[Sequence[float]], material_key: int, thickness: float, group: str) -> GeneratedQuad:
        pts = [Point3D(*_xyz(p)) for p in points]
        # Preserve the C# node order: BridgeMesher relies on it for the
        # element reference system and sets the normal from the winding.
        kinematics = compute_quad_kinematics(
            pts,
            thickness=thickness,
            out_of_plane_normal=(0.0, 1.0, 0.0),
        )
        keys = tuple(self._node(_xyz(point)) for point in pts)
        key = self._next_quad_key
        self._next_quad_key += 1
        quad = GeneratedQuad(
            key=key,
            node_keys=(keys[0], keys[1], keys[2], keys[3]),
            material_key=material_key,
            thickness=thickness,
            kinematics=kinematics,
            group=group,
        )
        self.quads[key] = quad
        return quad

    # -- C# WizardBridge geometry -------------------------------------------

    def _abscissa(self) -> List[float]:
        values: List[float] = []
        cursor = 0.0
        for element in self.spec.elements:
            if isinstance(element, Span):
                cursor += element.L
                values.append(cursor - element.L / 2.0)
            elif isinstance(element, Pier):
                cursor += element.b2
                values.append(cursor - element.b2 / 2.0)
            elif isinstance(element, Abutment):
                if element.kind == "Destra":
                    cursor += element.b2
                    values.append(cursor)
                else:
                    values.append(cursor)
                    cursor += element.b2
        return values

    def _element_origin(self, target: object) -> float:
        """Return the element centre using C# cumulative Abscissa layout."""
        cursor = 0.0
        for element in self.spec.elements:
            if isinstance(element, Span):
                centre = cursor + element.L / 2.0
                cursor += element.L
            else:
                centre = cursor + element.b2 / 2.0
                cursor += element.b2
            if element is target:
                return centre
        return cursor

    def _strip_centres(self) -> List[float]:
        # C# walks from +Width/2 and subtracts half-lane widths.
        cursor = self.spec.definition.width / 2.0
        centres: List[float] = []
        for corsia in self.spec.definition.corsias:
            cursor -= corsia.width / 2.0
            centres.append(cursor)
            cursor -= corsia.width / 2.0
        return centres

    # -- AddMesh4 / AddMesh3 -------------------------------------------------

    def _add_mesh4(
        self,
        points1: Sequence[Sequence[float]],
        points2: Sequence[Sequence[float]],
        material_key: int,
        thickness: float,
        is_right: bool,
    ) -> Tuple[int, int]:
        value = _normalise(_sub(points2[1], points2[0]))
        denominator = _dot(value, _sub(points1[-1], points1[0]))
        if abs(denominator) < 1.0e-15:
            denominator = 1.0
        n = len(points1) - 1
        first_gap = _dist(points1[0], points2[0])
        last_gap = _dist(points1[-1], points2[-1])
        m = max(1, _arrotonda(max(first_gap, last_gap) / self.spec.definition.nl))

        for i in range(n):
            a: List[Point3D] = [None, None, None, None]  # type: ignore[list-item]
            a[0] = Point3D(*_xyz(points1[i]))
            a[1] = Point3D(*_xyz(points1[i + 1]))
            a[2] = _lerp(
                points2[0],
                points2[1],
                _dot(value, _sub(points1[i + 1], points1[0])) / denominator,
            )
            a[3] = _lerp(
                points2[0],
                points2[1],
                _dot(value, _sub(points1[i], points1[0])) / denominator,
            )
            for j in range(m):
                if is_right:
                    points = [
                        _lerp(a[1], a[2], j / m),
                        _lerp(a[0], a[3], j / m),
                        _lerp(a[0], a[3], (j + 1) / m),
                        _lerp(a[1], a[2], (j + 1) / m),
                    ]
                else:
                    points = [
                        _lerp(a[0], a[3], j / m),
                        _lerp(a[1], a[2], j / m),
                        _lerp(a[1], a[2], (j + 1) / m),
                        _lerp(a[0], a[3], (j + 1) / m),
                    ]
                self._quad(points, material_key, thickness, "CSharp_Fill")
        return n, m

    def _add_mesh3(
        self,
        points: Sequence[Sequence[float]],
        n: int,
        m: int,
        material_key: int,
        thickness: float,
        is_right: bool,
    ) -> None:
        for i in range(n):
            if is_right:
                a = [
                    _lerp(points[0], points[3], i / n),
                    _lerp(points[1], points[2], i / n),
                    _lerp(points[1], points[2], (i + 1) / n),
                    _lerp(points[0], points[3], (i + 1) / n),
                ]
            else:
                a = [
                    _lerp(points[0], points[3], i / n),
                    _lerp(points[1], points[2], i / n),
                    _lerp(points[1], points[2], (i + 1) / n),
                    _lerp(points[0], points[3], (i + 1) / n),
                ]
            for j in range(m):
                self._quad(
                    [
                        _lerp(a[0], a[3], j / m),
                        _lerp(a[1], a[2], j / m),
                        _lerp(a[1], a[2], (j + 1) / m),
                        _lerp(a[0], a[3], (j + 1) / m),
                    ],
                    material_key,
                    thickness,
                    "CSharp_Fill",
                )

    # -- AddSemiArcoSx1 / Dx1 ------------------------------------------------

    def _add_semi_arch(
        self,
        span: Span,
        params: EllipseParams,
        x1: float,
        x2: float,
        y: float,
        is_right: bool,
        heights: int,
    ) -> Tuple[List[Point3D], int]:
        # The verified straight model uses one elevation layer.  The full
        # multi-layer branch is added in a later parity task.
        if heights > 3:
            raise NotImplementedError("multi-layer elevation fill is not yet ported")
        z1 = self.spec.elevations.get_z(x1, 1)
        z2 = self.spec.elevations.get_z(x2, 1)

        if is_right:
            extrados = Point3D(
                params.center[0] + params.rx * math.cos(params.theta0),
                y,
                params.center[2] + params.rz * math.sin(params.theta0),
            )
            edge_x = x2
            ext_edge = Point3D(edge_x, y, extrados.z)
        else:
            extrados = Point3D(
                params.center[0] + params.rx * math.cos(math.pi - params.theta0),
                y,
                params.center[2] + params.rz * math.sin(math.pi - params.theta0),
            )
            edge_x = x1
            ext_edge = Point3D(edge_x, y, extrados.z)

        crown = Point3D(params.crown_point[0], y, params.crown_point[2])
        extrados_points = get_points_in_ellipse_equi_spaced(
            (extrados.x, extrados.y, extrados.z),
            (crown.x, crown.y, crown.z),
            params.rx,
            params.rz,
            params.center,
            self.spec.definition.nl,
        )
        extrados_points = [Point3D(p[0], y, p[2]) for p in extrados_points]

        fill_material, _, _ = self.spec.elevations.get_material_key(1)
        upper = [
            Point3D(extrados_points[0].x, y, self.spec.elevations.get_z(extrados_points[0].x, 1)),
            Point3D(extrados_points[-1].x, y, self.spec.elevations.get_z(extrados_points[-1].x, 1)),
        ]
        n4, m4 = self._add_mesh4(
            extrados_points,
            upper,
            fill_material,
            self.spec.definition.corsias[0].width,
            is_right,
        )

        side = [
            Point3D(edge_x, y, extrados.z),
            extrados,
            Point3D(extrados.x, y, self.spec.elevations.get_z(extrados.x, 1)),
            Point3D(edge_x, y, self.spec.elevations.get_z(edge_x, 1)),
        ]
        n_side = max(1, _arrotonda(min(_dist(side[0], side[1]), _dist(side[2], side[3])) / self.spec.definition.nl))
        self._add_mesh3(
            side,
            m4,
            n_side,
            fill_material,
            self.spec.definition.corsias[0].width,
            is_right,
        )
        return extrados_points, n4

    # -- AddMeshArco1 --------------------------------------------------------

    def _add_arch_ring(
        self,
        span: Span,
        params: EllipseParams,
        extrados_points: Sequence[Point3D],
        x1: float,
        x2: float,
        y: float,
        is_right: bool,
    ) -> None:
        lintradosso = span.L + span.S1 + span.S2
        for index in range(len(extrados_points) - 1):
            ext0 = extrados_points[index]
            ext1 = extrados_points[index + 1]
            int0 = get_intradosso_arch_ellipse(
                (ext0.x, ext0.y, ext0.z),
                params.center,
                params.rx,
                params.rz,
                span.Tb,
                span.Tt,
                params.theta0,
            )
            int1 = get_intradosso_arch_ellipse(
                (ext1.x, ext1.y, ext1.z),
                params.center,
                params.rx,
                params.rz,
                span.Tb,
                span.Tt,
                params.theta0,
            )
            int0 = Point3D(int0[0], y, int0[2])
            int1 = Point3D(int1[0], y, int1[2])
            if index == 0:
                if is_right:
                    int0 = Point3D(params.center[0] + lintradosso / 2.0, y, 0.0)
                else:
                    int0 = Point3D(params.center[0] - lintradosso / 2.0, y, 0.0)

            if is_right:
                points = [int0, ext0, ext1, int1]
            else:
                points = [ext0, int0, int1, ext1]
            self._quad(points, span.material_key, self.spec.definition.corsias[0].width, "CSharp_Arch")

            if index == 0 and abs(span.Asx if not is_right else span.Adx) > 1.0e-9:
                if is_right:
                    pulvino = [
                        Point3D(int0.x, y, 0.0),
                        Point3D(x2, y, 0.0),
                        Point3D(x2, y, ext0.z),
                        Point3D(ext0.x, y, ext0.z),
                    ]
                else:
                    pulvino = [
                        Point3D(x1, y, 0.0),
                        Point3D(int0.x, y, 0.0),
                        Point3D(ext0.x, y, ext0.z),
                        Point3D(x1, y, ext0.z),
                    ]
                self._quad(
                    pulvino,
                    span.material_pulvino_key,
                    self.spec.definition.corsias[0].width,
                    "CSharp_Pulvino",
                )

    # -- AddBridgeRow1 -------------------------------------------------------

    def _add_bridge_row(
        self,
        abscissa: Sequence[float],
        spans: Sequence[Span],
        y: float,
        corsia_width: float,
        heights: int,
    ) -> None:
        span_index = 0
        for index in range(len(abscissa) - 1):
            span = spans[span_index]
            if (index + 1) % 2 == 0:
                span_index += 1
            x1 = abscissa[index]
            x2 = abscissa[index + 1]
            is_right = bool(index % 2)
            vector_x = x1 if is_right else x2
            params = half_arch_params(
                vector_x,
                span.f,
                span.L,
                span.Tb,
                span.Tt,
                span.Adx if is_right else span.Asx,
                span.S1,
                span.S2,
                span.Dz,
            )
            params = EllipseParams(
                center=(params.center[0], y, params.center[2]),
                rx=params.rx,
                rz=params.rz,
                theta0=params.theta0,
                intrados_rx=params.intrados_rx,
                intrados_rz=params.intrados_rz,
                springing_drop=params.springing_drop,
                crown_point=(params.crown_point[0], y, params.crown_point[2]),
            )
            extrados_points, columns = self._add_semi_arch(
                span, params, x1, x2, y, is_right, heights
            )
            self._add_arch_ring(span, params, extrados_points, x1, x2, y, is_right)
            if is_right:
                span.discr_right = max(1, columns)
            else:
                span.discr_left = max(1, columns)

    # -- AddSpallePile -------------------------------------------------------

    def _add_pier_shafts(self, y: float, thickness: float) -> None:
        for element in self.spec.elements:
            if not isinstance(element, Pier) or element.H <= 0.0:
                continue
            centre = self._element_origin(element)
            # Verified case: Asx/Adx != 0 -> no springer segments in the
            # pier-top discretization; DiscrLeft/DiscrRight split b2.
            half = element.b2 / 2.0
            columns = [centre - half, centre, centre + half]
            rows = max(1, _arrotonda(element.H / self.spec.definition.nl))
            z_rows = [-element.H + r * element.H / rows for r in range(rows + 1)]
            for column in range(len(columns) - 1):
                for row in range(rows):
                    points = [
                        Point3D(columns[column], y, z_rows[row]),
                        Point3D(columns[column + 1], y, z_rows[row]),
                        Point3D(columns[column + 1], y, z_rows[row + 1]),
                        Point3D(columns[column], y, z_rows[row + 1]),
                    ]
                    self._quad(points, element.material_key, thickness, "CSharp_Pier")

    # -- public entry point --------------------------------------------------

    def mesh(self) -> CSharpBridgeMesh:
        abscissa = self._abscissa()
        if not abscissa:
            raise ValueError("bridge abscissa is empty")
        self._total_length = abscissa[-1]
        self._deck_z = max(
            self.spec.elevations.get_z(x, 1)
            for x in abscissa
        )
        spans = [element for element in self.spec.elements if isinstance(element, Span)]
        centres = self._strip_centres()
        for corsia, y in zip(self.spec.definition.corsias, centres):
            heights = 4 if corsia.height > 0.0 else 3
            self._add_bridge_row(abscissa, spans, y, corsia.width, heights)
        # C# AddSpallePile runs once after all transverse rows have been built.
        for corsia, y in zip(self.spec.definition.corsias, centres):
            self._add_pier_shafts(y, corsia.width)
        return CSharpBridgeMesh(
            spec=self.spec,
            nodes=self.nodes,
            quads=self.quads,
            deck_z=self._deck_z,
            total_length=self._total_length,
        )


def build_csharp_bridge_mesh(spec: CSharpBridgeSpec) -> CSharpBridgeMesh:
    return CSharpMesher(spec).mesh()
