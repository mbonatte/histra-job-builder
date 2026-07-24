from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from lxml import etree


def _normalize(value: Any) -> Any:
    """Return a stable JSON-compatible representation.

    Numeric values are normalized so 100, 100.0 and "100" do not create
    different fingerprints when they represent the same imported XML value.
    Non-numeric strings are preserved verbatim.
    """

    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            return int(number)
        return float(f"{number:.15g}")
    if isinstance(value, str):
        stripped = value.strip()
        lower = stripped.lower()
        if lower in {"true", "false"}:
            return lower
        try:
            number = float(stripped)
        except ValueError:
            return value
        if number.is_integer():
            return int(number)
        return float(f"{number:.15g}")
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(by_alias=True, exclude_none=True))
    return str(value)


def json_fingerprint(value: Any) -> str:
    payload = json.dumps(_normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def xml_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_xml(element_or_tree: etree._Element | etree._ElementTree) -> bytes:
    element = element_or_tree.getroot() if isinstance(element_or_tree, etree._ElementTree) else element_or_tree
    return etree.tostring(element, method="c14n", exclusive=False, with_comments=False)


def xml_fingerprint(element_or_tree: etree._Element | etree._ElementTree) -> str:
    return hashlib.sha256(canonical_xml(element_or_tree)).hexdigest()


def geometry_payload(request: Any) -> dict[str, Any]:
    return {
        "Geometry": request.Geometry.model_dump(by_alias=True, exclude_none=True),
        "Mesh": request.Mesh.model_dump(by_alias=True, exclude_none=True),
    }


def materials_payload(request: Any) -> Any:
    return request.Materials


def analyses_payload(request: Any) -> dict[str, Any]:
    analyses: list[dict[str, Any]] = []
    for item in request.analyses:
        values = item.model_dump(by_alias=True, exclude_none=True)
        # Runner-only values do not alter the HRX document.
        for key in ("timeout_seconds", "interfaces", "outputs"):
            values.pop(key, None)
        analyses.append(values)
    return {
        "analyses": analyses,
        "AnalysisParameters": request.AnalysisParameters.model_dump(by_alias=True, exclude_none=True),
    }


def config_payload(request: Any) -> Any:
    return request.advanced_options.model_dump(by_alias=True, exclude_none=True)


def request_section_fingerprints(request: Any) -> dict[str, str]:
    geometry = json_fingerprint(geometry_payload(request))
    materials = json_fingerprint(materials_payload(request))
    analyses = json_fingerprint(analyses_payload(request))
    config = json_fingerprint(config_payload(request))
    complete = json_fingerprint(
        {
            "geometry": geometry,
            "materials": materials,
            "analyses": analyses,
            "config": config,
        }
    )
    return {
        "geometry": geometry,
        "materials": materials,
        "analyses": analyses,
        "config": config,
        "hrx": complete,
    }


def _semantic_xml_payload(element: etree._Element, *, ignored_attributes: set[str] | None = None) -> Any:
    ignored = ignored_attributes or set()
    return {
        "tag": str(element.tag),
        "attributes": _normalize(
            {key: value for key, value in element.attrib.items() if key not in ignored}
        ),
        "children": [
            _semantic_xml_payload(child, ignored_attributes=ignored)
            for child in element
            if isinstance(child.tag, str)
        ],
    }


def wizard_geometry_fingerprint(
    tree: etree._ElementTree,
    *,
    ignore_target_mesh: bool = False,
) -> str:
    """Fingerprint WizardData with numeric/string normalization.

    Imported JSON is validated by Pydantic, so values such as ``100`` and
    ``100.0`` can be serialized differently when written back to XML.  This
    semantic representation ignores those harmless formatting differences.
    """

    root = tree.getroot()
    wizard = root.find("./WizardData")
    if wizard is None:
        raise ValueError("HRX does not contain WizardData")
    ignored = {"Nl"} if ignore_target_mesh else set()
    return json_fingerprint(_semantic_xml_payload(wizard, ignored_attributes=ignored))


def mesh_geometry_fingerprint(mesh: Any, precision: int = 8) -> str:
    """Return a numbering-independent fingerprint of generated mesh geometry."""

    node_points = {
        int(node.key): tuple(round(float(value), precision) for value in node.point)
        for node in mesh.nodes
    }
    canonical_quads: list[Any] = []
    for quad in mesh.quads:
        points = [node_points[int(key)] for key in quad.node_keys]
        candidates = []
        for sequence in (points, list(reversed(points))):
            for offset in range(4):
                candidates.append(tuple(sequence[offset:] + sequence[:offset]))
        canonical_quads.append(
            (
                min(candidates),
                str(quad.material_key),
                int(quad.layer_key),
                round(float(quad.thickness), precision),
                str(quad.group),
                quad.transverse_band_index,
                str(quad.transverse_role or ""),
            )
        )
    return json_fingerprint(
        {
            "nodes": sorted(node_points.values()),
            "quads": sorted(canonical_quads, key=repr),
        }
    )
