from __future__ import annotations

from collections import Counter
from typing import Any

from lxml import etree

from .fingerprints import canonical_xml, xml_sha256
from .xml_utils import parse_xml


def _direct_counts(root: etree._Element) -> dict[str, int]:
    return dict(Counter(child.tag for child in root if isinstance(child.tag, str)))


def _material_signatures(root: etree._Element) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for element in root.findall("Template"):
        if "Material" in (element.get("TypeOf") or "") and element.get("Key"):
            result[element.get("Key")] = dict(element.attrib)
    return result


def _analysis_signatures(root: etree._Element) -> dict[str, bytes]:
    return {
        element.get("Name", f"#{index}"): canonical_xml(element)
        for index, element in enumerate(root.findall("Analysis"), start=1)
    }


def _node_coordinates(root: etree._Element, digits: int = 6) -> Counter[tuple[float, float, float]]:
    result: Counter[tuple[float, float, float]] = Counter()
    for node in root.findall("Node"):
        raw = node.get("Point")
        if not raw:
            continue
        values = tuple(round(float(item), digits) for item in raw.split(";"))
        if len(values) == 3:
            result[values] += 1
    return result


def _quad_signatures(root: etree._Element, digits: int = 6) -> Counter[tuple[Any, ...]]:
    nodes = {
        int(node.get("Key")): tuple(round(float(item), digits) for item in node.get("Point", "0;0;0").split(";"))
        for node in root.findall("Node")
        if node.get("Key")
    }
    result: Counter[tuple[Any, ...]] = Counter()
    for quad in root.findall("Quad"):
        try:
            points = [nodes[int(quad.get(f"NodeKey{i}"))] for i in range(1, 5)]
        except (KeyError, TypeError, ValueError):
            continue
        # Ignore starting corner and winding when comparing topology.
        rotations = []
        for sequence in (points, list(reversed(points))):
            rotations.extend(tuple(sequence[index:] + sequence[:index]) for index in range(4))
        canonical_points = min(rotations)
        thickness = tuple(round(float(quad.get(f"Thickness{i}", "0")), digits) for i in range(1, 5))
        result[(canonical_points, quad.get("MaterialKey"), quad.get("LayerKey"), thickness)] += 1
    return result


def compare_hrx(source: bytes, generated: bytes) -> dict[str, Any]:
    source_tree = parse_xml(source)
    generated_tree = parse_xml(generated)
    source_root = source_tree.getroot()
    generated_root = generated_tree.getroot()

    source_nodes = _node_coordinates(source_root)
    generated_nodes = _node_coordinates(generated_root)
    source_quads = _quad_signatures(source_root)
    generated_quads = _quad_signatures(generated_root)
    source_materials = _material_signatures(source_root)
    generated_materials = _material_signatures(generated_root)
    source_analyses = _analysis_signatures(source_root)
    generated_analyses = _analysis_signatures(generated_root)

    wizard_source = source_root.find("WizardData")
    wizard_generated = generated_root.find("WizardData")
    checks = {
        "byte_equal": source == generated,
        "canonical_xml_equal": canonical_xml(source_tree) == canonical_xml(generated_tree),
        "wizard_data_equal": (
            wizard_source is not None
            and wizard_generated is not None
            and canonical_xml(wizard_source) == canonical_xml(wizard_generated)
        ),
        "direct_counts_equal": _direct_counts(source_root) == _direct_counts(generated_root),
        "node_coordinates_equal": source_nodes == generated_nodes,
        "quad_geometry_equal": source_quads == generated_quads,
        "materials_equal": source_materials == generated_materials,
        "analyses_equal": source_analyses == generated_analyses,
    }
    geometry_match = checks["node_coordinates_equal"] and checks["quad_geometry_equal"]
    semantic_match = (
        checks["wizard_data_equal"]
        and geometry_match
        and checks["materials_equal"]
        and checks["analyses_equal"]
    )
    return {
        "match": bool(semantic_match),
        "geometry_match": bool(geometry_match),
        "exact_match": bool(checks["byte_equal"]),
        "checks": checks,
        "source": {
            "sha256": xml_sha256(source),
            "bytes": len(source),
            "counts": _direct_counts(source_root),
            "nodes": sum(source_nodes.values()),
            "quads": sum(source_quads.values()),
        },
        "generated": {
            "sha256": xml_sha256(generated),
            "bytes": len(generated),
            "counts": _direct_counts(generated_root),
            "nodes": sum(generated_nodes.values()),
            "quads": sum(generated_quads.values()),
        },
        "differences": {
            "missing_node_coordinates": sum((source_nodes - generated_nodes).values()),
            "extra_node_coordinates": sum((generated_nodes - source_nodes).values()),
            "missing_quads": sum((source_quads - generated_quads).values()),
            "extra_quads": sum((generated_quads - source_quads).values()),
            "material_keys_changed": sorted(
                key for key in set(source_materials) | set(generated_materials)
                if source_materials.get(key) != generated_materials.get(key)
            ),
            "analysis_names_changed": sorted(
                name for name in set(source_analyses) | set(generated_analyses)
                if source_analyses.get(name) != generated_analyses.get(name)
            ),
        },
    }
