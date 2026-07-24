from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Iterable

from lxml import etree

from .mesh import Mesh, Node, Quad
from .xml_utils import attr_float, direct_children, first_direct, parse_vector, set_attributes, vec_text


@dataclass
class ModelPointSelection:
    name: str
    node_key: int
    point: list[float]
    target: list[float]
    distance: float
    component: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "nodeKey": self.node_key,
            "point": self.point,
            "target": self.target,
            "distance": self.distance,
            "component": self.component,
        }


def _group_node_keys(mesh: Mesh, predicate) -> set[int]:
    keys: set[int] = set()
    for quad in mesh.quads:
        if predicate(quad):
            keys.update(quad.node_keys)
    return keys


def _closest(nodes_by_key: dict[int, Node], allowed: set[int], target: list[float]) -> tuple[Node, float]:
    candidates = [nodes_by_key[key] for key in allowed if key in nodes_by_key]
    if not candidates:
        candidates = list(nodes_by_key.values())
    node = min(candidates, key=lambda item: math.dist(item.point, target))
    return node, math.dist(node.point, target)


def select_model_points(tree: etree._ElementTree, mesh: Mesh) -> list[ModelPointSelection]:
    root = tree.getroot()
    wizard = first_direct(root, "WizardData")
    if wizard is None:
        return []
    nodes_by_key = {node.key: node for node in mesh.nodes}
    selections: list[ModelPointSelection] = []
    piers = direct_children(wizard, "Pier")

    for pier_index, pier in enumerate(piers, start=1):
        ref = first_direct(pier, "ReferenceSystem")
        x, y, z = parse_vector(ref.get("Origin") if ref is not None else None)
        height = attr_float(pier, "H")
        pier_width = attr_float(pier, "w2")
        foundation_height = attr_float(pier, "Hf")
        foundation_width = attr_float(pier, "W1f") + pier_width + attr_float(pier, "W3f")
        pier_top = z
        pier_bottom = z - height
        foundation_top = pier_bottom
        foundation_bottom = foundation_top - foundation_height

        shaft_keys = _group_node_keys(
            mesh,
            lambda quad, sequence=2 * pier_index: quad.group == f"pier-{sequence}-shaft",
        )
        foundation_keys = _group_node_keys(
            mesh,
            lambda quad, sequence=2 * pier_index: quad.group == f"pier-{sequence}-foundation",
        )

        locations = {
            f"Pier_{pier_index}_center_top": ([x, y, pier_top], shaft_keys, f"pier_{pier_index}"),
            f"Pier_{pier_index}_upstream_top": ([x, y - pier_width / 2, pier_top], shaft_keys, f"pier_{pier_index}"),
            f"Pier_{pier_index}_downstream_top": ([x, y + pier_width / 2, pier_top], shaft_keys, f"pier_{pier_index}"),
            f"Pier_{pier_index}_center_bottom": ([x, y, pier_bottom], shaft_keys, f"pier_{pier_index}"),
            f"Pier_{pier_index}_upstream_bottom": ([x, y - pier_width / 2, pier_bottom], shaft_keys, f"pier_{pier_index}"),
            f"Pier_{pier_index}_downstream_bottom": ([x, y + pier_width / 2, pier_bottom], shaft_keys, f"pier_{pier_index}"),
            f"Foundation_{pier_index}_center_top": ([x, y, foundation_top], foundation_keys, f"foundation_{pier_index}"),
            f"Foundation_{pier_index}_upstream_top": ([x, y - foundation_width / 2, foundation_top], foundation_keys, f"foundation_{pier_index}"),
            f"Foundation_{pier_index}_downstream_top": ([x, y + foundation_width / 2, foundation_top], foundation_keys, f"foundation_{pier_index}"),
            f"Foundation_{pier_index}_center_bottom": ([x, y, foundation_bottom], foundation_keys, f"foundation_{pier_index}"),
            f"Foundation_{pier_index}_upstream_bottom": ([x, y - foundation_width / 2, foundation_bottom], foundation_keys, f"foundation_{pier_index}"),
            f"Foundation_{pier_index}_downstream_bottom": ([x, y + foundation_width / 2, foundation_bottom], foundation_keys, f"foundation_{pier_index}"),
        }
        for name, (target, allowed, component) in locations.items():
            node, distance = _closest(nodes_by_key, allowed, target)
            selections.append(ModelPointSelection(name, node.key, node.point, target, distance, component))

    for span_meta in mesh.metadata.get("spans", []):
        index = int(span_meta["index"]) + 1
        target = [float(span_meta["centerX"]), 0.0, float(span_meta["springZ"]) + _span_rise(wizard, index)]
        allowed = _group_node_keys(mesh, lambda quad, index=index: quad.group == f"span-{index}-arch")
        node, distance = _closest(nodes_by_key, allowed, target)
        selections.append(ModelPointSelection(f"Span_{index}_crown", node.key, node.point, target, distance, f"span_{index}"))

    return selections


def _span_rise(wizard: etree._Element, one_based_index: int) -> float:
    spans = direct_children(wizard, "Span")
    return attr_float(spans[one_based_index - 1], "f") if one_based_index <= len(spans) else 0.0


def make_model_point(archetype: etree._Element | None, selection: ModelPointSelection, key: int) -> etree._Element:
    element = copy.deepcopy(archetype) if archetype is not None else etree.Element("ModelPoint")
    for child in list(element):
        element.remove(child)
    element.attrib.clear()
    set_attributes(
        element,
        {
            "IdElement": selection.node_key,
            "Ux": "0", "Uy": "0", "Uz": "0",
            "Vx": "0", "Vy": "0", "Vz": "0",
            "Ax": "0", "Ay": "0", "Az": "0",
            "ElementType": "Node",
            "ParentKey": key,
            "ParentElementKey": "0",
            "ParentElementType": "None",
            "Description": selection.name,
            "IdVertex": "0",
            "ElementKey": selection.node_key,
            "Mass": "0",
            "Point": vec_text(selection.point),
            "AnalysisKey": "0",
            "Combination": "0",
            "Step": "0",
            "Key": key,
            "Name": selection.name,
        },
    )
    return element


def existing_model_points(tree: etree._ElementTree) -> list[ModelPointSelection]:
    """Return existing HRX model points as selections for reports/previews."""

    result: list[ModelPointSelection] = []
    for index, element in enumerate(direct_children(tree.getroot(), "ModelPoint"), start=1):
        raw_point = element.get("Point") or "0;0;0"
        point = parse_vector(raw_point)
        node_key_raw = element.get("ElementKey") or element.get("IdElement") or "0"
        try:
            node_key = int(node_key_raw)
        except ValueError:
            node_key = 0
        name = element.get("Name") or element.get("Description") or f"ModelPoint_{index}"
        result.append(
            ModelPointSelection(
                name=name,
                node_key=node_key,
                point=point,
                target=list(point),
                distance=0.0,
                component="imported",
            )
        )
    return result
