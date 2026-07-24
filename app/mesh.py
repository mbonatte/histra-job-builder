from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

from lxml import etree

from .schemas import MeshPatch
from .xml_utils import (
    EPS,
    attr_bool,
    attr_float,
    attr_text,
    direct_children,
    first_direct,
    parse_vector,
    sorted_unique,
)

Point = list[float]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def distance3d(a: Point, b: Point) -> float:
    return math.dist(a, b)


def _signed_area_xz(points: Sequence[Point]) -> float:
    return 0.5 * sum(
        points[i][0] * points[(i + 1) % 4][2]
        - points[(i + 1) % 4][0] * points[i][2]
        for i in range(4)
    )


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0])


def _segments_cross(a: Point, b: Point, c: Point, d: Point, tolerance: float) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    return (
        ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance))
        and ((o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance))
    )


@dataclass
class Node:
    key: int
    point: Point

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "point": self.point}


@dataclass
class Quad:
    key: int
    node_keys: list[int]
    material_key: str
    layer_key: int
    parent_key: int
    parent_type_element: str
    thickness: float
    group: str
    source_index: Optional[int] = None
    transverse_band_index: Optional[int] = None
    transverse_band_name: Optional[str] = None
    transverse_role: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "nodeKeys": self.node_keys,
            "materialKey": self.material_key,
            "layerKey": self.layer_key,
            "parentKey": self.parent_key,
            "parentTypeElement": self.parent_type_element,
            "thickness": self.thickness,
            "group": self.group,
            "sourceIndex": self.source_index,
            "transverseBandIndex": self.transverse_band_index,
            "transverseBandName": self.transverse_band_name,
            "transverseRole": self.transverse_role,
        }


@dataclass
class Mesh:
    nodes: list[Node]
    quads: list[Quad]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.as_dict() for node in self.nodes],
            "quads": [quad.as_dict() for quad in self.quads],
            "metadata": self.metadata,
        }


class MeshBuilder:
    def __init__(self, tolerance: float = 1e-5, parent_key: int = 1):
        self.tolerance = tolerance
        self.parent_key = parent_key
        self.nodes: list[Node] = []
        self.quads: list[Quad] = []
        self._node_map: dict[tuple[int, int, int], int] = {}

    def _node_hash(self, point: Point) -> tuple[int, int, int]:
        return tuple(round(float(value) / self.tolerance) for value in point)  # type: ignore[return-value]

    def add_node(self, point: Point) -> int:
        normalized = [float(point[0]), float(point[1] if len(point) > 1 else 0), float(point[2])]
        node_hash = self._node_hash(normalized)
        existing = self._node_map.get(node_hash)
        if existing is not None:
            return existing
        key = len(self.nodes) + 1
        self._node_map[node_hash] = key
        self.nodes.append(Node(key=key, point=normalized))
        return key

    def _validate_quad_points(self, points: list[Point], group: str) -> None:
        if any(not math.isfinite(value) for point in points for value in point):
            raise ValueError(f"{group}: quad contains a non-finite coordinate")
        hashes = {self._node_hash(point) for point in points}
        if len(hashes) != 4:
            raise ValueError(f"{group}: quad has repeated vertices")
        minimum_edge = max(self.tolerance * 0.25, 1e-10)
        if any(distance3d(points[i], points[(i + 1) % 4]) <= minimum_edge for i in range(4)):
            raise ValueError(f"{group}: quad has a zero-length edge")
        area = abs(_signed_area_xz(points))
        if area <= max(self.tolerance * self.tolerance, 1e-12):
            raise ValueError(f"{group}: quad has zero projected area")
        tolerance = max(self.tolerance * self.tolerance, 1e-12)
        if _segments_cross(points[0], points[1], points[2], points[3], tolerance) or _segments_cross(
            points[1], points[2], points[3], points[0], tolerance
        ):
            raise ValueError(f"{group}: quad is self-intersecting")

    def add_quad(self, points: list[Point], **metadata: Any) -> int:
        if len(points) != 4:
            raise ValueError("A quad must contain exactly four points")
        normalized = [[float(p[0]), float(p[1]), float(p[2])] for p in points]
        group = str(metadata.get("group", "mesh"))
        self._validate_quad_points(normalized, group)
        node_keys = [self.add_node(point) for point in normalized]
        key = len(self.quads) + 1
        self.quads.append(
            Quad(
                key=key,
                node_keys=node_keys,
                material_key=str(metadata.get("material_key", "0")),
                layer_key=int(metadata.get("layer_key", 1)),
                parent_key=int(metadata.get("parent_key", self.parent_key)),
                parent_type_element=str(metadata.get("parent_type_element", "Bridge")),
                thickness=float(metadata.get("thickness", 1)),
                group=group,
                source_index=metadata.get("source_index"),
                transverse_band_index=metadata.get("transverse_band_index"),
                transverse_band_name=metadata.get("transverse_band_name"),
                transverse_role=metadata.get("transverse_role"),
            )
        )
        return key


@dataclass(eq=False)
class Support:
    type: str
    element: etree._Element
    sequence_index: int
    origin: Point
    center_x: float
    center_y: float
    left_x: float
    right_x: float
    width_x: float
    width_y: float
    is_left: Optional[bool] = None


@dataclass
class TransverseBand:
    index: int
    key: str
    name: str
    description: str
    y_min: float
    y_max: float
    y: float
    thickness: float
    material_key: str
    role: str
    height: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "yMin": self.y_min,
            "yMax": self.y_max,
            "y": self.y,
            "thickness": self.thickness,
            "materialKey": self.material_key,
            "role": self.role,
            "height": self.height,
        }


@dataclass
class ElevationProfile:
    samples: list[dict[str, float]]

    def component_at(self, x: float, index: int) -> float:
        key = f"h{index + 1}"
        if len(self.samples) == 1:
            return self.samples[0][key]
        if x <= self.samples[0]["x"]:
            return self.samples[0][key]
        if x >= self.samples[-1]["x"]:
            return self.samples[-1][key]
        for a, b in zip(self.samples, self.samples[1:]):
            if a["x"] <= x <= b["x"]:
                dx = b["x"] - a["x"]
                t = 0.0 if abs(dx) < EPS else (x - a["x"]) / dx
                return lerp(a[key], b[key], t)
        return self.samples[-1][key]

    def cumulative_at(self, x: float, count: int) -> float:
        return sum(self.component_at(x, index) for index in range(max(0, min(count, 3))))

    def maximum_component(self, index: int) -> float:
        return max(sample[f"h{index + 1}"] for sample in self.samples)


@dataclass
class BackfillLayer:
    source_index: int
    tag: str
    material_key: str
    material_key_2: str
    enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "sourceIndex": self.source_index,
            "tag": self.tag,
            "materialKey": self.material_key,
            "materialKey2": self.material_key_2,
            "enabled": self.enabled,
        }


@dataclass
class SpanRecord:
    element: etree._Element
    sequence_index: int
    index: int
    left_support: Support
    right_support: Support
    x_start: float = 0.0
    x_end: float = 0.0
    radius: float = 0.0
    center_x: float = 0.0
    center_z: float = 0.0
    spring_z: float = 0.0
    angle_start: float = 0.0
    angle_end: float = 0.0
    angle_values: list[float] = field(default_factory=list)
    arc_divisions: int = 0
    radial_divisions: int = 0
    curves: list[list[Point]] = field(default_factory=list)
    inner_curve: list[Point] = field(default_factory=list)
    outer_curve: list[Point] = field(default_factory=list)
    outer_left: Point = field(default_factory=list)
    outer_right: Point = field(default_factory=list)
    spring_thickness: float = 0.0
    crown_thickness: float = 0.0


@dataclass
class MeshContext:
    max_length: float
    elevation_profile: ElevationProfile
    backfill_layers: list[BackfillLayer]
    bridge_width: float
    deck_bands: list[TransverseBand]
    deck_internal_boundaries: list[float]
    parent_key: int
    warnings: list[str]
    arc_division_mode: str
    arc_division_override: Optional[int]
    arc_minimum: int


class PolylineFunction:
    def __init__(self, points: Sequence[Point]):
        self.points = sorted(([float(p[0]), float(p[1]), float(p[2])] for p in points), key=lambda p: p[0])

    def at(self, x: float) -> float:
        if x <= self.points[0][0]:
            return self.points[0][2]
        if x >= self.points[-1][0]:
            return self.points[-1][2]
        for a, b in zip(self.points, self.points[1:]):
            if a[0] - EPS <= x <= b[0] + EPS:
                dx = b[0] - a[0]
                t = 0.0 if abs(dx) < EPS else (x - a[0]) / dx
                return lerp(a[2], b[2], t)
        return self.points[-1][2]


def support_from_element(element: etree._Element, sequence_index: int) -> Support:
    reference = first_direct(element, "ReferenceSystem")
    origin_x, origin_y, origin_z = parse_vector(reference.get("Origin") if reference is not None else None)
    b2 = attr_float(element, "b2")
    if element.tag == "Pier":
        return Support(
            type="Pier",
            element=element,
            sequence_index=sequence_index,
            origin=[origin_x, origin_y, origin_z],
            center_x=origin_x,
            center_y=origin_y,
            left_x=origin_x - b2 / 2,
            right_x=origin_x + b2 / 2,
            width_x=b2,
            width_y=attr_float(element, "w2"),
        )
    kind = attr_text(element, "AbutmentKind").lower()
    is_left = "sinistra" in kind or "left" in kind
    return Support(
        type="Abutment",
        element=element,
        sequence_index=sequence_index,
        origin=[origin_x, origin_y, origin_z],
        center_x=origin_x,
        center_y=origin_y,
        left_x=origin_x if is_left else origin_x - b2,
        right_x=origin_x + b2 if is_left else origin_x,
        width_x=b2,
        width_y=attr_float(element, "w2"),
        is_left=is_left,
    )


def make_elevation_profile(wizard: etree._Element, warnings: list[str]) -> ElevationProfile:
    elevations_root = first_direct(wizard, "Elevations")
    elevation_list = first_direct(elevations_root, "Elevations")
    samples = [
        {
            "x": attr_float(item, "X"),
            "h1": max(0.0, attr_float(item, "H1")),
            "h2": max(0.0, attr_float(item, "H2")),
            "h3": max(0.0, attr_float(item, "H3")),
        }
        for item in direct_children(elevation_list, "Elevation")
    ]
    samples.sort(key=lambda item: item["x"])
    if not samples:
        warnings.append("No Elevations/Elevation values were found; backfill elevations default to 0")
        samples = [{"x": 0.0, "h1": 0.0, "h2": 0.0, "h3": 0.0}]
    if len(samples) > 1:
        warnings.append("Variable H1/H2/H3 elevations use piecewise-linear interpolation")
    return ElevationProfile(samples=samples)


def make_backfill_layers(wizard: etree._Element, profile: ElevationProfile, warnings: list[str]) -> list[BackfillLayer]:
    elevations_root = first_direct(wizard, "Elevations")
    layers: list[BackfillLayer] = []
    for index in range(3):
        element = first_direct(elevations_root, f"Layer{index + 1}")
        thickness_present = profile.maximum_component(index) > EPS
        if element is None:
            if index == 0 and thickness_present:
                warnings.append("Elevations/Layer1 is missing; its material defaults to 0")
            layers.append(
                BackfillLayer(
                    source_index=index,
                    tag=f"Layer{index + 1}",
                    material_key="0",
                    material_key_2="0",
                    enabled=thickness_present,
                )
            )
            continue
        enabled = attr_bool(element, "GenerateComputationalElements", True) and thickness_present
        layers.append(
            BackfillLayer(
                source_index=index,
                tag=f"Layer{index + 1}",
                material_key=attr_text(element, "MaterialKey", "0"),
                material_key_2=attr_text(element, "MaterialKey2", attr_text(element, "MaterialKey", "0")),
                enabled=enabled,
            )
        )
    active = [layer for layer in layers if layer.enabled]
    if not active:
        warnings.append("No positive, enabled backfill layer was found")
    return active


def make_deck_bands(bridge: etree._Element, warnings: list[str]) -> tuple[list[TransverseBand], list[float], float, float]:
    bridge_origin = parse_vector(bridge.get("Origin"))
    declared_width = attr_float(bridge, "Width", 1.0)
    lane_root = first_direct(bridge, "Corsie")
    lanes = direct_children(lane_root, "Corsia")
    if not lanes:
        band = TransverseBand(
            index=0,
            key="0",
            name="Deck",
            description="Whole bridge width",
            y_min=bridge_origin[1] - declared_width / 2,
            y_max=bridge_origin[1] + declared_width / 2,
            y=bridge_origin[1],
            thickness=declared_width,
            material_key="0",
            role="deck",
            height=0.0,
        )
        return [band], [], declared_width, bridge_origin[1]

    total = sum(attr_float(lane, "Width") for lane in lanes)
    width = total if total > EPS else declared_width
    if abs(width - declared_width) > 1e-3:
        warnings.append(
            f"Lane widths sum to {width}, while BridgeDefinition.Width is {declared_width}; "
            "lane widths were preserved and centred on the bridge origin"
        )
    cursor = bridge_origin[1] - width / 2
    boundaries = [cursor]
    bands: list[TransverseBand] = []
    for index, lane in enumerate(lanes):
        lane_width = attr_float(lane, "Width")
        y_min = cursor
        y_max = cursor + lane_width
        cursor = y_max
        boundaries.append(cursor)
        bands.append(
            TransverseBand(
                index=index,
                key=attr_text(lane, "Key", str(index)),
                name=attr_text(lane, "Name", f"Lane {index + 1}"),
                description=attr_text(lane, "Description"),
                y_min=y_min,
                y_max=y_max,
                y=(y_min + y_max) / 2,
                thickness=lane_width,
                material_key=attr_text(lane, "MaterialKey", "0"),
                role="deck",
                height=max(0.0, attr_float(lane, "Height")),
            )
        )
    return bands, boundaries[1:-1], width, bridge_origin[1]


def make_component_bands_from_bounds(
    *,
    y_min: float,
    y_max: float,
    internal_boundaries: Iterable[float] = (),
    forced_boundaries: Iterable[float] = (),
    role: str,
) -> list[TransverseBand]:
    if y_max - y_min <= EPS:
        return []
    candidates = [y_min, *internal_boundaries, *forced_boundaries, y_max]
    boundaries = sorted_unique(value for value in candidates if y_min - EPS <= value <= y_max + EPS)
    bands: list[TransverseBand] = []
    for index, (lower, upper) in enumerate(zip(boundaries, boundaries[1:])):
        if upper - lower <= EPS:
            continue
        bands.append(
            TransverseBand(
                index=index,
                key=f"{role}-{index}",
                name=f"{role} {index + 1}",
                description=role,
                y_min=lower,
                y_max=upper,
                y=(lower + upper) / 2,
                thickness=upper - lower,
                material_key="0",
                role=role,
            )
        )
    return bands


def make_component_bands(
    *,
    center_y: float,
    width: float,
    internal_boundaries: Iterable[float] = (),
    left_extra: float = 0.0,
    right_extra: float = 0.0,
    forced_boundaries: Iterable[float] = (),
    role: str,
) -> list[TransverseBand]:
    return make_component_bands_from_bounds(
        y_min=center_y - width / 2 - max(0.0, left_extra),
        y_max=center_y + width / 2 + max(0.0, right_extra),
        internal_boundaries=internal_boundaries,
        forced_boundaries=forced_boundaries,
        role=role,
    )


def fill_material_for_band(band: TransverseBand, default_key: str) -> str:
    return default_key if str(band.material_key or "0") == "0" else str(band.material_key)


def subdivide_interval(start: float, end: float, max_length: float, forced_points: Iterable[float] = ()) -> list[float]:
    low, high = min(start, end), max(start, end)
    points = sorted_unique([low, *(value for value in forced_points if low + EPS < value < high - EPS), high])
    result = [points[0]]
    for a, b in zip(points, points[1:]):
        count = max(1, math.ceil(abs(b - a) / max_length))
        result.extend(lerp(a, b, step / count) for step in range(1, count + 1))
    return result if start <= end else list(reversed(result))


def _bisect_root(function: Callable[[float], float], a: float, b: float) -> float:
    fa, fb = function(a), function(b)
    if abs(fa) <= 1e-9:
        return a
    if abs(fb) <= 1e-9:
        return b
    for _ in range(60):
        mid = (a + b) / 2
        fm = function(mid)
        if abs(fm) <= 1e-9:
            return mid
        if fa * fm <= 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return (a + b) / 2


def refine_with_roots(
    x_coordinates: Sequence[float],
    functions: Iterable[Callable[[float], float]],
) -> list[float]:
    values = list(x_coordinates)
    roots: list[float] = []
    for a, b in zip(values, values[1:]):
        for function in functions:
            fa, fb = function(a), function(b)
            if abs(fa) <= 1e-8:
                roots.append(a)
            if abs(fb) <= 1e-8:
                roots.append(b)
            if fa * fb < 0:
                roots.append(_bisect_root(function, a, b))
    return sorted_unique([*values, *roots])


def _local_arch_thickness(element: etree._Element, angle: float, angle_start: float, angle_end: float) -> float:
    spring = attr_float(element, "Tb")
    crown = attr_float(element, "Tt", spring)
    center = (angle_start + angle_end) / 2
    half = max(abs(angle_end - angle_start) / 2, EPS)
    crown_weight = max(0.0, 1.0 - abs(angle - center) / half)
    return lerp(spring, crown, crown_weight)


def _arc_point(
    *,
    center_x: float,
    center_z: float,
    radius: float,
    element: etree._Element,
    angle: float,
    angle_start: float,
    angle_end: float,
    radial_fraction: float,
) -> Point:
    local_thickness = _local_arch_thickness(element, angle, angle_start, angle_end)
    current_radius = radius + local_thickness * radial_fraction
    return [
        center_x + current_radius * math.cos(angle),
        0.0,
        center_z + current_radius * math.sin(angle),
    ]


def _arc_length_between(
    *,
    center_x: float,
    center_z: float,
    radius: float,
    element: etree._Element,
    angle_start: float,
    angle_end: float,
    full_start: float,
    full_end: float,
) -> float:
    count = 24
    points = [
        _arc_point(
            center_x=center_x,
            center_z=center_z,
            radius=radius,
            element=element,
            angle=lerp(angle_start, angle_end, index / count),
            angle_start=full_start,
            angle_end=full_end,
            radial_fraction=1.0,
        )
        for index in range(count + 1)
    ]
    return sum(distance3d(a, b) for a, b in zip(points, points[1:]))


def _forced_arch_angles(
    *,
    context: MeshContext,
    element: etree._Element,
    center_x: float,
    center_z: float,
    radius: float,
    angle_start: float,
    angle_end: float,
) -> list[float]:
    values = [angle_start, (angle_start + angle_end) / 2, angle_end]
    layer_boundaries = [layer.source_index + 1 for layer in context.backfill_layers]
    # The final top boundary does not affect the arch/fill transition.  Internal
    # cumulative boundaries do, and HiStrA inserts radial nodes at these crossings.
    if layer_boundaries:
        layer_boundaries = layer_boundaries[:-1]
    for boundary_count in layer_boundaries:
        def difference(angle: float) -> float:
            point = _arc_point(
                center_x=center_x,
                center_z=center_z,
                radius=radius,
                element=element,
                angle=angle,
                angle_start=angle_start,
                angle_end=angle_end,
                radial_fraction=1.0,
            )
            return point[2] - context.elevation_profile.cumulative_at(point[0], boundary_count)

        samples = 240
        angles = [lerp(angle_start, angle_end, index / samples) for index in range(samples + 1)]
        previous_angle, previous_value = angles[0], difference(angles[0])
        for angle in angles[1:]:
            value = difference(angle)
            if previous_value * value < 0:
                values.append(_bisect_root(difference, previous_angle, angle))
            elif abs(value) <= 1e-8:
                values.append(angle)
            previous_angle, previous_value = angle, value
    return sorted_unique(values, tolerance=1e-8)


def _allocate_arc_counts(
    intervals: list[tuple[float, float, float]],
    *,
    max_length: float,
    minimum_per_half: int,
    crown: float,
    override: Optional[int],
) -> list[int]:
    if override is not None and override > 0:
        total_length = sum(length for _, _, length in intervals)
        raw = [max(1, round(override * length / max(total_length, EPS))) for _, _, length in intervals]
        while sum(raw) < override:
            index = max(range(len(raw)), key=lambda i: intervals[i][2] / raw[i])
            raw[index] += 1
        while sum(raw) > override and any(value > 1 for value in raw):
            index = max((i for i, value in enumerate(raw) if value > 1), key=lambda i: raw[i])
            raw[index] -= 1
        return raw

    counts = [max(1, round(length / max_length)) for _, _, length in intervals]
    for side in ("left", "right"):
        indices = [
            index
            for index, (a, b, _length) in enumerate(intervals)
            if (b <= crown + 1e-8 if side == "left" else a >= crown - 1e-8)
        ]
        while sum(counts[index] for index in indices) < minimum_per_half and indices:
            index = max(indices, key=lambda i: intervals[i][2] / counts[i])
            counts[index] += 1
    return counts


def compute_span_geometry(record: SpanRecord, context: MeshContext) -> SpanRecord:
    element = record.element
    x_start = record.left_support.right_x
    x_end = record.right_support.left_x
    actual_length = x_end - x_start
    declared_length = attr_float(element, "L", actual_length)
    rise = attr_float(element, "f")
    spring_thickness = attr_float(element, "Tb")
    crown_thickness = attr_float(element, "Tt", spring_thickness)
    dz = attr_float(element, "Dz")
    if actual_length <= 0:
        raise ValueError(f"Span {record.index + 1} has a non-positive support-to-support length")
    if rise <= 0:
        raise ValueError(f"Span {record.index + 1} has a non-positive rise")
    if spring_thickness <= 0 or crown_thickness <= 0:
        raise ValueError(f"Span {record.index + 1} has a non-positive ring thickness")
    if abs(declared_length - actual_length) > 1e-3:
        context.warnings.append(
            f"Span {record.index + 1}: declared L={declared_length} differs from support geometry "
            f"{actual_length}; support geometry was used"
        )
    if abs(record.left_support.origin[2] - record.right_support.origin[2]) > 1e-6:
        context.warnings.append(f"Span {record.index + 1}: unequal support elevations use one horizontal spring line")
    if attr_bool(element, "IsChkAdvancedMode"):
        context.warnings.append(f"Span {record.index + 1}: advanced mode is approximated from L/f/Tb/Tt/Dz")
    if not attr_bool(element, "Circolare", True):
        # In HiStrA bridge WizardData this flag can be false while the generated
        # geometry is still the L/f circular segment (as in Model1).  Advanced
        # shape fields take precedence when they are enabled; otherwise the
        # circular segment is the observed behavior.
        context.warnings.append(
            f"Span {record.index + 1}: Circolare=false but no active advanced geometry was found; "
            "the observed circular L/f construction was used"
        )
    if abs(crown_thickness - spring_thickness) > 1e-6:
        context.warnings.append(
            f"Span {record.index + 1}: ring thickness varies from Tb={spring_thickness} "
            f"at the springs to Tt={crown_thickness} at the crown"
        )

    radius = actual_length**2 / (8 * rise) + rise / 2
    center_x = (x_start + x_end) / 2
    spring_z = (record.left_support.origin[2] + record.right_support.origin[2]) / 2 + dz
    center_z = spring_z + rise - radius
    angle_start = math.atan2(spring_z - center_z, x_start - center_x)
    angle_end = math.atan2(spring_z - center_z, x_end - center_x)
    if angle_start > angle_end:
        angle_start, angle_end = angle_end, angle_start

    forced = _forced_arch_angles(
        context=context,
        element=element,
        center_x=center_x,
        center_z=center_z,
        radius=radius,
        angle_start=angle_start,
        angle_end=angle_end,
    )
    intervals: list[tuple[float, float, float]] = []
    for a, b in zip(forced, forced[1:]):
        length = _arc_length_between(
            center_x=center_x,
            center_z=center_z,
            radius=radius,
            element=element,
            angle_start=a,
            angle_end=b,
            full_start=angle_start,
            full_end=angle_end,
        )
        intervals.append((a, b, length))
    counts = _allocate_arc_counts(
        intervals,
        max_length=context.max_length,
        minimum_per_half=max(1, context.arc_minimum),
        crown=(angle_start + angle_end) / 2,
        override=context.arc_division_override,
    )
    angle_values = [intervals[0][0]]
    for (a, b, _length), count in zip(intervals, counts):
        angle_values.extend(lerp(a, b, index / count) for index in range(1, count + 1))
    angle_values = sorted_unique(angle_values, tolerance=1e-9)
    # Keep every span curve ordered from the left support to the right support.
    first_x = center_x + radius * math.cos(angle_values[0])
    last_x = center_x + radius * math.cos(angle_values[-1])
    if first_x > last_x:
        angle_values.reverse()

    radial_divisions = max(1, math.ceil(max(spring_thickness, crown_thickness) / context.max_length))
    curves: list[list[Point]] = []
    for radial in range(radial_divisions + 1):
        fraction = radial / radial_divisions
        curves.append(
            [
                _arc_point(
                    center_x=center_x,
                    center_z=center_z,
                    radius=radius,
                    element=element,
                    angle=angle,
                    angle_start=angle_start,
                    angle_end=angle_end,
                    radial_fraction=fraction,
                )
                for angle in angle_values
            ]
        )

    record.x_start = x_start
    record.x_end = x_end
    record.radius = radius
    record.center_x = center_x
    record.center_z = center_z
    record.spring_z = spring_z
    record.angle_start = angle_start
    record.angle_end = angle_end
    record.angle_values = angle_values
    record.arc_divisions = len(angle_values) - 1
    record.radial_divisions = radial_divisions
    record.curves = curves
    record.inner_curve = curves[0]
    record.outer_curve = curves[-1]
    record.outer_left = curves[-1][0]
    record.outer_right = curves[-1][-1]
    record.spring_thickness = spring_thickness
    record.crown_thickness = crown_thickness
    return record


def _layer_material(layer: BackfillLayer, band: TransverseBand) -> str:
    return fill_material_for_band(band, layer.material_key)


def _add_wedge_quad(
    builder: MeshBuilder,
    *,
    x0: float,
    x1: float,
    y: float,
    bottom0: float,
    bottom1: float,
    top0: float,
    top1: float,
    depth0: float,
    depth1: float,
    metadata: dict[str, Any],
) -> None:
    if depth0 <= EPS and depth1 <= EPS:
        return
    if depth0 <= EPS:
        midpoint = [(x0 + x1) / 2, y, (top0 + top1) / 2]
        points = [
            [x0, y, bottom0],
            [x1, y, bottom1],
            [x1, y, top1],
            midpoint,
        ]
    else:
        midpoint = [(x0 + x1) / 2, y, (top0 + top1) / 2]
        points = [
            [x0, y, bottom0],
            [x1, y, bottom1],
            midpoint,
            [x0, y, top0],
        ]
    builder.add_quad(points, **metadata)


def generate_layered_strip(
    builder: MeshBuilder,
    *,
    x_coordinates: list[float],
    bottom_at: Callable[[float], float],
    band: TransverseBand,
    context: MeshContext,
    group: str,
    source_index: Optional[int] = None,
) -> None:
    if len(x_coordinates) < 2 or not context.backfill_layers:
        return
    active_layers = context.backfill_layers
    last_source_index = active_layers[-1].source_index
    for layer in active_layers:
        lower_count = layer.source_index
        upper_count = layer.source_index + 1

        def lower_at(x: float) -> float:
            return context.elevation_profile.cumulative_at(x, lower_count)

        def upper_at(x: float) -> float:
            extra = band.height if layer.source_index == last_source_index else 0.0
            return context.elevation_profile.cumulative_at(x, upper_count) + extra

        def actual_bottom(x: float) -> float:
            return max(bottom_at(x), lower_at(x))

        roots = [
            lambda x, upper_at=upper_at: upper_at(x) - bottom_at(x),
            lambda x, lower_at=lower_at: lower_at(x) - bottom_at(x),
        ]
        xs = refine_with_roots(x_coordinates, roots)
        sample_x = sorted_unique([*xs, *((a + b) / 2 for a, b in zip(xs, xs[1:]))])
        maximum_depth = max((upper_at(x) - actual_bottom(x) for x in sample_x), default=0.0)
        if maximum_depth <= EPS:
            continue
        vertical_divisions = max(1, math.ceil(maximum_depth / context.max_length))
        metadata = {
            "material_key": _layer_material(layer, band),
            "layer_key": 1,
            "thickness": band.thickness,
            "group": f"{group}-{layer.tag.lower()}",
            "source_index": source_index,
            "transverse_band_index": band.index,
            "transverse_band_name": band.name,
            "transverse_role": band.role,
        }
        for x0, x1 in zip(xs, xs[1:]):
            bottom0, bottom1 = actual_bottom(x0), actual_bottom(x1)
            top0, top1 = upper_at(x0), upper_at(x1)
            depth0, depth1 = top0 - bottom0, top1 - bottom1
            if depth0 <= EPS and depth1 <= EPS:
                continue
            if depth0 <= EPS or depth1 <= EPS:
                _add_wedge_quad(
                    builder,
                    x0=x0,
                    x1=x1,
                    y=band.y,
                    bottom0=bottom0,
                    bottom1=bottom1,
                    top0=top0,
                    top1=top1,
                    depth0=depth0,
                    depth1=depth1,
                    metadata=metadata,
                )
                continue
            for iz in range(vertical_divisions):
                t0, t1 = iz / vertical_divisions, (iz + 1) / vertical_divisions
                builder.add_quad(
                    [
                        [x0, band.y, lerp(bottom0, top0, t0)],
                        [x1, band.y, lerp(bottom1, top1, t0)],
                        [x1, band.y, lerp(bottom1, top1, t1)],
                        [x0, band.y, lerp(bottom0, top0, t1)],
                    ],
                    **metadata,
                )


def generate_span_for_band(builder: MeshBuilder, span: SpanRecord, band: TransverseBand, context: MeshContext) -> None:
    curves = [[[x, band.y, z] for x, _, z in curve] for curve in span.curves]
    for radial in range(span.radial_divisions):
        inner, outer = curves[radial], curves[radial + 1]
        for index in range(span.arc_divisions):
            builder.add_quad(
                [outer[index], inner[index], inner[index + 1], outer[index + 1]],
                material_key=attr_text(span.element, "MaterialKey", "0"),
                layer_key=0,
                thickness=band.thickness,
                group=f"span-{span.index + 1}-arch",
                source_index=span.index,
                transverse_band_index=band.index,
                transverse_band_name=band.name,
                transverse_role=band.role,
            )
    outer = [[x, band.y, z] for x, _, z in span.outer_curve]
    bottom = PolylineFunction(outer)
    generate_layered_strip(
        builder,
        x_coordinates=[point[0] for point in outer],
        bottom_at=bottom.at,
        band=band,
        context=context,
        group=f"span-{span.index + 1}-fill",
        source_index=span.index,
    )


def _try_add_quad(builder: MeshBuilder, points: list[Point], **metadata: Any) -> bool:
    try:
        builder.add_quad(points, **metadata)
        return True
    except ValueError as error:
        if "zero projected area" in str(error) or "repeated vertices" in str(error):
            return False
        raise


def _generate_abutment_body(builder: MeshBuilder, support: Support, context: MeshContext) -> None:
    element = support.element
    height = attr_float(element, "H")
    if height <= EPS:
        return
    body_bands = make_component_bands(
        center_y=support.center_y,
        width=attr_float(element, "w2", context.bridge_width),
        internal_boundaries=context.deck_internal_boundaries,
        role="abutment",
    )
    x_body = subdivide_interval(support.left_x, support.right_x, context.max_length)
    z_top = support.origin[2]
    z_body = subdivide_interval(z_top - height, z_top, context.max_length)
    for band in body_bands:
        for ix in range(len(x_body) - 1):
            for iz in range(len(z_body) - 1):
                builder.add_quad(
                    [
                        [x_body[ix], band.y, z_body[iz]],
                        [x_body[ix + 1], band.y, z_body[iz]],
                        [x_body[ix + 1], band.y, z_body[iz + 1]],
                        [x_body[ix], band.y, z_body[iz + 1]],
                    ],
                    material_key=attr_text(element, "MaterialKey", "0"),
                    layer_key=1,
                    thickness=band.thickness,
                    group="left-abutment-body" if support.is_left else "right-abutment-body",
                    transverse_band_index=band.index,
                    transverse_band_name=band.name,
                    transverse_role=band.role,
                )


def generate_abutment(builder: MeshBuilder, support: Support, adjacent: SpanRecord, context: MeshContext) -> None:
    is_left = bool(support.is_left)
    outer_spring = adjacent.outer_left if is_left else adjacent.outer_right
    domain_x = support.origin[0]
    x_coordinates = subdivide_interval(domain_x, outer_spring[0], context.max_length)
    bottom_level = outer_spring[2]
    for band in context.deck_bands:
        generate_layered_strip(
            builder,
            x_coordinates=x_coordinates,
            bottom_at=lambda _x, value=bottom_level: value,
            band=band,
            context=context,
            group="left-abutment-fill" if is_left else "right-abutment-fill",
        )
        cap_material = attr_text(adjacent.element, "MaterialPulvinoKey", "0")
        points = (
            [
                [support.left_x, band.y, support.origin[2]],
                [support.right_x, band.y, support.origin[2]],
                [outer_spring[0], band.y, outer_spring[2]],
                [domain_x, band.y, outer_spring[2]],
            ]
            if is_left
            else [
                [support.left_x, band.y, support.origin[2]],
                [support.right_x, band.y, support.origin[2]],
                [domain_x, band.y, outer_spring[2]],
                [outer_spring[0], band.y, outer_spring[2]],
            ]
        )
        _try_add_quad(
            builder,
            points,
            material_key=cap_material,
            layer_key=1,
            thickness=band.thickness,
            group="left-abutment-cap" if is_left else "right-abutment-cap",
            transverse_band_index=band.index,
            transverse_band_name=band.name,
            transverse_role=band.role,
        )
    _generate_abutment_body(builder, support, context)


def _support_shape_factor(element: etree._Element, z: float, top_z: float, bottom_z: float) -> float:
    if top_z - bottom_z <= EPS:
        return 0.0
    depth = max(0.0, min(1.0, (top_z - z) / (top_z - bottom_z)))
    alignment = attr_text(element, "VerticalAllignment", "Top").lower()
    if alignment == "bottom":
        return 1.0 - depth
    if alignment == "center":
        # HiStrA's common Center case has zero b1/b3/w1/w3.  For non-zero
        # values use a symmetric waist, which is continuous and conservative.
        return abs(2.0 * depth - 1.0)
    return depth


def _pier_x_bounds(support: Support, z: float, top_z: float, bottom_z: float) -> tuple[float, float]:
    factor = _support_shape_factor(support.element, z, top_z, bottom_z)
    return (
        support.left_x - attr_float(support.element, "b1") * factor,
        support.right_x + attr_float(support.element, "b3") * factor,
    )


def _pier_y_bounds(support: Support, z: float, top_z: float, bottom_z: float) -> tuple[float, float]:
    factor = _support_shape_factor(support.element, z, top_z, bottom_z)
    return (
        support.center_y - support.width_y / 2 - attr_float(support.element, "w3") * factor,
        support.center_y + support.width_y / 2 + attr_float(support.element, "w1") * factor,
    )


def _generate_pier_cap(
    builder: MeshBuilder,
    *,
    support: Support,
    previous: SpanRecord,
    next_span: SpanRecord,
    band: TransverseBand,
    context: MeshContext,
) -> None:
    top_left = previous.outer_right
    top_right = next_span.outer_left
    bottom_left = [support.left_x, band.y, support.origin[2]]
    bottom_right = [support.right_x, band.y, support.origin[2]]
    # HiStrA models pier caps as one macro-element on each half of the
    # support, independently of the target wall-mesh length.  Keeping the
    # centre break also prevents the cap from pulling unrelated arch nodes
    # together when adjacent spans have different extrados elevations.
    count = 2
    material = attr_text(previous.element, "MaterialPulvinoKey", "0")
    for index in range(count):
        u0, u1 = index / count, (index + 1) / count
        points = [
            [lerp(bottom_left[0], bottom_right[0], u0), band.y, support.origin[2]],
            [lerp(bottom_left[0], bottom_right[0], u1), band.y, support.origin[2]],
            [lerp(top_left[0], top_right[0], u1), band.y, lerp(top_left[2], top_right[2], u1)],
            [lerp(top_left[0], top_right[0], u0), band.y, lerp(top_left[2], top_right[2], u0)],
        ]
        _try_add_quad(
            builder,
            points,
            material_key=material,
            layer_key=1,
            thickness=band.thickness,
            group=f"pier-{support.sequence_index}-cap",
            transverse_band_index=band.index,
            transverse_band_name=band.name,
            transverse_role=band.role,
        )


def _generate_pier_shaft(builder: MeshBuilder, support: Support, context: MeshContext) -> tuple[tuple[float, float], tuple[float, float]]:
    element = support.element
    height = attr_float(element, "H")
    top_z = support.origin[2]
    bottom_z = top_z - height
    if height <= EPS:
        return (support.left_x, support.right_x), (
            support.center_y - support.width_y / 2,
            support.center_y + support.width_y / 2,
        )
    z_coordinates = subdivide_interval(bottom_z, top_z, context.max_length)
    for row_index, (z0, z1) in enumerate(zip(z_coordinates, z_coordinates[1:])):
        x0_left, x0_right = _pier_x_bounds(support, z0, top_z, bottom_z)
        x1_left, x1_right = _pier_x_bounds(support, z1, top_z, bottom_z)
        x0_center, x1_center = (x0_left + x0_right) / 2, (x1_left + x1_right) / 2
        left_length = max(x0_center - x0_left, x1_center - x1_left)
        right_length = max(x0_right - x0_center, x1_right - x1_center)
        left_count = max(1, math.ceil(left_length / context.max_length))
        right_count = max(1, math.ceil(right_length / context.max_length))
        parameters = [index / left_count * 0.5 for index in range(left_count)]
        parameters += [0.5 + index / right_count * 0.5 for index in range(right_count)]
        parameters.append(1.0)
        parameters = sorted_unique(parameters, tolerance=1e-9)

        middle_z = (z0 + z1) / 2
        y_min, y_max = _pier_y_bounds(support, middle_z, top_z, bottom_z)
        bands = make_component_bands_from_bounds(
            y_min=y_min,
            y_max=y_max,
            internal_boundaries=context.deck_internal_boundaries,
            role="pier",
        )
        for band in bands:
            for u0, u1 in zip(parameters, parameters[1:]):
                builder.add_quad(
                    [
                        [lerp(x0_left, x0_right, u0), band.y, z0],
                        [lerp(x0_left, x0_right, u1), band.y, z0],
                        [lerp(x1_left, x1_right, u1), band.y, z1],
                        [lerp(x1_left, x1_right, u0), band.y, z1],
                    ],
                    material_key=attr_text(element, "MaterialKey", "0"),
                    layer_key=1,
                    thickness=band.thickness,
                    group=f"pier-{support.sequence_index}-shaft",
                    transverse_band_index=band.index,
                    transverse_band_name=band.name,
                    transverse_role=band.role,
                )
    return _pier_x_bounds(support, bottom_z, top_z, bottom_z), _pier_y_bounds(
        support, bottom_z, top_z, bottom_z
    )


def _generate_pier_foundation(
    builder: MeshBuilder,
    *,
    support: Support,
    bottom_x_bounds: tuple[float, float],
    bottom_y_bounds: tuple[float, float],
    context: MeshContext,
) -> None:
    element = support.element
    foundation_height = attr_float(element, "Hf")
    if foundation_height <= EPS:
        return
    height = attr_float(element, "H")
    foundation_top = support.origin[2] - height
    foundation_bottom = foundation_top - foundation_height
    shaft_left_x, shaft_right_x = bottom_x_bounds
    shaft_center_x = (shaft_left_x + shaft_right_x) / 2
    foundation_left_x = shaft_left_x - attr_float(element, "B1f")
    foundation_right_x = shaft_right_x + attr_float(element, "B3f")
    x_coordinates = subdivide_interval(
        foundation_left_x,
        foundation_right_x,
        context.max_length,
        [shaft_left_x, shaft_center_x, shaft_right_x],
    )
    z_coordinates = subdivide_interval(foundation_bottom, foundation_top, context.max_length)

    shaft_y_min, shaft_y_max = bottom_y_bounds
    foundation_y_min = shaft_y_min - attr_float(element, "W3f")
    foundation_y_max = shaft_y_max + attr_float(element, "W1f")
    bands = make_component_bands_from_bounds(
        y_min=foundation_y_min,
        y_max=foundation_y_max,
        internal_boundaries=context.deck_internal_boundaries,
        forced_boundaries=[shaft_y_min, shaft_y_max],
        role="foundation",
    )
    for band in bands:
        for ix in range(len(x_coordinates) - 1):
            for iz in range(len(z_coordinates) - 1):
                builder.add_quad(
                    [
                        [x_coordinates[ix], band.y, z_coordinates[iz]],
                        [x_coordinates[ix + 1], band.y, z_coordinates[iz]],
                        [x_coordinates[ix + 1], band.y, z_coordinates[iz + 1]],
                        [x_coordinates[ix], band.y, z_coordinates[iz + 1]],
                    ],
                    material_key=attr_text(element, "MaterialFoundationKey", "0"),
                    layer_key=1,
                    thickness=band.thickness,
                    group=f"pier-{support.sequence_index}-foundation",
                    transverse_band_index=band.index,
                    transverse_band_name=band.name,
                    transverse_role=band.role,
                )


def generate_pier(builder: MeshBuilder, support: Support, previous: SpanRecord, next_span: SpanRecord, context: MeshContext) -> None:
    connector_points = [previous.outer_right, next_span.outer_left]
    connector = PolylineFunction(connector_points)
    x_coordinates = subdivide_interval(connector_points[0][0], connector_points[1][0], context.max_length)
    for band in context.deck_bands:
        generate_layered_strip(
            builder,
            x_coordinates=x_coordinates,
            bottom_at=connector.at,
            band=band,
            context=context,
            group=f"pier-{support.sequence_index}-fill",
        )
        _generate_pier_cap(
            builder,
            support=support,
            previous=previous,
            next_span=next_span,
            band=band,
            context=context,
        )
    bottom_x_bounds, bottom_y_bounds = _generate_pier_shaft(builder, support, context)
    _generate_pier_foundation(
        builder,
        support=support,
        bottom_x_bounds=bottom_x_bounds,
        bottom_y_bounds=bottom_y_bounds,
        context=context,
    )


def validate_mesh_geometry(mesh: Mesh, tolerance: float = 1e-8) -> dict[str, Any]:
    nodes = {node.key: node.point for node in mesh.nodes}
    errors: list[str] = []
    repeated = zero_area = self_intersecting = missing = 0
    for quad in mesh.quads:
        if any(key not in nodes for key in quad.node_keys):
            missing += 1
            errors.append(f"Quad {quad.key} references a missing node")
            continue
        points = [nodes[key] for key in quad.node_keys]
        if len(set(quad.node_keys)) != 4:
            repeated += 1
            errors.append(f"Quad {quad.key} repeats a node")
        if abs(_signed_area_xz(points)) <= tolerance:
            zero_area += 1
            errors.append(f"Quad {quad.key} has zero area")
        if _segments_cross(points[0], points[1], points[2], points[3], tolerance) or _segments_cross(
            points[1], points[2], points[3], points[0], tolerance
        ):
            self_intersecting += 1
            errors.append(f"Quad {quad.key} is self-intersecting")
    return {
        "valid": not errors,
        "errorCount": len(errors),
        "repeatedNodeQuads": repeated,
        "zeroAreaQuads": zero_area,
        "selfIntersectingQuads": self_intersecting,
        "missingNodeReferences": missing,
        "errors": errors[:100],
    }


def generate_mesh(tree: etree._ElementTree, options: MeshPatch) -> Mesh:
    root = tree.getroot()
    wizard = first_direct(root, "WizardData")
    if wizard is None:
        raise ValueError("No WizardData element was found")
    bridge = first_direct(wizard, "BridgeDefinition")
    if bridge is None:
        raise ValueError("WizardData/BridgeDefinition is missing")
    warnings: list[str] = []
    max_length = options.MaxLength or attr_float(bridge, "Nl", 30.0)
    if max_length <= 0:
        raise ValueError("Mesh maximum length must be positive")
    bridge_width = attr_float(bridge, "Width", 1.0)
    builder = MeshBuilder(options.NodeTolerance, parent_key=1)
    elevation_profile = make_elevation_profile(wizard, warnings)
    backfill_layers = make_backfill_layers(wizard, elevation_profile, warnings)
    deck_bands, internal_boundaries, _transverse_width, _ = make_deck_bands(bridge, warnings)
    if any(band.thickness <= EPS for band in deck_bands):
        raise ValueError("Every lane width must be positive")

    sequence_elements = [child for child in direct_children(wizard) if child.tag in {"Abutment", "Span", "Pier"}]
    if len(sequence_elements) < 3:
        raise ValueError("WizardData does not contain a support/span sequence")
    support_by_index: dict[int, Support] = {}
    supports: list[Support] = []
    for index, element in enumerate(sequence_elements):
        if element.tag in {"Abutment", "Pier"}:
            support = support_from_element(element, index)
            support_by_index[index] = support
            supports.append(support)
            if element.tag == "Pier" and any(
                abs(attr_float(element, name)) > EPS for name in ("b1", "b3", "w1", "w3")
            ):
                warnings.append(
                    f"Pier at x={support.center_x}: b1/b3/w1/w3 variation is reconstructed with "
                    f"VerticalAllignment={attr_text(element, 'VerticalAllignment', 'Top')}"
                )
            if abs(attr_float(element, "beta1")) > EPS or abs(attr_float(element, "beta2")) > EPS:
                warnings.append(f"{element.tag} at x={support.center_x}: beta taper is not reconstructed")

    span_records: list[SpanRecord] = []
    for index, element in enumerate(sequence_elements):
        if element.tag != "Span":
            continue
        left_support = support_by_index.get(index - 1)
        right_support = support_by_index.get(index + 1)
        if left_support is None or right_support is None:
            raise ValueError(f"Span at sequence index {index} is not between two supports")
        span_records.append(
            SpanRecord(
                element=element,
                sequence_index=index,
                index=len(span_records),
                left_support=left_support,
                right_support=right_support,
            )
        )
    advanced = first_direct(root, "AdvancedOptionsDefault")
    context = MeshContext(
        max_length=max_length,
        elevation_profile=elevation_profile,
        backfill_layers=backfill_layers,
        bridge_width=bridge_width,
        deck_bands=deck_bands,
        deck_internal_boundaries=internal_boundaries,
        parent_key=1,
        warnings=warnings,
        arc_division_mode=options.ArcDivisionMode,
        arc_division_override=options.ArcDivisions,
        arc_minimum=round(attr_float(advanced, "ArcoMesherQuadNumMin", 4.0)),
    )
    spans = [compute_span_geometry(record, context) for record in span_records]
    for band in deck_bands:
        for span in spans:
            generate_span_for_band(builder, span, band, context)

    span_by_left = {span.left_support: span for span in spans}
    span_by_right = {span.right_support: span for span in spans}
    for support in supports:
        if support.type == "Abutment":
            adjacent = span_by_left.get(support) if support.is_left else span_by_right.get(support)
            if adjacent is None:
                raise ValueError("An abutment has no adjacent span")
            generate_abutment(builder, support, adjacent, context)
        else:
            previous = span_by_right.get(support)
            next_span = span_by_left.get(support)
            if previous is None or next_span is None:
                warnings.append(f"Pier at x={support.center_x} is not between two spans and was skipped")
                continue
            generate_pier(builder, support, previous, next_span, context)

    mesh = Mesh(nodes=builder.nodes, quads=builder.quads, metadata={})
    geometry_validation = validate_mesh_geometry(mesh)
    if not geometry_validation["valid"]:
        summary = "; ".join(geometry_validation["errors"][:5])
        raise ValueError(f"Generated mesh failed geometric validation: {summary}")

    metadata = {
        "wizardType": root.get("WizardType", ""),
        "version": root.get("version", ""),
        "maxLength": max_length,
        "thickness": bridge_width,
        "bridgeWidth": bridge_width,
        "backfillLayers": [layer.as_dict() for layer in backfill_layers],
        "spanCount": len(spans),
        "supportCount": len(supports),
        "transverseBandCount": len(deck_bands),
        "transverseBands": [band.as_dict() for band in deck_bands],
        "warnings": warnings,
        "arcDivisionMode": context.arc_division_mode,
        "geometryValidation": geometry_validation,
        "spans": [
            {
                "index": span.index,
                "xStart": span.x_start,
                "xEnd": span.x_end,
                "radius": span.radius,
                "centerX": span.center_x,
                "centerZ": span.center_z,
                "springZ": span.spring_z,
                "arcDivisions": span.arc_divisions,
                "radialDivisions": span.radial_divisions,
                "springThickness": span.spring_thickness,
                "crownThickness": span.crown_thickness,
            }
            for span in spans
        ],
    }
    mesh.metadata = metadata
    return mesh


def mesh_from_hrx(tree: etree._ElementTree) -> Mesh:
    """Read the already-generated Node/Quad geometry from an HRX document."""

    root = tree.getroot()
    nodes: list[Node] = []
    node_keys: set[int] = set()
    for element in direct_children(root, "Node"):
        key_raw = element.get("Key")
        point_raw = element.get("Point")
        if not key_raw or not point_raw:
            continue
        key = int(key_raw)
        nodes.append(Node(key=key, point=parse_vector(point_raw)))
        node_keys.add(key)

    quads: list[Quad] = []
    for element in direct_children(root, "Quad"):
        try:
            node_refs = [int(element.get(f"NodeKey{i}", "")) for i in range(1, 5)]
        except ValueError:
            continue
        if any(key not in node_keys for key in node_refs):
            continue
        thickness_values = [attr_float(element, f"Thickness{i}") for i in range(1, 5)]
        thickness = sum(thickness_values) / 4
        key = int(element.get("Key", str(len(quads) + 1)))
        quads.append(
            Quad(
                key=key,
                node_keys=node_refs,
                material_key=attr_text(element, "MaterialKey", "0"),
                layer_key=int(attr_float(element, "LayerKey", 0)),
                parent_key=int(attr_float(element, "ParentKey", 1)),
                parent_type_element=attr_text(element, "ParentTypeElement", "Bridge"),
                thickness=thickness,
                group=f"imported-material-{attr_text(element, 'MaterialKey', '0')}",
            )
        )
    mesh = Mesh(
        nodes=nodes,
        quads=quads,
        metadata={
            "source": "imported-hrx",
            "warnings": [],
            "counts": {"nodes": len(nodes), "quads": len(quads)},
        },
    )
    mesh.metadata["geometryValidation"] = validate_mesh_geometry(mesh)
    return mesh
