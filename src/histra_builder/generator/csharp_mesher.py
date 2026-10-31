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
from .mesher import GeneratedQuad, MonitoringPoint, PierMetadata
from .restraints import GeneratedNodeC, GeneratedRestraint
from .csharp_discretize import (
    discretize_bottom_foundation_pileb2,
    discretize_bottom_pileb2,
    discretize_top_pileb2,
)
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
class GeneratedGeometryLineRestraint:
    """C# ``GeometryLineRestraint`` (foundation line support)."""

    key: int
    name: str
    node_key1: int
    node_key2: int
    b: float
    h: float = 30.0
    material_key: int = 0
    load_condition_key: int = 0
    zg: float = 0.0
    parent_key: int = 1
    parent_type: str = "Bridge"
    parent_edge: int = 0
    alignment: str = "Center"
    dy: float = 0.0
    mechanical_type: str = "Foundation"
    k: Tuple[float, ...] = (-1.0, -1.0, -1.0, -1.0, -1.0, -1.0)


@dataclass
class CSharpBridgeMesh:
    """Structural mesh produced by the C#-parity mesher."""

    spec: CSharpBridgeSpec
    nodes: Dict[int, Point3D]
    quads: Dict[int, GeneratedQuad]
    geometry_line_restraints: List[GeneratedGeometryLineRestraint]
    restraints: List[GeneratedRestraint]
    node_cs: List[GeneratedNodeC]
    monitoring_points: List[object]
    piers: List[PierMetadata]
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
        self._foundation_edges: List[Tuple[int, float, int, int, int, int]] = []
        self._next_glr_key = 1
        self._next_restraint_key = 1
        self._next_node_c_key = 1
        self._node_c_map: Dict[int, int] = {}
        self._glrs: List[GeneratedGeometryLineRestraint] = []
        self._restraints: List[GeneratedRestraint] = []
        self._node_cs: List[GeneratedNodeC] = []
        self._piers: List[PierMetadata] = []
        self._monitoring_points: List[MonitoringPoint] = []

    # -- geometric primitives -------------------------------------------------

    def _node(self, point) -> int:
        px, py, pz = _xyz(point)
        key = (round(px, 4), round(py, 4), round(pz, 4))
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
        group: str = "CSharp_Fill",
    ) -> List[GeneratedQuad]:
        created: List[GeneratedQuad] = []
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
                created.append(
                    self._quad(
                        [
                            _lerp(a[0], a[3], j / m),
                            _lerp(a[1], a[2], j / m),
                            _lerp(a[1], a[2], (j + 1) / m),
                            _lerp(a[0], a[3], (j + 1) / m),
                        ],
                        material_key,
                        thickness,
                        group,
                    )
                )
        return created

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
        hmuro: float = 0.0,
        fill_material_override: int = 0,
    ) -> Tuple[List[Point3D], int]:
        z1 = self.spec.elevations.get_z(x1, 1, hmuro)
        z2 = self.spec.elevations.get_z(x2, 1, hmuro)

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
        if fill_material_override > 0:
            fill_material = fill_material_override
        upper = [
            Point3D(extrados_points[0].x, y, self.spec.elevations.get_z(extrados_points[0].x, 1, hmuro)),
            Point3D(extrados_points[-1].x, y, self.spec.elevations.get_z(extrados_points[-1].x, 1, hmuro)),
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
            Point3D(extrados.x, y, self.spec.elevations.get_z(extrados.x, 1, hmuro)),
            Point3D(edge_x, y, self.spec.elevations.get_z(edge_x, 1, hmuro)),
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

        # Stack the remaining elevation layers as structured quad bands over
        # the same extrados columns.  This is the C# ``else``/flat-layer path;
        # curved transition triangles are a separate golden-dependent branch.
        columns = sorted({x1, x2, *(point.x for point in extrados_points)})
        for layer in range(2, heights + 1):
            layer_material, _, _ = self.spec.elevations.get_material_key(layer)
            if fill_material_override > 0:
                layer_material = fill_material_override
            for left_x, right_x in zip(columns, columns[1:]):
                width = right_x - left_x
                if abs(width) <= 1.0e-9:
                    continue
                bottom_left = self.spec.elevations.get_z(left_x, layer - 1, hmuro)
                bottom_right = self.spec.elevations.get_z(right_x, layer - 1, hmuro)
                top_left = self.spec.elevations.get_z(left_x, layer, hmuro)
                top_right = self.spec.elevations.get_z(right_x, layer, hmuro)
                if (
                    top_left - bottom_left <= 1.0e-9
                    or top_right - bottom_right <= 1.0e-9
                ):
                    continue
                points = [
                    Point3D(left_x, y, bottom_left),
                    Point3D(right_x, y, bottom_right),
                    Point3D(right_x, y, top_right),
                    Point3D(left_x, y, top_left),
                ]
                subdivisions = max(
                    1,
                    _arrotonda(abs(width) / self.spec.definition.nl),
                )
                self._add_mesh3(
                    points,
                    1,
                    subdivisions,
                    layer_material,
                    self.spec.definition.corsias[0].width,
                    False,
                    "CSharp_Fill",
                )

        # C# sets span.DiscrLeft/Right from Colonne.First().N.  In the
        # non-curved AddMesh4 branch each colonna is created with N=1.
        return extrados_points, 1

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
        foundation_owner: Optional[int] = None,
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
                suppress_pulvino = False
                if foundation_owner is not None:
                    owner = self.spec.elements[foundation_owner]
                    suppress_pulvino = (
                        isinstance(owner, Abutment) and owner.Hf > 0.0
                    )
                if suppress_pulvino:
                    continue
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
                pulvino_quad = self._quad(
                    pulvino,
                    span.material_pulvino_key,
                    self.spec.definition.corsias[0].width,
                    "CSharp_Pulvino",
                )
                if foundation_owner is not None:
                    owner = self.spec.elements[foundation_owner]
                    if (
                        getattr(owner, "H", 0.0) <= 0.0
                        and getattr(owner, "Hf", 0.0) <= 0.0
                    ):
                        left_key = self._node((pulvino[0].x, y, pulvino[0].z))
                        right_key = self._node((pulvino[1].x, y, pulvino[1].z))
                        self._record_foundation_edge(
                            foundation_owner,
                            y,
                            0,
                            pulvino_quad,
                            left_key,
                            right_key,
                        )

    # -- AddBridgeRow1 -------------------------------------------------------

    def _add_bridge_row(
        self,
        abscissa: Sequence[float],
        spans: Sequence[Span],
        y: float,
        corsia_width: float,
        heights: int,
        hmuro: float = 0.0,
        fill_material_override: int = 0,
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
                span, params, x1, x2, y, is_right, heights, hmuro,
                fill_material_override,
            )
            foundation_owner: Optional[int] = None
            if index == 0:
                foundation_owner = 0
            elif index == len(abscissa) - 2:
                foundation_owner = len(self.spec.elements) - 1
            self._add_arch_ring(
                span,
                params,
                extrados_points,
                x1,
                x2,
                y,
                is_right,
                foundation_owner,
            )
            if is_right:
                span.discr_right = max(1, columns)
            else:
                span.discr_left = max(1, columns)

    # -- AddSpallePile -------------------------------------------------------

    def _add_spalle_pile(self, centres: Sequence[float]) -> None:
        """Port of ``generatePilaSpalla`` + ``generateMasonryFoundation``."""
        for owner_index, element in enumerate(self.spec.elements):
            if not isinstance(element, (Abutment, Pier)):
                continue
            centre = self._element_origin(element)
            for corsia, y in zip(self.spec.definition.corsias, centres):
                thickness = corsia.width
                top = [centre + value for value in discretize_top_pileb2(self.spec.elements, owner_index)]
                bottom = [centre + value for value in discretize_bottom_pileb2(self.spec.elements, owner_index)]
                columns = len(top) - 1
                if element.H > 0.0 and columns > 0:
                    rows = max(0, _arrotonda(element.H / self.spec.definition.nl))
                    for column in range(columns):
                        points = [
                            Point3D(bottom[column], y, -element.H),
                            Point3D(bottom[column + 1], y, -element.H),
                            Point3D(top[column + 1], y, 0.0),
                            Point3D(top[column], y, 0.0),
                        ]
                        span_width = top[column + 1] - top[column]
                        cross = max(1, _arrotonda(abs(span_width) / self.spec.definition.nl))
                        created = self._add_mesh3(
                            points,
                            rows,
                            cross,
                            element.material_key,
                            thickness,
                            False,
                            "CSharp_Pier",
                        )
                        if element.Hf <= 0.0 and created:
                            self._record_foundation_edge(
                                owner_index,
                                y,
                                column,
                                created[0],
                                self._node(points[0]),
                                self._node(points[1]),
                            )

                if element.Hf > 0.0:
                    foundation_bottom = [
                        centre + value
                        for value in discretize_bottom_foundation_pileb2(
                            self.spec.elements, owner_index
                        )
                    ]
                    foundation_columns = len(foundation_bottom) - 1
                    rows = max(1, _arrotonda(element.Hf / self.spec.definition.nl))
                    for column in range(foundation_columns):
                        points = [
                            Point3D(foundation_bottom[column], y, -element.H - element.Hf),
                            Point3D(foundation_bottom[column + 1], y, -element.H - element.Hf),
                            Point3D(foundation_bottom[column + 1], y, -element.H),
                            Point3D(foundation_bottom[column], y, -element.H),
                        ]
                        cross = max(
                            1,
                            _arrotonda(
                                abs(foundation_bottom[column + 1] - foundation_bottom[column])
                                / self.spec.definition.nl
                            ),
                        )
                        created = self._add_mesh3(
                            points,
                            rows,
                            cross,
                            element.material_foundation_key,
                            thickness,
                            False,
                            "CSharp_Foundation",
                        )
                        if created:
                            self._record_foundation_edge(
                                owner_index,
                                y,
                                column,
                                created[0],
                                self._node(points[0]),
                                self._node(points[1]),
                            )

    def _default_model_point(self) -> None:
        """Port of ``ModelPointOperations.TryAddDefaultModelPoints``.

        C# selects the highest-Z structural node closest to the plan centre of
        all nodes at that elevation.
        """
        if not self.nodes:
            return
        z_max = max(point.z for point in self.nodes.values())
        top = [
            (key, point)
            for key, point in self.nodes.items()
            if abs(point.z - z_max) <= 1.0e-9
        ]
        if not top:
            return
        x_mid = (max(point.x for _, point in top) + min(point.x for _, point in top)) / 2.0
        y_mid = (max(point.y for _, point in top) + min(point.y for _, point in top)) / 2.0
        key, point = min(
            top,
            key=lambda item: (item[1].x - x_mid) ** 2 + (item[1].y - y_mid) ** 2,
        )
        self._monitoring_points.append(
            MonitoringPoint(
                key=1,
                element_key=key,
                element_type="Node",
                id_vertex=0,
                description=f"Point in ({{X:{point.x:g} Y:{point.y:g} Z:{point.z:g}}})",
                point=point,
            )
        )

    # -- foundation edge / GLR / Restraint generation -----------------------

    def _record_foundation_edge(
        self,
        owner_index: int,
        strip_y: float,
        sub_index: int,
        quad: GeneratedQuad,
        left_node: int,
        right_node: int,
    ) -> None:
        self._foundation_edges.append(
            (owner_index, strip_y, sub_index, quad.key, left_node, right_node)
        )

    def _foundation_tag(self, owner_index: int) -> str:
        element = self.spec.elements[owner_index]
        if isinstance(element, Pier):
            pier_number = sum(
                1
                for item in self.spec.elements[: owner_index + 1]
                if isinstance(item, Pier)
            )
            return f"pier_{pier_number}"
        if isinstance(element, Abutment):
            return "abutment_left" if element.kind == "Sinistra" else "abutment_right"
        return ""

    def _build_foundation_supports(self) -> None:
        """Port of ``generateMasonryFoundation`` for the verified Hf=0 case."""
        if not self._foundation_edges:
            return
        edges = sorted(
            self._foundation_edges,
            key=lambda item: (item[0], -item[1], item[2]),
        )
        for owner_index, strip_y, _sub, quad_key, left_key, right_key in edges:
            left = self.nodes[left_key]
            right = self.nodes[right_key]
            if right.x < left.x:
                left_key, right_key = right_key, left_key
                left, right = right, left
            strip_width = self._find_strip_width(strip_y)
            glr_key = self._next_glr_key
            self._next_glr_key += 1
            glr = GeneratedGeometryLineRestraint(
                key=glr_key,
                name=str(glr_key),
                node_key1=right_key,
                node_key2=left_key,
                b=strip_width,
            )
            self._glrs.append(glr)

            nc_left = self._node_c(left_key)
            nc_right = self._node_c(right_key)
            half = strip_width / 2.0
            point1 = Point3D(left.x, strip_y - half, left.z)
            point2 = Point3D(right.x, strip_y - half, right.z)
            point3 = Point3D(right.x, strip_y + half, right.z)
            point4 = Point3D(left.x, strip_y + half, left.z)
            restraint = GeneratedRestraint(
                key=self._next_restraint_key,
                name=str(self._next_restraint_key),
                node_key1=left_key,
                node_key2=right_key,
                node_c_key1=nc_left,
                node_c_key2=nc_right,
                computational_element_key=quad_key,
                computational_element_type="Quad",
                computational_element_edge=0,
                material_key=0,
                parent_key=glr_key,
                parent_type_element="GeometryLineRestraint",
                k=(-1.0, -1.0, -1.0, -1.0, -1.0, -1.0),
                g=Point3D((left.x + right.x) / 2.0, strip_y, left.z),
                point1=point1,
                point2=point2,
                point3=point3,
                point4=point4,
                foundation_tag=self._foundation_tag(owner_index),
            )
            self._next_restraint_key += 1
            self._restraints.append(restraint)

    def _find_strip_width(self, strip_y: float) -> float:
        centres = self._strip_centres()
        for corsia, centre in zip(self.spec.definition.corsias, centres):
            if abs(centre - strip_y) < 1.0e-6:
                return corsia.width
        return self.spec.definition.corsias[0].width

    def _node_c(self, node_key: int) -> int:
        existing = self._node_c_map.get(node_key)
        if existing is not None:
            return existing
        key = self._next_node_c_key
        self._next_node_c_key += 1
        self._node_c_map[node_key] = key
        self._node_cs.append(GeneratedNodeC(key=key, node_key=node_key))
        return key

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
            self._add_bridge_row(
                abscissa,
                spans,
                y,
                corsia.width,
                heights,
                corsia.height,
                corsia.material_key,
            )
        # C# AddSpallePile runs once after all transverse rows have been built.
        self._add_spalle_pile(centres)
        self._build_foundation_supports()
        self._default_model_point()
        for index, element in enumerate(self.spec.piers, start=1):
            centre = self._element_origin(element)
            self._piers.append(
                PierMetadata(
                    id=f"pier_{index}",
                    index=index,
                    origin=Point3D(centre, 0.0, 0.0),
                    x_start=centre - element.b2 / 2.0,
                    x_end=centre + element.b2 / 2.0,
                    restraint_keys=[],
                )
            )
        return CSharpBridgeMesh(
            spec=self.spec,
            nodes=self.nodes,
            quads=self.quads,
            geometry_line_restraints=self._glrs,
            restraints=self._restraints,
            node_cs=self._node_cs,
            monitoring_points=self._monitoring_points,
            piers=self._piers,
            deck_z=self._deck_z,
            total_length=self._total_length,
        )


def build_csharp_bridge_mesh(spec: CSharpBridgeSpec) -> CSharpBridgeMesh:
    return CSharpMesher(spec).mesh()
