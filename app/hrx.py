from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from lxml import etree

from .analyses import rebuild_analyses
from .mesh import Mesh, Node, Quad
from .model_points import ModelPointSelection, make_model_point, select_model_points
from .schemas import GenerationRequest, ValidationReport
from .xml_utils import (
    EPS,
    attr_float,
    clear_children,
    clone,
    direct_children,
    ensure_child,
    first_direct,
    fmt,
    reference_system,
    serialize,
    set_attributes,
    vec_text,
)

GEOMETRY_TAGS = {
    "Node", "ModelPoint", "Quad", "Restraint", "GeometryLineRestraint",
    "NodeC", "SurfaceRestraint", "Bridge", "LoadElement",
}


def add(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def sub(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def scale(a: Sequence[float], value: float) -> list[float]:
    return [a[0] * value, a[1] * value, a[2] * value]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def magnitude(a: Sequence[float]) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Sequence[float], fallback: Sequence[float] = (1, 0, 0)) -> list[float]:
    value = magnitude(a)
    return scale(a, 1 / value) if value > EPS else list(fallback)


def centroid(points: list[list[float]]) -> list[float]:
    result = [0.0, 0.0, 0.0]
    for point in points:
        result = add(result, point)
    return scale(result, 1 / len(points))


def nearly_equal(a: float, b: float, tolerance: float = 1e-6) -> bool:
    return abs(a - b) <= tolerance


def clear_afference_values(root: etree._Element | None) -> None:
    if root is None:
        return
    for matrix in direct_children(root, "AfferenceMatrix"):
        alfa = first_direct(matrix, "Alfa")
        gdl = first_direct(matrix, "Gdl")
        if alfa is not None:
            clear_children(alfa)
        if gdl is not None:
            clear_children(gdl)


def make_node(archetype: etree._Element | None, node: Node, model_point_node_keys: set[int]) -> etree._Element:
    element = clone(archetype, "Node")
    clear_children(element)
    element.attrib.clear()
    set_attributes(
        element,
        {
            "IsModelPoint": "True" if node.key in model_point_node_keys else "false",
            "Point": vec_text(node.point),
            "MasterElementKey": "0",
            "MasterElementType": "None",
            "LayerKey": "0",
            "IsPropertyModified": "false",
            "Key": node.key,
            "Name": node.key,
        },
    )
    element.append(reference_system([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0]))
    return element


def quad_geometry(points: list[list[float]]) -> dict[str, Any]:
    lengths = [math.dist(point, points[(index + 1) % 4]) for index, point in enumerate(points)]
    diagonals = [math.dist(points[0], points[2]), math.dist(points[1], points[3])]
    cosines: list[float] = []
    sines: list[float] = []
    for index in range(4):
        previous = sub(points[(index + 3) % 4], points[index])
        next_edge = sub(points[(index + 1) % 4], points[index])
        denominator = magnitude(previous) * magnitude(next_edge)
        if denominator <= EPS:
            raise ValueError("Degenerate quad edge found while exporting")
        cosine = max(-1.0, min(1.0, dot(previous, next_edge) / denominator))
        cosines.append(cosine)
        sines.append(magnitude(cross(previous, next_edge)) / denominator)
    e1 = normalize(sub(points[1], points[0]))
    e3 = normalize(cross(sub(points[1], points[0]), sub(points[3], points[0])), (0, -1, 0))
    e2 = normalize(cross(e3, e1), (0, 0, 1))
    return {
        "lengths": lengths,
        "diagonals": diagonals,
        "cosines": cosines,
        "sines": sines,
        "normal": e3,
        "center": centroid(points),
        "axes": [e1, e2, e3],
    }


def _child_archetypes(element: etree._Element) -> list[etree._Element]:
    return [copy.deepcopy(child) for child in direct_children(element)]


def make_quad(archetype: etree._Element | None, quad: Quad, points: list[list[float]]) -> etree._Element:
    element = clone(archetype, "Quad")
    children = _child_archetypes(element)
    clear_children(element)
    element.attrib.clear()
    geometry = quad_geometry(points)
    n1, n2, n3, n4 = quad.node_keys
    thickness = fmt(quad.thickness)
    attrs = {
        "IsModelPointG": "false", "IsModelPoint1": "false", "IsModelPoint2": "false",
        "IsModelPoint3": "false", "IsModelPoint4": "false",
        "LoadTemplateAreaKey": "0", "LoadTemplateLineKey": "0", "LoadTemplatePointKey": "0",
        "ParentKey": quad.parent_key or 1,
        "ParentTypeElement": quad.parent_type_element or "Bridge",
        "NodeKey1": n1, "NodeKey2": n2, "NodeKey3": n3, "NodeKey4": n4,
        "Thickness1": thickness, "Thickness2": thickness, "Thickness3": thickness, "Thickness4": thickness,
        "Length1": fmt(geometry["lengths"][0]), "Length2": fmt(geometry["lengths"][1]),
        "Length3": fmt(geometry["lengths"][2]), "Length4": fmt(geometry["lengths"][3]),
        "Diago1": fmt(geometry["diagonals"][0]), "Diago2": fmt(geometry["diagonals"][1]),
        "Cos1": fmt(geometry["cosines"][0]), "Cos2": fmt(geometry["cosines"][1]),
        "Cos3": fmt(geometry["cosines"][2]), "Cos4": fmt(geometry["cosines"][3]),
        "Sin1": fmt(geometry["sines"][0]), "Sin2": fmt(geometry["sines"][1]),
        "Sin3": fmt(geometry["sines"][2]), "Sin4": fmt(geometry["sines"][3]),
        "MaterialKey": quad.material_key,
        "HeightTopVaultLoad": "0",
        "U1": "0", "U2": "0", "U3": "0", "U4": "0", "U5": "0", "U6": "0", "U7": "0",
        "LoadTemplateLinePoint1": "0;0;0", "LoadTemplateLinePoint2": "0;0;0",
        "LoadTemplatePointPoint": "0;0;0",
        "Normal1": vec_text(geometry["normal"]), "Normal2": vec_text(geometry["normal"]),
        "Normal3": vec_text(geometry["normal"]), "Normal4": vec_text(geometry["normal"]),
        "G": vec_text(geometry["center"]),
        "MasterElementKey": "0", "MasterElementType": "None",
        "LayerKey": quad.layer_key, "IsPropertyModified": "false",
        "Key": quad.key, "Name": quad.key,
    }
    set_attributes(element, attrs)
    for child in children:
        if child.tag in {"Spring", "ReferenceSystem"}:
            continue
        if child.tag == "AfferenceMatrices":
            clear_afference_values(child)
        else:
            clear_children(child)
        element.append(child)
    if first_direct(element, "AfferenceMatrices") is None:
        element.append(etree.Element("AfferenceMatrices"))
    element.append(reference_system(geometry["axes"], points[0]))
    return element


def component_id_for_quad(quad: Quad) -> str | None:
    group = quad.group
    if group.startswith("left-abutment-"):
        return "left-abutment"
    if group.startswith("right-abutment-"):
        return "right-abutment"
    if group.startswith("pier-") and group.endswith(("-shaft", "-foundation")):
        parts = group.split("-")
        return f"pier-{parts[1]}"
    return None


@dataclass
class FoundationSegment:
    component: str
    quad: Quad
    edge: int
    node1: int
    node2: int
    point1: list[float]
    point2: list[float]
    thickness: float
    y: float


@dataclass
class RestraintData:
    component: str
    quad: Quad
    edge: int
    node1: int
    node2: int
    point1: list[float]
    point2: list[float]
    thickness: float
    y: float
    key: int
    local_name: int
    line_key: int
    node_c1: int = 0
    node_c2: int = 0


@dataclass
class LineGroup:
    component: str
    thickness: float
    y: float
    start: float
    end: float
    z: float
    key: int = 0
    restraints: list[RestraintData] = field(default_factory=list)


@dataclass
class NodeCData:
    node_key: int
    key: int
    restraint_keys: list[int]


@dataclass
class RestraintTopology:
    line_groups: list[LineGroup]
    node_cs: list[NodeCData]


def collect_foundation_segments(mesh: Mesh) -> list[tuple[str, list[FoundationSegment], float]]:
    nodes = {node.key: node for node in mesh.nodes}
    groups: dict[tuple[str, str], list[Quad]] = {}
    for quad in mesh.quads:
        component = component_id_for_quad(quad)
        if component is None:
            continue
        band = f"{quad.transverse_band_index}|{fmt(quad.thickness)}"
        groups.setdefault((component, band), []).append(quad)
    result: list[tuple[str, list[FoundationSegment], float]] = []
    for (component, _band), quads in groups.items():
        minimum = min(nodes[key].point[2] for quad in quads for key in quad.node_keys)
        segments: list[FoundationSegment] = []
        for quad in quads:
            points = [nodes[key].point for key in quad.node_keys]
            for edge in range(4):
                next_index = (edge + 1) % 4
                if not nearly_equal(points[edge][2], minimum) or not nearly_equal(points[next_index][2], minimum):
                    continue
                if not nearly_equal(points[edge][1], points[next_index][1]):
                    continue
                left_index, right_index = (edge, next_index) if points[edge][0] <= points[next_index][0] else (next_index, edge)
                segments.append(
                    FoundationSegment(
                        component=component,
                        quad=quad,
                        edge=edge,
                        node1=quad.node_keys[left_index],
                        node2=quad.node_keys[right_index],
                        point1=points[left_index],
                        point2=points[right_index],
                        thickness=quad.thickness,
                        y=points[left_index][1],
                    )
                )
        segments.sort(key=lambda item: item.point1[0])
        if segments:
            result.append((component, segments, minimum))
    return result


def structural_breaks(mesh: Mesh, component: str, segments: list[FoundationSegment]) -> list[float]:
    minimum = segments[0].point1[0]
    maximum = segments[-1].point2[0]
    if not component.startswith("pier-"):
        return [minimum, maximum]
    prefix = f"{component}-shaft"
    shaft = [quad for quad in mesh.quads if quad.group == prefix]
    if not shaft:
        return [minimum, maximum]
    node_by_key = {node.key: node.point for node in mesh.nodes}
    x_values = [node_by_key[key][0] for quad in shaft for key in quad.node_keys]
    left, right = min(x_values), max(x_values)
    center = (left + right) / 2
    values = sorted([minimum, left, center, right, maximum])
    result: list[float] = []
    for value in values:
        if not result or not nearly_equal(value, result[-1]):
            result.append(value)
    return result


def build_restraint_topology(mesh: Mesh) -> RestraintTopology:
    line_groups: list[LineGroup] = []
    for component, segments, minimum in collect_foundation_segments(mesh):
        breaks = structural_breaks(mesh, component, segments)
        for start, end in zip(breaks, breaks[1:]):
            selected = [
                segment for segment in segments
                if start - 1e-6 <= (segment.point1[0] + segment.point2[0]) / 2 <= end + 1e-6
            ]
            if selected:
                line_groups.append(
                    LineGroup(
                        component=component,
                        thickness=selected[0].thickness,
                        y=selected[0].y,
                        start=start,
                        end=end,
                        z=minimum,
                    )
                )
                line_groups[-1]._segments = selected  # type: ignore[attr-defined]
    line_groups.sort(key=lambda item: (item.component, -item.y, item.start))
    restraint_key = 1
    for line_key, line in enumerate(line_groups, start=1):
        line.key = line_key
        selected: list[FoundationSegment] = getattr(line, "_segments")  # type: ignore[attr-defined]
        line.restraints = []
        for local_name, segment in enumerate(selected, start=1):
            line.restraints.append(
                RestraintData(
                    **segment.__dict__,
                    key=restraint_key,
                    local_name=local_name,
                    line_key=line_key,
                )
            )
            restraint_key += 1
    node_c_by_node: dict[int, NodeCData] = {}
    for line in line_groups:
        for restraint in line.restraints:
            for node_key in (restraint.node1, restraint.node2):
                if node_key not in node_c_by_node:
                    node_c_by_node[node_key] = NodeCData(node_key, len(node_c_by_node) + 1, [])
                node_c_by_node[node_key].restraint_keys.append(restraint.key)
    for line in line_groups:
        for restraint in line.restraints:
            restraint.node_c1 = node_c_by_node[restraint.node1].key
            restraint.node_c2 = node_c_by_node[restraint.node2].key
    return RestraintTopology(line_groups=line_groups, node_cs=list(node_c_by_node.values()))


def mechanical_defaults(element: etree._Element, include_alignment: bool = False) -> None:
    attrs: dict[str, object] = {
        "MaterialKey": "0", "LoadConditionKey": "0", "Zg": "0", "H": "30",
        "U1mechBehaviourType": "Fixed", "K1": "-1",
        "U2mechBehaviourType": "Fixed", "K2": "-1",
        "U3mechBehaviourType": "Fixed", "K3": "-1",
        "R1mechBehaviourType": "Fixed", "Kr1": "-1",
        "R2mechBehaviourType": "Fixed", "Kr2": "-1",
        "R3mechBehaviourType": "Fixed", "Kr3": "-1",
        "MechanicalType": "Foundation", "K": "-1|-1|-1|-1|-1|-1",
        "MasterElementKey": "0", "MasterElementType": "None",
        "LayerKey": "0", "IsPropertyModified": "false",
    }
    if include_alignment:
        attrs.update({"Alignment": "Center", "Dy": "0"})
    set_attributes(element, attrs)


def make_geometry_line(archetype: etree._Element | None, line: LineGroup) -> etree._Element:
    element = clone(archetype, "GeometryLineRestraint")
    clear_children(element)
    element.attrib.clear()
    mechanical_defaults(element, True)
    first, last = line.restraints[0], line.restraints[-1]
    set_attributes(
        element,
        {
            "NodeKey1": last.node2,
            "NodeKey2": first.node1,
            "ParentKey": "1",
            "ParentType": "Bridge",
            "ParentEdge": "0",
            "B": fmt(line.thickness),
            "Key": line.key,
            "Name": line.key,
        },
    )
    keys = etree.SubElement(element, "RestraintKeys")
    for restraint in line.restraints:
        etree.SubElement(keys, "RestraintKey", Value=str(restraint.key))
    element.append(reference_system([[1, 0, 0], [0, 0, 1], [0, -1, 0]], last.point2))
    return element


def make_restraint(archetype: etree._Element | None, restraint: RestraintData) -> etree._Element:
    element = clone(archetype, "Restraint")
    afference = copy.deepcopy(first_direct(element, "AfferenceMatrices")) if first_direct(element, "AfferenceMatrices") is not None else etree.Element("AfferenceMatrices")
    clear_afference_values(afference)
    clear_children(element)
    element.attrib.clear()
    mechanical_defaults(element)
    p1, p2 = restraint.point1, restraint.point2
    half = restraint.thickness / 2
    set_attributes(
        element,
        {
            "ParentKey": restraint.line_key,
            "ParentTypeElement": "GeometryLineRestraint",
            "NodeCKey1": restraint.node_c1,
            "NodeCKey2": restraint.node_c2,
            "Type": "Line",
            "NodeKey1": restraint.node1,
            "NodeKey2": restraint.node2,
            "ComputationalElementKey": restraint.quad.key,
            "ComputationalElementType": "Quad",
            "ComputationalElementEdge": restraint.edge,
            "G": vec_text([(p1[0] + p2[0]) / 2, p1[1], p1[2]]),
            "Point1": vec_text([p1[0], p1[1] - half, p1[2]]),
            "Point2": vec_text([p2[0], p2[1] - half, p2[2]]),
            "Point3": vec_text([p2[0], p2[1] + half, p2[2]]),
            "Point4": vec_text([p1[0], p1[1] + half, p1[2]]),
            "Key": restraint.key,
            "Name": restraint.local_name,
        },
    )
    element.append(afference)
    element.append(reference_system([[1, 0, 0], [0, 0, 1], [0, -1, 0]], p1))
    return element


def make_node_c(archetype: etree._Element | None, node_c: NodeCData) -> etree._Element:
    element = clone(archetype, "NodeC")
    afference = copy.deepcopy(first_direct(element, "AfferenceMatrices")) if first_direct(element, "AfferenceMatrices") is not None else etree.Element("AfferenceMatrices")
    clear_afference_values(afference)
    clear_children(element)
    element.attrib.clear()
    set_attributes(
        element,
        {
            "NodeKey": node_c.node_key,
            "IsIndipendent": "true",
            "MasterElementKey": "0",
            "MasterElementType": "None",
            "LayerKey": "0",
            "IsPropertyModified": "false",
            "Key": node_c.key,
            "Name": node_c.key,
        },
    )
    element.append(afference)
    masters = etree.SubElement(element, "MasterElements")
    etree.SubElement(masters, "MasterElement", Key=str(node_c.node_key), Value="Node")
    slaves = etree.SubElement(element, "SlaveElements")
    for key in node_c.restraint_keys:
        etree.SubElement(slaves, "SlaveElement", Key=str(key), Value="Restraint")
    element.append(reference_system([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0]))
    return element


def make_key_list(parent: etree._Element, container_name: str, item_name: str, values: Iterable[int]) -> None:
    container = ensure_child(parent, container_name)
    clear_children(container)
    for value in values:
        etree.SubElement(container, item_name, Value=str(value))


def make_bridge(archetype: etree._Element | None, mesh: Mesh, tree: etree._ElementTree, topology: RestraintTopology) -> etree._Element:
    element = clone(archetype, "Bridge")
    all_x = [node.point[0] for node in mesh.nodes]
    wizard = first_direct(tree.getroot(), "WizardData")
    bridge_definition = first_direct(wizard, "BridgeDefinition")
    elevations_root = first_direct(wizard, "Elevations")
    elevation_list = first_direct(elevations_root, "Elevations")
    height = max((attr_float(item, "H1") for item in direct_children(elevation_list, "Elevation")), default=0.0)
    set_attributes(
        element,
        {
            "H": fmt(height),
            "B": fmt(attr_float(bridge_definition, "Width")),
            "L": fmt(max(all_x) - min(all_x) if all_x else 0),
            "MasterElementKey": "0",
            "MasterElementType": "None",
            "LayerKey": "0",
            "IsPropertyModified": "false",
            "Key": "1",
            "Name": "1",
        },
    )
    make_key_list(element, "VertexKeys", "VertexKeys", [])
    make_key_list(element, "SolidKeys", "SolidKeys", [])
    make_key_list(element, "TrussKeys", "TrussKeys", [])
    make_key_list(element, "QuadKeys", "QuadKeys", [quad.key for quad in mesh.quads])
    make_key_list(element, "GeometryLineRestraintKeys", "GeometryLineRestraintKeys", [line.key for line in topology.line_groups])
    make_key_list(element, "QuadSpanKeys", "QuadSpanKeys", [quad.key for quad in mesh.quads if "-arch" in quad.group])
    make_key_list(element, "SurfaceRestraints", "SurfaceRestraints", [])
    old_ref = first_direct(element, "ReferenceSystem")
    if old_ref is not None:
        element.replace(old_ref, reference_system([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0]))
    else:
        element.append(reference_system([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0]))
    return element


def find_geometry_insertion_reference(root: etree._Element) -> etree._Element | None:
    children = direct_children(root)
    first_index = next((index for index, child in enumerate(children) if child.tag in GEOMETRY_TAGS), -1)
    if first_index < 0:
        return next((child for child in children if child.tag == "ActionTable"), None)
    for child in children[first_index:]:
        if child.tag not in GEOMETRY_TAGS:
            return child
    return None


def material_keys(root: etree._Element) -> set[str]:
    return {
        item.get("Key")
        for item in direct_children(root, "Template")
        if "Material" in item.get("TypeOf", "") and item.get("Key")
    }


def list_values(parent: etree._Element, container_name: str) -> list[int]:
    container = first_direct(parent, container_name)
    values: list[int] = []
    for item in direct_children(container):
        try:
            values.append(int(item.get("Value", "")))
        except ValueError:
            continue
    return values


def validate_document(tree: etree._ElementTree, mesh: Mesh | None = None) -> ValidationReport:
    root = tree.getroot()
    errors: list[str] = []
    warnings: list[str] = []
    nodes = direct_children(root, "Node")
    model_points = direct_children(root, "ModelPoint")
    quads = direct_children(root, "Quad")
    restraints = direct_children(root, "Restraint")
    lines = direct_children(root, "GeometryLineRestraint")
    node_cs = direct_children(root, "NodeC")
    bridge = first_direct(root, "Bridge")

    def unique_keys(elements: list[etree._Element], label: str) -> set[int]:
        values: list[int] = []
        for item in elements:
            try:
                values.append(int(item.get("Key", "")))
            except ValueError:
                errors.append(f"{label}: one or more keys are missing or nonnumeric")
        if len(set(values)) != len(values):
            errors.append(f"{label}: duplicate keys found")
        return set(values)

    node_keys = unique_keys(nodes, "Nodes")
    mp_keys = unique_keys(model_points, "ModelPoints")
    quad_keys = unique_keys(quads, "Quads")
    restraint_keys = unique_keys(restraints, "Restraints")
    line_keys = unique_keys(lines, "Geometry line restraints")
    node_c_keys = unique_keys(node_cs, "NodeC objects")

    for quad in quads:
        for index in range(1, 5):
            try:
                key = int(quad.get(f"NodeKey{index}", ""))
            except ValueError:
                key = -1
            if key not in node_keys:
                errors.append(f"Quad {quad.get('Key')} references missing node {key}")
    for mp in model_points:
        try:
            key = int(mp.get("ElementKey", ""))
        except ValueError:
            key = -1
        if mp.get("ElementType") == "Node" and key not in node_keys:
            errors.append(f"ModelPoint {mp.get('Key')} references missing node {key}")

    if bridge is None:
        errors.append("Bridge object is missing")
    else:
        listed = list_values(bridge, "QuadKeys")
        if len(listed) != len(quads) or any(key not in quad_keys for key in listed):
            errors.append("Bridge/QuadKeys is incomplete or invalid")
        listed_lines = list_values(bridge, "GeometryLineRestraintKeys")
        if len(listed_lines) != len(lines) or any(key not in line_keys for key in listed_lines):
            errors.append("Bridge/GeometryLineRestraintKeys is incomplete or invalid")
        if any(key not in quad_keys for key in list_values(bridge, "QuadSpanKeys")):
            errors.append("Bridge/QuadSpanKeys contains invalid keys")

    for restraint in restraints:
        key = restraint.get("Key")
        for name in ("NodeKey1", "NodeKey2"):
            try:
                value = int(restraint.get(name, ""))
            except ValueError:
                value = -1
            if value not in node_keys:
                errors.append(f"Restraint {key} references missing node {value}")
        for name in ("NodeCKey1", "NodeCKey2"):
            try:
                value = int(restraint.get(name, ""))
            except ValueError:
                value = -1
            if value not in node_c_keys:
                errors.append(f"Restraint {key} references missing NodeC {value}")
        try:
            quad_key = int(restraint.get("ComputationalElementKey", ""))
        except ValueError:
            quad_key = -1
        if quad_key not in quad_keys:
            errors.append(f"Restraint {key} references missing quad {quad_key}")
        try:
            line_key = int(restraint.get("ParentKey", ""))
        except ValueError:
            line_key = -1
        if line_key not in line_keys:
            errors.append(f"Restraint {key} references missing geometry line {line_key}")

    for line in lines:
        key = line.get("Key")
        for name in ("NodeKey1", "NodeKey2"):
            try:
                value = int(line.get(name, ""))
            except ValueError:
                value = -1
            if value not in node_keys:
                errors.append(f"Geometry line {key} references missing node {value}")
        for value in list_values(line, "RestraintKeys"):
            if value not in restraint_keys:
                errors.append(f"Geometry line {key} references missing restraint {value}")

    for node_c in node_cs:
        key = node_c.get("Key")
        try:
            node_key = int(node_c.get("NodeKey", ""))
        except ValueError:
            node_key = -1
        if node_key not in node_keys:
            errors.append(f"NodeC {key} references missing node {node_key}")
        slaves = first_direct(node_c, "SlaveElements")
        for slave in direct_children(slaves, "SlaveElement"):
            if slave.get("Value") == "Restraint":
                try:
                    restraint_key = int(slave.get("Key", ""))
                except ValueError:
                    restraint_key = -1
                if restraint_key not in restraint_keys:
                    errors.append(f"NodeC {key} references missing restraint {restraint_key}")

    materials = material_keys(root)
    used = {quad.get("MaterialKey") for quad in quads if quad.get("MaterialKey") not in {None, "0"}}
    for key in used:
        if key not in materials:
            errors.append(f"Material key {key} is used by generated quads but absent from model.hrx")

    analyses = direct_children(root, "Analysis")
    analysis_keys = unique_keys(analyses, "Analyses")
    for analysis in analyses:
        active = first_direct(analysis, "ActiveModelPoints")
        listed_mp = [int(item.get("Key")) for item in direct_children(active, "ActiveModelPoint")]
        if set(listed_mp) != mp_keys:
            errors.append(f"Analysis {analysis.get('Name')} has incomplete ActiveModelPoints")

    if direct_children(root, "LoadElement"):
        errors.append("Stale LoadElement objects remain")
    if direct_children(root, "SurfaceRestraint"):
        warnings.append("SurfaceRestraint objects remain")
    if mesh and (len(nodes) != len(mesh.nodes) or len(quads) != len(mesh.quads)):
        errors.append("Serialized node/quad counts differ from the generated mesh")

    return ValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        counts={
            "nodes": len(nodes),
            "modelPoints": len(model_points),
            "quads": len(quads),
            "restraints": len(restraints),
            "geometryLineRestraints": len(lines),
            "nodeCs": len(node_cs),
            "analyses": len(analyses),
        },
    )


@dataclass
class HrxBuildResult:
    xml: bytes
    validation: ValidationReport
    model_points: list[ModelPointSelection]
    analyses: list[dict[str, Any]]
    removed_counts: dict[str, int]


class HrxBuilder:
    def build(self, tree: etree._ElementTree, mesh: Mesh, request: GenerationRequest) -> HrxBuildResult:
        root = tree.getroot()
        if root.get("WizardType") != "RailBridge":
            raise ValueError("model.hrx is not a RailBridge model")

        archetypes = {
            tag: copy.deepcopy(first_direct(root, tag))
            for tag in ("Node", "ModelPoint", "Quad", "Restraint", "GeometryLineRestraint", "NodeC", "Bridge")
        }
        removed_counts = {
            "modelPoints": len(direct_children(root, "ModelPoint")),
            "loadElements": len(direct_children(root, "LoadElement")),
            "surfaceRestraints": len(direct_children(root, "SurfaceRestraint")),
        }
        insertion_reference = find_geometry_insertion_reference(root)
        for child in list(root):
            if child.tag in GEOMETRY_TAGS:
                root.remove(child)
        insertion_index = root.index(insertion_reference) if insertion_reference is not None else len(root)

        selections = select_model_points(tree, mesh)
        model_point_node_keys = {selection.node_key for selection in selections}
        node_by_key = {node.key: node for node in mesh.nodes}
        generated: list[etree._Element] = []
        generated.extend(make_node(archetypes["Node"], node, model_point_node_keys) for node in mesh.nodes)
        generated.extend(
            make_model_point(archetypes["ModelPoint"], selection, index)
            for index, selection in enumerate(selections, start=1)
        )
        for quad in mesh.quads:
            points = [node_by_key[key].point for key in quad.node_keys]
            generated.append(make_quad(archetypes["Quad"], quad, points))

        topology = build_restraint_topology(mesh)
        for line in topology.line_groups:
            generated.extend(make_restraint(archetypes["Restraint"], item) for item in line.restraints)
        generated.extend(make_geometry_line(archetypes["GeometryLineRestraint"], line) for line in topology.line_groups)
        generated.extend(make_node_c(archetypes["NodeC"], node_c) for node_c in topology.node_cs)
        generated.append(make_bridge(archetypes["Bridge"], mesh, tree, topology))
        for offset, element in enumerate(generated):
            root.insert(insertion_index + offset, element)

        analyses = rebuild_analyses(root, request, selections)
        validation = validate_document(tree, mesh)
        validation.warnings.extend(
            [
                f"Removed {removed_counts['modelPoints']} old ModelPoint object(s)",
                f"Removed {removed_counts['loadElements']} old LoadElement object(s)",
                f"Removed {removed_counts['surfaceRestraints']} old SurfaceRestraint object(s)",
                "Analysis interface payloads are preserved in the work-job JSON but are not encoded as static HRX mutations",
            ]
        )
        xml = serialize(tree)
        reparsed = etree.ElementTree(etree.fromstring(xml, etree.XMLParser(huge_tree=True)))
        final_validation = validate_document(reparsed, mesh)
        final_validation.warnings.extend(validation.warnings)
        return HrxBuildResult(xml, final_validation, selections, analyses, removed_counts)
