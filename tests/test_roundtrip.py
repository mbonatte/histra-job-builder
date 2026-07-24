from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from lxml import etree

from app.import_hrx import imported_job_payload
from app.roundtrip import compare_hrx
from app.schemas import GenerationRequest
from app.service import GeneratorService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "app" / "templates" / "model.hrx"
MODEL1 = ROOT / "app" / "templates" / "imported" / "c2736ca1b816be3e0f1fc8989ad5a4b497fac4fc5399a0c09736058fc82575c6.hrx"


def imported_request(service: GeneratorService) -> tuple[bytes, dict]:
    source = MODEL1.read_bytes()
    payload = imported_job_payload(source, MODEL1.name, registry=service.registry)
    return source, payload


def test_model1_import_extracts_outlier_wizard_features():
    service = GeneratorService(DEFAULT_TEMPLATE)
    _source, payload = imported_request(service)

    assert len(payload["Geometry"]["Spans"]) == 4
    assert payload["Geometry"]["Spans"][0]["Tb"] == 70.0
    assert payload["Geometry"]["Spans"][0]["Tt"] == 40.0

    lanes = payload["Geometry"]["Lanes"]
    assert lanes[0]["Height"] == 50.0
    assert lanes[-1]["Height"] == 50.0

    assert payload["Geometry"]["Piers"][0]["w1"] == 50.0
    assert payload["Geometry"]["Piers"][1]["b1"] == 10.0

    layers = payload["Geometry"]["Elevations"]["Layers"]
    assert [layer["Tag"] for layer in layers] == ["Layer1", "Layer2", "Layer3"]
    assert payload["Geometry"]["Elevations"]["Elevations"][0]["H2"] == 390.0


def test_model1_hrx_job_hrx_roundtrip_is_byte_exact():
    service = GeneratorService(DEFAULT_TEMPLATE)
    source, payload = imported_request(service)
    request = GenerationRequest.model_validate(payload)

    preview = service.preview(request)
    assert len(preview.mesh["nodes"]) == 3235
    assert len(preview.mesh["quads"]) == 2614

    result = service.generate(request)
    assert result.validation.valid, result.validation.errors
    assert result.xml == source

    comparison = compare_hrx(source, result.xml)
    assert comparison["exact_match"] is True
    assert comparison["match"] is True


def test_material_edit_preserves_imported_geometry():
    service = GeneratorService(DEFAULT_TEMPLATE)
    source, payload = imported_request(service)
    edited = deepcopy(payload)
    arch = next(item for item in edited["Materials"] if item["Key"] == "18")
    arch["Ehor"] = "999.25"

    result = service.generate(GenerationRequest.model_validate(edited))
    assert result.validation.valid, result.validation.errors
    comparison = compare_hrx(source, result.xml)
    assert comparison["exact_match"] is False
    assert comparison["checks"]["node_coordinates_equal"] is True
    assert comparison["checks"]["quad_geometry_equal"] is True
    assert comparison["checks"]["materials_equal"] is False
    assert comparison["checks"]["analyses_equal"] is True


def test_geometry_edit_switches_to_python_mesher_and_remains_valid():
    service = GeneratorService(DEFAULT_TEMPLATE)
    _source, payload = imported_request(service)
    edited = deepcopy(payload)
    edited["Geometry"]["Spans"][0]["f"] = 210.0

    result = service.generate(GenerationRequest.model_validate(edited))
    assert result.validation.valid, result.validation.errors
    assert result.validation.counts["quads"] > 0
    assert result.validation.counts["modelPoints"] > 0
    assert any("b1/b3/w1/w3 variation" in warning for warning in result.validation.warnings)


def test_target_mesh_101_preserves_reference_histra_topology():
    service = GeneratorService(DEFAULT_TEMPLATE)
    source = (ROOT / "tests" / "fixtures" / "Model1.hrx").read_bytes()
    payload = imported_job_payload(source, "Model1.hrx", registry=service.registry)
    payload["Geometry"]["BridgeDefinition"]["Nl"] = 101

    request = GenerationRequest.model_validate(payload)
    preview = service.preview(request)
    assert len(preview.mesh["nodes"]) == 3286
    assert len(preview.mesh["quads"]) == 2644
    assert any("target-size discretisation signature is unchanged" in warning for warning in preview.warnings)

    result = service.generate(request)
    assert result.validation.valid, result.validation.errors
    generated = etree.fromstring(result.xml, etree.XMLParser(huge_tree=True))
    bridge = generated.find("./WizardData/BridgeDefinition")
    advanced = generated.find("./AdvancedOptionsDefault")
    assert bridge is not None and bridge.get("Nl") in {"101", "101.0"}
    assert advanced is not None
    assert advanced.get("ArcoMesherQuadLengthMax") in {"101", "101.0"}
    assert advanced.get("WallMesherQuadLengthMax") in {"101", "101.0"}

    reference = (ROOT / "tests" / "fixtures" / "Model1_101.hrx").read_bytes()
    comparison = compare_hrx(reference, result.xml)
    assert comparison["checks"]["direct_counts_equal"] is True
    assert comparison["checks"]["node_coordinates_equal"] is True
    assert comparison["checks"]["quad_geometry_equal"] is True
    assert comparison["checks"]["materials_equal"] is True
    assert comparison["checks"]["analyses_equal"] is True
