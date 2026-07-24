from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from lxml import etree

from .fingerprints import request_section_fingerprints, xml_sha256
from .schemas import GenerationRequest
from .template import TemplateRegistry
from .xml_utils import direct_children, first_direct, parse_vector, parse_xml


def _safe_job_id(filename: str) -> str:
    stem = Path(filename).stem or "imported-model"
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "imported-model"
    if not value[0].isalnum():
        value = f"model-{value}"
    return value[:128]


def _attributes(element: etree._Element | None) -> dict[str, Any]:
    return dict(element.attrib) if element is not None else {}


def _support_payload(element: etree._Element) -> dict[str, Any]:
    payload = _attributes(element)
    reference = first_direct(element, "ReferenceSystem")
    if reference is not None and reference.get("Origin"):
        payload["Origin"] = parse_vector(reference.get("Origin"))
    return payload


def _material_payload(root: etree._Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for template in direct_children(root, "Template"):
        if "Material" not in (template.get("TypeOf") or ""):
            continue
        if not template.get("Key") or not template.get("Name"):
            continue
        result.append(dict(template.attrib))
    return result


def _analysis_outputs(analysis: etree._Element) -> dict[str, Any]:
    analysis_type = analysis.get("AnalysisType")
    if analysis_type == "5":
        return {"modal_contributions": {"enabled": False, "top_n": 3}}
    return {
        "displacements": {"enabled": True, "all_steps": True, "model_point_ids": []},
        "reactions": {"enabled": True, "all_steps": True},
    }


def _analysis_payload(root: etree._Element) -> list[dict[str, Any]]:
    analyses: list[dict[str, Any]] = []
    for analysis in direct_children(root, "Analysis"):
        payload: dict[str, Any] = {
            "name": analysis.get("Name") or f"Analysis_{len(analyses) + 1}",
            "timeout_seconds": 50,
            "interfaces": {},
            "outputs": _analysis_outputs(analysis),
        }
        for key, value in analysis.attrib.items():
            if key in {"Key", "Name"}:
                continue
            payload[key] = value
        analyses.append(payload)
    if not analyses:
        analyses.append({"name": "Vert", "timeout_seconds": 50, "interfaces": {}, "outputs": {}})
    return analyses


def _scour_payload(materials: list[dict[str, Any]]) -> dict[str, Any]:
    names = {str(item.get("Name", "")) for item in materials}
    candidates = [name for name in ("Foundation_Soil", "Soil") if name in names]
    removed = "Soil_removed" if "Soil_removed" in names else None
    return {
        "foundation_interface_materials": candidates,
        "scoured_foundation_interface_material": removed,
    }


def _geometry_payload(root: etree._Element) -> dict[str, Any]:
    wizard = first_direct(root, "WizardData")
    if wizard is None:
        raise ValueError("The HRX does not contain WizardData")
    bridge = first_direct(wizard, "BridgeDefinition")
    if bridge is None:
        raise ValueError("WizardData does not contain BridgeDefinition")

    lane_root = first_direct(bridge, "Corsie")
    lanes: list[dict[str, Any]] = []
    for index, lane in enumerate(direct_children(lane_root, "Corsia")):
        payload = dict(lane.attrib)
        payload.setdefault("Key", str(index))
        payload.setdefault("Name", f"Lane_{index + 1}")
        payload.setdefault("Width", "1")
        payload.setdefault("MaterialKey", "0")
        lanes.append(payload)

    elevations_root = first_direct(wizard, "Elevations")
    elevation_list = first_direct(elevations_root, "Elevations")
    elevations = [dict(item.attrib) for item in direct_children(elevation_list, "Elevation")]
    if not elevations:
        elevations = [{"X": 0, "H1": 0, "H2": 0, "H3": 0}]
    layers = []
    for child in direct_children(elevations_root):
        if child.tag.startswith("Layer"):
            layer = {"Tag": child.tag, **dict(child.attrib)}
            layers.append(layer)

    return {
        "BridgeDefinition": dict(bridge.attrib),
        "Lanes": lanes or None,
        "Abutments": [_support_payload(item) for item in direct_children(wizard, "Abutment")],
        "Piers": [_support_payload(item) for item in direct_children(wizard, "Pier")],
        "Spans": [dict(item.attrib) for item in direct_children(wizard, "Span")],
        "Elevations": {"Elevations": elevations, "Layers": layers},
    }


def _advanced_options(root: etree._Element) -> dict[str, Any]:
    options = first_direct(root, "AdvancedOptionsDefault")
    return dict(options.attrib) if options is not None else {}


def imported_job_payload(
    data: bytes,
    source_filename: str,
    *,
    registry: TemplateRegistry,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Import an HRX as an editable work-job JSON document.

    The source HRX is registered as a template.  An unchanged imported job can
    therefore be reproduced byte-for-byte, while edits can selectively preserve
    the source geometry or trigger the Python mesher.
    """

    tree = parse_xml(data)
    root = tree.getroot()
    if root.get("WizardType") != "RailBridge":
        raise ValueError("Only RailBridge HRX files can currently be imported")

    template_path, digest = registry.import_bytes(data, source_filename)
    materials = _material_payload(root)
    resolved_job_id = _safe_job_id(job_id or source_filename)
    relative_template = registry.relative_name(template_path)

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": resolved_job_id,
        "model": {
            "path": f"{resolved_job_id}.hrx",
            "template_path": relative_template,
            "source_sha256": digest,
        },
        "mesh": {"enabled": False, "analysis_name": "StartMesh", "timeout_seconds": 900},
        "scour": _scour_payload(materials),
        "analyses": _analysis_payload(root),
        "validation": {
            "require_completed_state": True,
            "require_results_database": True,
            "minimum_results_bytes": 1,
        },
        "metadata": {
            "scenario_id": resolved_job_id,
            "imported_from": source_filename,
            "imported_hrx_version": root.get("version"),
            "imported_wizard_type": root.get("WizardType"),
        },
        "Geometry": _geometry_payload(root),
        "Materials": materials,
        "AnalysisParameters": {"Defaults": {}, "ByName": {}},
        "Config": _advanced_options(root),
        "Mesh": {
            "NodeTolerance": 1e-5,
            "ArcDivisionMode": "observed-even",
            "PreserveImportedGeometry": True,
        },
    }

    # Validate once before recording the stable section fingerprints.  Pydantic
    # normalizes known numeric fields, which makes later comparisons robust to
    # JSON number/string representation differences.
    request = GenerationRequest.model_validate(copy.deepcopy(payload))
    fingerprints = request_section_fingerprints(request)
    payload["model"]["imported"] = {
        "template_path": relative_template,
        "source_filename": source_filename,
        "source_sha256": xml_sha256(data),
        "fingerprints": fingerprints,
        "preserve_exact_if_unchanged": True,
        "preserve_geometry_if_unchanged": True,
        "preserve_analyses_if_unchanged": True,
        "preserve_model_points_if_unchanged": True,
    }
    return GenerationRequest.model_validate(payload).model_dump(by_alias=True, exclude_none=True)
