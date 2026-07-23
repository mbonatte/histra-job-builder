from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

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

    def add_quad(self, points: list[Point], **metadata: Any) -> int:
        if len(points) != 4:
            raise ValueError("A quad must contain exactly four points")
        node_keys = [self.add_node(point) for point in points]
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
                group=str(metadata.get("group", "mesh")),
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
        }


@dataclass
class ElevationFunction:
    samples: list[dict[str, float]]

    def at(self, x: float) -> float:
        if len(self.samples) == 1:
            return self.samples[0]["z"]
        if x <= self.samples[0]["x"]:
            return self.samples[0]["z"]
        if x >= self.samples[-1]["x"]:
            return self.samples[-1]["z"]
        for a, b in zip(self.samples, self.samples[1:]):
            if a["x"] <= x <= b["x"]:
                dx = b["x"] - a["x"]
                t = 0.0 if abs(dx) < EPS else (x - a["x"]) / dx
                return lerp(a["z"], b["z"], t)
        return self.samples[-1]["z"]


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
    arc_divisions: int = 0
    radial_divisions: int = 0
    fill_divisions: int = 0
    curves: list[list[Point]] = field(default_factory=list)
    inner_curve: list[Point] = field(default_factory=list)
    outer_curve: list[Point] = field(default_factory=list)
    outer_left: Point = field(default_factory=list)
    outer_right: Point = field(default_factory=list)


@dataclass
class MeshContext:
    max_length: float
    top_elevation: ElevationFunction
    fill_material_key: str
    bridge_width: float
    deck_bands: list[TransverseBand]
    deck_internal_boundaries: list[float]
    parent_key: int
    warnings: list[str]
    arc_division_mode: str
    arc_division_override: Optional[int]
    arc_minimum: int


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


def make_top_elevation(wizard: etree._Element, warnings: list[str]) -> ElevationFunction:
    elevations_root = first_direct(wizard, "Elevations")
    elevation_list = first_direct(elevations_root, "Elevations")
    samples = [
        {
            "x": attr_float(item, "X"),
            "z": attr_float(item, "H1"),
            "h2": attr_float(item, "H2"),
            "h3": attr_float(item, "H3"),
        }
        for item in direct_children(elevation_list, "Elevation")
    ]
    samples.sort(key=lambda item: item["x"])
    if not samples:
        warnings.append("No Elevations/Elevation.H1 was found; top elevation defaults to 0")
        samples = [{"x": 0.0, "z": 0.0, "h2": 0.0, "h3": 0.0}]
    if len(samples) > 1:
        warnings.append("Variable H1 elevations are approximated by piecewise-linear interpolation")
    if any(abs(item["h2"]) > EPS or abs(item["h3"]) > EPS for item in samples):
        warnings.append("H2/H3 stratigraphy is present; only H1 is meshed")
    return ElevationFunction(samples=samples)


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
            )
        )
    return bands, boundaries[1:-1], width, bridge_origin[1]


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
    if width <= EPS:
        return []
    component_left = center_y - width / 2
    component_right = center_y + width / 2
    y_min = component_left - max(0.0, left_extra)
    y_max = component_right + max(0.0, right_extra)
    candidates = [y_min, *internal_boundaries, *forced_boundaries, y_max]
    boundaries = sorted_unique(value for value in candidates if y_min - EPS <= value <= y_max + EPS)
    bands: list[TransverseBand] = []
    for index, (lower, upper) in enumerate(zip(boundaries, boundaries[1:])):
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


def resolve_arc_divisions(
    *, radius: float, ring_thickness: float, angle_span: float, max_length: float,
    minimum: int, mode: str, override: Optional[int]
) -> int:
    if override is not None and override > 0:
        return max(1, round(override))
    inner_target = radius * angle_span / max_length
    outer_target = (radius + ring_thickness) * angle_span / max_length
    if mode == "inner-ceil":
        divisions = math.ceil(inner_target)
    elif mode == "outer-ceil":
        divisions = math.ceil(outer_target)
    else:
        divisions = 2 * max(1, round(outer_target / 2))
    minimum = max(1, math.ceil(minimum or 1))
    return max(divisions, 2 * math.ceil(minimum / 2)) if mode == "observed-even" else max(divisions, minimum)


def compute_span_geometry(record: SpanRecord, context: MeshContext) -> SpanRecord:
    element = record.element
    x_start = record.left_support.right_x
    x_end = record.right_support.left_x
    actual_length = x_end - x_start
    declared_length = attr_float(element, "L", actual_length)
    rise = attr_float(element, "f")
    ring_thickness = attr_float(element, "Tb")
    dz = attr_float(element, "Dz")
    if actual_length <= 0:
        raise ValueError(f"Span {record.index + 1} has a non-positive support-to-support length")
    if rise <= 0:
        raise ValueError(f"Span {record.index + 1} has a non-positive rise")
    if abs(declared_length - actual_length) > 1e-3:
        context.warnings.append(
            f"Span {record.index + 1}: declared L={declared_length} differs from support geometry "
            f"{actual_length}; support geometry was used"
        )
    if abs(record.left_support.origin[2] - record.right_support.origin[2]) > 1e-6:
        context.warnings.append(f"Span {record.index + 1}: unequal support elevations use one horizontal spring line")
    if attr_bool(element, "IsChkAdvancedMode"):
        context.warnings.append(f"Span {record.index + 1}: advanced mode is approximated from L/f/Tb/Dz")

    radius = actual_length**2 / (8 * rise) + rise / 2
    center_x = (x_start + x_end) / 2
    spring_z = (record.left_support.origin[2] + record.right_support.origin[2]) / 2 + dz
    center_z = spring_z + rise - radius
    angle_start = math.atan2(spring_z - center_z, x_start - center_x)
    angle_end = math.atan2(spring_z - center_z, x_end - center_x)
    angle_span = abs(angle_end - angle_start)
    arc_divisions = resolve_arc_divisions(
        radius=radius,
        ring_thickness=ring_thickness,
        angle_span=angle_span,
        max_length=context.max_length,
        minimum=context.arc_minimum,
        mode=context.arc_division_mode,
        override=context.arc_division_override,
    )
    radial_divisions = max(1, math.ceil(max(ring_thickness, EPS) / context.max_length))
    curves: list[list[Point]] = []
    for radial in range(radial_divisions + 1):
        current_radius = radius + ring_thickness * radial / radial_divisions
        curve: list[Point] = []
        for index in range(arc_divisions + 1):
            t = index / arc_divisions
            angle = lerp(angle_start, angle_end, t)
            curve.append([
                center_x + current_radius * math.cos(angle),
                0.0,
                center_z + current_radius * math.sin(angle),
            ])
        curves.append(curve)
    outer = curves[-1]
    max_fill_depth = max(max(0.0, context.top_elevation.at(point[0]) - point[2]) for point in outer)
    fill_divisions = max(1, math.ceil(max_fill_depth / context.max_length))

    record.x_start = x_start
    record.x_end = x_end
    record.radius = radius
    record.center_x = center_x
    record.center_z = center_z
    record.spring_z = spring_z
    record.arc_divisions = arc_divisions
    record.radial_divisions = radial_divisions
    record.fill_divisions = fill_divisions
    record.curves = curves
    record.inner_curve = curves[0]
    record.outer_curve = outer
    record.outer_left = outer[0]
    record.outer_right = outer[-1]
    return record


def add_vertical_strip(
    builder: MeshBuilder,
    x_coordinates: list[float],
    bottom_at: Callable[[float], float],
    top_at: Callable[[float], float],
    divisions: int,
    band: TransverseBand,
    **metadata: Any,
) -> None:
    nz = max(1, divisions)
    for x0, x1 in zip(x_coordinates, x_coordinates[1:]):
        bottom0, bottom1 = bottom_at(x0), bottom_at(x1)
        top0, top1 = top_at(x0), top_at(x1)
        for iz in range(nz):
            t0, t1 = iz / nz, (iz + 1) / nz
            builder.add_quad(
                [
                    [x0, band.y, lerp(bottom0, top0, t0)],
                    [x1, band.y, lerp(bottom1, top1, t0)],
                    [x1, band.y, lerp(bottom1, top1, t1)],
                    [x0, band.y, lerp(bottom0, top0, t1)],
                ],
                thickness=band.thickness,
                transverse_band_index=band.index,
                transverse_band_name=band.name,
                transverse_role=band.role,
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
    outer = curves[-1]
    material_key = fill_material_for_band(band, context.fill_material_key)
    for index in range(span.arc_divisions):
        p0, p1 = outer[index], outer[index + 1]
        top0, top1 = context.top_elevation.at(p0[0]), context.top_elevation.at(p1[0])
        for iz in range(span.fill_divisions):
            t0, t1 = iz / span.fill_divisions, (iz + 1) / span.fill_divisions
            builder.add_quad(
                [
                    [p0[0], band.y, lerp(p0[2], top0, t0)],
                    [p1[0], band.y, lerp(p1[2], top1, t0)],
                    [p1[0], band.y, lerp(p1[2], top1, t1)],
                    [p0[0], band.y, lerp(p0[2], top0, t1)],
                ],
                material_key=material_key,
                layer_key=1,
                thickness=band.thickness,
                group=f"span-{span.index + 1}-fill",
                source_index=span.index,
                transverse_band_index=band.index,
                transverse_band_name=band.name,
                transverse_role=band.role,
            )


def generate_abutment(builder: MeshBuilder, support: Support, adjacent: SpanRecord, context: MeshContext) -> None:
    element = support.element
    is_left = bool(support.is_left)
    outer_spring = adjacent.outer_left if is_left else adjacent.outer_right
    domain_x = support.origin[0]
    x_coordinates = subdivide_interval(min(domain_x, outer_spring[0]), max(domain_x, outer_spring[0]), context.max_length)
    for band in context.deck_bands:
        add_vertical_strip(
            builder,
            x_coordinates,
            lambda _x, z=outer_spring[2]: z,
            context.top_elevation.at,
            adjacent.fill_divisions,
            band,
            material_key=fill_material_for_band(band, context.fill_material_key),
            layer_key=1,
            group="left-abutment-fill" if is_left else "right-abutment-fill",
        )
        cap_material = attr_text(adjacent.element, "MaterialPulvinoKey", "0")
        points = (
            [
                [support.left_x, band.y, support.origin[2]],
                [support.right_x, band.y, support.origin[2]],
                [outer_spring[0], band.y, outer_spring[2]],
                [support.left_x, band.y, outer_spring[2]],
            ]
            if is_left
            else [
                [support.left_x, band.y, support.origin[2]],
                [support.right_x, band.y, support.origin[2]],
                [support.right_x, band.y, outer_spring[2]],
                [outer_spring[0], band.y, outer_spring[2]],
            ]
        )
        builder.add_quad(
            points,
            material_key=cap_material,
            layer_key=1,
            thickness=band.thickness,
            group="left-abutment-cap" if is_left else "right-abutment-cap",
            transverse_band_index=band.index,
            transverse_band_name=band.name,
            transverse_role=band.role,
        )

    height = attr_float(element, "H")
    if height > EPS:
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
                        group="left-abutment-body" if is_left else "right-abutment-body",
                        transverse_band_index=band.index,
                        transverse_band_name=band.name,
                        transverse_role=band.role,
                    )


def generate_pier(builder: MeshBuilder, support: Support, previous: SpanRecord, next_span: SpanRecord, context: MeshContext) -> None:
    element = support.element
    left_outer, right_outer = previous.outer_right, next_span.outer_left
    center_top_z = (left_outer[2] + right_outer[2]) / 2
    center_top = [support.center_x, 0.0, center_top_z]
    fill_divisions = max(previous.fill_divisions, next_span.fill_divisions, 1)
    for band in context.deck_bands:
        halves = [(left_outer, center_top, "left"), (center_top, right_outer, "right")]
        for start, end, name in halves:
            x_coordinates = subdivide_interval(start[0], end[0], context.max_length)
            def bottom_at(x: float, start=start, end=end) -> float:
                denominator = end[0] - start[0]
                t = 0.0 if abs(denominator) < EPS else (x - start[0]) / denominator
                return lerp(start[2], end[2], t)
            add_vertical_strip(
                builder,
                x_coordinates,
                bottom_at,
                context.top_elevation.at,
                fill_divisions,
                band,
                material_key=fill_material_for_band(band, context.fill_material_key),
                layer_key=1,
                group=f"pier-{support.sequence_index}-{name}-fill",
            )
        cap_material = attr_text(previous.element, "MaterialPulvinoKey", "0")
        builder.add_quad(
            [
                [support.left_x, band.y, support.origin[2]],
                [support.center_x, band.y, support.origin[2]],
                [center_top[0], band.y, center_top[2]],
                [left_outer[0], band.y, left_outer[2]],
            ],
            material_key=cap_material,
            layer_key=1,
            thickness=band.thickness,
            group=f"pier-{support.sequence_index}-left-cap",
            transverse_band_index=band.index,
            transverse_band_name=band.name,
            transverse_role=band.role,
        )
        builder.add_quad(
            [
                [support.center_x, band.y, support.origin[2]],
                [support.right_x, band.y, support.origin[2]],
                [right_outer[0], band.y, right_outer[2]],
                [center_top[0], band.y, center_top[2]],
            ],
            material_key=cap_material,
            layer_key=1,
            thickness=band.thickness,
            group=f"pier-{support.sequence_index}-right-cap",
            transverse_band_index=band.index,
            transverse_band_name=band.name,
            transverse_role=band.role,
        )

    height = attr_float(element, "H")
    width_y = attr_float(element, "w2", context.bridge_width)
    shaft_bands = make_component_bands(
        center_y=support.center_y,
        width=width_y,
        internal_boundaries=context.deck_internal_boundaries,
        role="pier",
    )
    if height > EPS:
        z_top = support.origin[2]
        z_coordinates = subdivide_interval(z_top - height, z_top, context.max_length)
        x_coordinates = subdivide_interval(support.left_x, support.right_x, context.max_length, [support.center_x])
        for band in shaft_bands:
            for ix in range(len(x_coordinates) - 1):
                for iz in range(len(z_coordinates) - 1):
                    builder.add_quad(
                        [
                            [x_coordinates[ix], band.y, z_coordinates[iz]],
                            [x_coordinates[ix + 1], band.y, z_coordinates[iz]],
                            [x_coordinates[ix + 1], band.y, z_coordinates[iz + 1]],
                            [x_coordinates[ix], band.y, z_coordinates[iz + 1]],
                        ],
                        material_key=attr_text(element, "MaterialKey", "0"),
                        layer_key=1,
                        thickness=band.thickness,
                        group=f"pier-{support.sequence_index}-shaft",
                        transverse_band_index=band.index,
                        transverse_band_name=band.name,
                        transverse_role=band.role,
                    )

    foundation_height = attr_float(element, "Hf")
    if foundation_height > EPS:
        shaft_left_y = support.center_y - width_y / 2
        shaft_right_y = support.center_y + width_y / 2
        foundation_bands = make_component_bands(
            center_y=support.center_y,
            width=width_y,
            left_extra=attr_float(element, "W1f"),
            right_extra=attr_float(element, "W3f"),
            internal_boundaries=context.deck_internal_boundaries,
            forced_boundaries=[shaft_left_y, shaft_right_y],
            role="foundation",
        )
        x_coordinates = subdivide_interval(
            support.left_x - attr_float(element, "B1f"),
            support.right_x + attr_float(element, "B3f"),
            context.max_length,
            [support.left_x, support.center_x, support.right_x],
        )
        foundation_top = support.origin[2] - height
        foundation_bottom = foundation_top - foundation_height
        z_coordinates = subdivide_interval(foundation_bottom, foundation_top, context.max_length)
        for band in foundation_bands:
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
    elevations_root = first_direct(wizard, "Elevations")
    layer1 = first_direct(elevations_root, "Layer1")
    fill_material_key = attr_text(layer1, "MaterialKey", "0")
    if layer1 is None:
        warnings.append("Elevations/Layer1 is missing; fill material defaults to 0")
    top_elevation = make_top_elevation(wizard, warnings)
    deck_bands, internal_boundaries, transverse_width, _ = make_deck_bands(bridge, warnings)
    if any(band.thickness <= EPS for band in deck_bands):
        raise ValueError("Every lane width must be positive")

    sequence_elements = [
        child for child in direct_children(wizard) if child.tag in {"Abutment", "Span", "Pier"}
    ]
    if len(sequence_elements) < 3:
        raise ValueError("WizardData does not contain a support/span sequence")
    support_by_index: dict[int, Support] = {}
    supports: list[Support] = []
    for index, element in enumerate(sequence_elements):
        if element.tag in {"Abutment", "Pier"}:
            support = support_from_element(element, index)
            support_by_index[index] = support
            supports.append(support)
            if abs(attr_float(element, "w1")) > EPS or abs(attr_float(element, "w3")) > EPS:
                warnings.append(f"{element.tag} at x={support.center_x}: w1/w3 shaping is not reconstructed")
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
        top_elevation=top_elevation,
        fill_material_key=fill_material_key,
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

    metadata = {
        "wizardType": root.get("WizardType", ""),
        "version": root.get("version", ""),
        "maxLength": max_length,
        "thickness": bridge_width,
        "bridgeWidth": bridge_width,
        "fillMaterialKey": fill_material_key,
        "spanCount": len(spans),
        "supportCount": len(supports),
        "transverseBandCount": len(deck_bands),
        "transverseBands": [band.as_dict() for band in deck_bands],
        "warnings": warnings,
        "arcDivisionMode": context.arc_division_mode,
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
                "fillDivisions": span.fill_divisions,
            }
            for span in spans
        ],
    }
    return Mesh(nodes=builder.nodes, quads=builder.quads, metadata=metadata)
