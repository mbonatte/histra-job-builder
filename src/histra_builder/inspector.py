from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from lxml import etree

from .compiler import compile_job
from .errors import InvalidHrxError
from .models import JobSpec
from .templates import TemplateRegistry


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _children(root: etree._Element, name: str) -> Iterable[etree._Element]:
    return (child for child in root if isinstance(child.tag, str) and _local_name(child) == name)


def _vector(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    parts = raw.split(";")
    if len(parts) != 3:
        return None
    try:
        point = [float(part) for part in parts]
    except ValueError:
        return None
    return point if all(math.isfinite(value) for value in point) else None


def _float(raw: str | None, default: float = 0.0) -> float:
    try:
        value = float(raw) if raw not in (None, "") else default
    except ValueError:
        return default
    return value if math.isfinite(value) else default


def _signed_area_xz(points: list[list[float]]) -> float:
    return 0.5 * sum(
        points[i][0] * points[(i + 1) % 4][2] - points[(i + 1) % 4][0] * points[i][2]
        for i in range(4)
    )


@dataclass(frozen=True)
class HrxInspection:
    metadata: dict[str, Any]
    counts: dict[str, int]
    bounds: dict[str, list[float]] | None
    nodes: list[dict[str, Any]]
    quads: list[dict[str, Any]]
    groups: dict[str, int]
    materials: dict[str, int]
    warnings: list[str]
    validation: dict[str, Any]

    def as_dict(self, *, include_geometry: bool = True) -> dict[str, Any]:
        value = {
            "metadata": self.metadata,
            "counts": self.counts,
            "bounds": self.bounds,
            "groups": self.groups,
            "materials": self.materials,
            "warnings": self.warnings,
            "validation": self.validation,
        }
        if include_geometry:
            value.update({"nodes": self.nodes, "quads": self.quads})
        return value


def inspect_hrx(hrx_bytes: bytes, *, max_geometry_items: int | None = None) -> HrxInspection:
    if not hrx_bytes:
        raise InvalidHrxError("HRX input is empty")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False, huge_tree=True)
    try:
        root = etree.fromstring(hrx_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise InvalidHrxError(f"HRX is not valid XML: {exc}") from exc

    warnings: list[str] = []
    node_map: dict[int, list[float]] = {}
    nodes: list[dict[str, Any]] = []
    duplicate_nodes: list[int] = []
    for element in _children(root, "Node"):
        try:
            key = int(element.get("Key", ""))
        except ValueError:
            warnings.append("A Node with an invalid Key was ignored")
            continue
        point = _vector(element.get("Point"))
        if point is None:
            warnings.append(f"Node {key} has an invalid Point and was ignored")
            continue
        if key in node_map:
            duplicate_nodes.append(key)
            continue
        node_map[key] = point
        nodes.append({"key": key, "point": point})

    quads: list[dict[str, Any]] = []
    missing_refs: list[dict[str, Any]] = []
    repeated: list[int] = []
    zero_area: list[int] = []
    materials: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    for index, element in enumerate(_children(root, "Quad"), start=1):
        try:
            key = int(element.get("Key", str(index)))
            refs = [int(element.get(f"NodeKey{i}", "")) for i in range(1, 5)]
        except ValueError:
            warnings.append("A Quad with invalid key/reference attributes was ignored")
            continue
        missing = [ref for ref in refs if ref not in node_map]
        if missing:
            missing_refs.append({"quad": key, "nodes": missing})
        if len(set(refs)) != 4:
            repeated.append(key)
        if not missing and abs(_signed_area_xz([node_map[ref] for ref in refs])) <= 1e-10:
            zero_area.append(key)
        material = element.get("MaterialKey", "0")
        parent_type = element.get("ParentTypeElement", "Unknown")
        layer = int(_float(element.get("LayerKey"), 0))
        group = f"{parent_type}:layer-{layer}:material-{material}"
        thicknesses = [_float(element.get(f"Thickness{i}"), 0.0) for i in range(1, 5)]
        quad = {
            "key": key,
            "nodeKeys": refs,
            "materialKey": material,
            "layerKey": layer,
            "parentKey": int(_float(element.get("ParentKey"), 0)),
            "parentTypeElement": parent_type,
            "thickness": sum(thicknesses) / 4.0,
            "group": group,
        }
        quads.append(quad)
        materials[material] += 1
        groups[group] += 1

    bounds = None
    if nodes:
        points = [node["point"] for node in nodes]
        bounds = {
            "min": [min(point[i] for point in points) for i in range(3)],
            "max": [max(point[i] for point in points) for i in range(3)],
        }
    if not nodes:
        warnings.append("No generated Node geometry was found in the HRX")
    if not quads:
        warnings.append("No generated Quad geometry was found in the HRX")

    tag_counts = Counter(_local_name(element) for element in root.iter() if isinstance(element.tag, str))
    validation_errors: list[str] = []
    if duplicate_nodes:
        validation_errors.append(f"duplicate Node keys: {duplicate_nodes[:20]}")
    if missing_refs:
        validation_errors.append(f"{len(missing_refs)} Quad(s) reference missing nodes")
    if repeated:
        validation_errors.append(f"Quad(s) repeat node references: {repeated[:20]}")
    if zero_area:
        validation_errors.append(f"zero-area Quad(s): {zero_area[:20]}")
    validation = {
        "valid": not validation_errors,
        "errors": validation_errors,
        "duplicateNodeKeys": duplicate_nodes,
        "missingNodeReferences": missing_refs[:100],
        "repeatedNodeQuads": repeated[:100],
        "zeroAreaQuads": zero_area[:100],
    }
    metadata = {
        "root_tag": _local_name(root),
        "version": root.get("version", root.get("Version", "")),
        "wizard_type": root.get("WizardType", ""),
        "tag_counts": dict(sorted(tag_counts.items())),
    }
    if max_geometry_items is not None:
        nodes = nodes[:max_geometry_items]
        quads = quads[:max_geometry_items]
        if len(node_map) > len(nodes) or sum(materials.values()) > len(quads):
            warnings.append(f"Geometry response was truncated to {max_geometry_items} nodes/quads")
    return HrxInspection(
        metadata=metadata,
        counts={"nodes": len(node_map), "quads": sum(materials.values())},
        bounds=bounds,
        nodes=nodes,
        quads=quads,
        groups=dict(sorted(groups.items())),
        materials=dict(sorted(materials.items())),
        warnings=warnings,
        validation=validation,
    )


def preview_job(job: JobSpec | dict[str, Any], registry: TemplateRegistry) -> dict[str, Any]:
    artifact = compile_job(job, registry)
    preview = inspect_hrx(artifact.hrx_bytes).as_dict(include_geometry=True)
    preview["provenance"] = artifact.provenance
    return preview
