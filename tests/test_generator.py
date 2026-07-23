import json
from pathlib import Path

from lxml import etree

from app.mesh import generate_mesh
from app.schemas import GenerationRequest, MeshPatch
from app.service import GeneratorService
from app.template import TemplateRepository

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "templates" / "model.hrx"
EXAMPLE = ROOT / "example_input.json"


def test_template_mesh_matches_reference_counts():
    tree = TemplateRepository(TEMPLATE).load()
    mesh = generate_mesh(tree, MeshPatch())
    assert len(mesh.nodes) == 2900
    assert len(mesh.quads) == 2310


def test_complete_generation_is_referentially_valid():
    request = GenerationRequest.model_validate_json(EXAMPLE.read_text())
    result = GeneratorService(TEMPLATE).generate(request)
    assert result.validation.valid, result.validation.errors
    assert result.validation.counts["analyses"] == 3
    assert result.validation.counts["modelPoints"] == 27

    root = etree.fromstring(result.xml, etree.XMLParser(huge_tree=True))
    assert [a.get("Name") for a in root.findall("Analysis")] == ["Vert", "scour_1", "Modal_1"]
    assert all(
        state.get("State") == "NotExecutedToBeExecute"
        for analysis in root.findall("Analysis")
        for state in analysis.findall("./States/State")
    )
    assert root.find("ModelPoint[@Name='Pier_1_center_top']") is not None
    assert root.find("ModelPoint[@Name='Span_1_crown']") is not None
