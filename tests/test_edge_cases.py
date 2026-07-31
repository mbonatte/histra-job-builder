from __future__ import annotations

from pathlib import Path
import pytest
from lxml import etree
from pydantic import ValidationError

from histra_builder import (
    InvalidJobError,
    JobSpec,
    PatchError,
    TemplateIntegrityError,
    TemplateNotFoundError,
    TemplateRegistry,
    VariantError,
    compile_job,
    generate_variants,
    inspect_hrx,
    job_from_hrx,
)
from histra_builder.canonical import canonical_json_bytes, job_sha256, sha256_hex


def base_document(hrx_bytes, registry):
    return job_from_hrx(hrx_bytes, job_id="base", template_id="railbridge-base", registry=registry).model_dump(mode="json")


def test_canonical_helpers_are_stable():
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert sha256_hex(b"x") == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    assert job_sha256({"a": 1}) == sha256_hex(b'{"a":1}')


@pytest.mark.parametrize("output", ["", "/model.hrx", "../model.hrx", "folder/", r"folder\\model.hrx", "model.xml"])
def test_rejects_unsafe_output_paths(hrx_bytes, registry, output):
    document = base_document(hrx_bytes, registry)
    document["model"]["output_path"] = output
    with pytest.raises(ValidationError):
        JobSpec.model_validate(document)


@pytest.mark.parametrize(
    "patch",
    [
        {"op": "set_attribute", "xpath": "/RailBridge"},
        {"op": "set_text", "xpath": "/RailBridge"},
        {"op": "replace_xml", "xpath": "/RailBridge"},
        {"op": "append_xml", "xpath": "/RailBridge"},
    ],
)
def test_patch_operand_validation(hrx_bytes, registry, patch):
    document = base_document(hrx_bytes, registry)
    document["model"]["patches"] = [patch]
    with pytest.raises(InvalidJobError):
        compile_job(document, registry)


def test_all_patch_operations(hrx_bytes, registry):
    document = base_document(hrx_bytes, registry)
    document["model"]["patches"] = [
        {"op": "set_text", "xpath": "/RailBridge/WizardData/BridgeDefinition", "value": "marker"},
        {"op": "append_xml", "xpath": "/RailBridge/WizardData", "xml": '<Extra Key="1" />'},
        {"op": "replace_xml", "xpath": "/RailBridge/WizardData/Extra", "xml": '<Extra Key="2" />'},
        {"op": "delete", "xpath": "/RailBridge/WizardData/Extra"},
    ]
    root = etree.fromstring(compile_job(document, registry).hrx_bytes)
    assert root.xpath("/RailBridge/WizardData/BridgeDefinition")[0].text == "marker"
    assert not root.xpath("/RailBridge/WizardData/Extra")


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"op": "set_text", "xpath": "//*[" , "value": "x"}, "invalid XPath"),
        ({"op": "set_text", "xpath": "/RailBridge/Missing", "value": "x"}, "matched no nodes"),
        ({"op": "set_text", "xpath": "/RailBridge/@version", "value": "x"}, "must select XML elements"),
        ({"op": "delete", "xpath": "/RailBridge"}, "cannot delete"),
        ({"op": "replace_xml", "xpath": "/RailBridge", "xml": "<Other/>"}, "cannot replace"),
        ({"op": "append_xml", "xpath": "/RailBridge", "xml": "<broken>"}, "invalid XML fragment"),
    ],
)
def test_patch_errors(hrx_bytes, registry, patch, message):
    document = base_document(hrx_bytes, registry)
    document["model"]["patches"] = [patch]
    with pytest.raises(PatchError, match=message):
        compile_job(document, registry)


def test_invalid_job_and_invalid_template(registry):
    with pytest.raises(InvalidJobError):
        compile_job({}, registry)
    asset = registry.register("broken", b"<broken>")
    document = {
        "schema_version": "1.0", "job_id": "broken", "workflow": {}, "metadata": {},
        "model": {"output_path": "model.hrx", "template": {"id": "broken", "sha256": asset.sha256},
                  "patches": [{"op": "set_text", "xpath": "/broken", "value": "x"}]},
    }
    with pytest.raises(InvalidJobError, match="not valid XML"):
        compile_job(document, registry)


def test_registry_errors_and_metadata(tmp_path):
    registry = TemplateRegistry(tmp_path)
    with pytest.raises(TemplateNotFoundError):
        registry.path_for("bad/id")
    with pytest.raises(TemplateNotFoundError):
        registry.load("missing", "0" * 64)
    with pytest.raises(TemplateIntegrityError):
        registry.register("empty", b"")
    asset = registry.register("asset", b"data")
    assert asset.as_dict() == {"id": "asset", "sha256": asset.sha256, "size_bytes": 4}
    with pytest.raises(TemplateIntegrityError, match="digest mismatch"):
        registry.load("asset", "0" * 64)
    overwritten = registry.register("asset", b"other", overwrite=True)
    assert overwritten.data == b"other"


def test_inspection_reports_bad_geometry_and_truncation():
    data = b'''<RailBridge version="x">
      <Node Key="bad" Point="0;0;0"/><Node Key="1" Point="bad"/>
      <Node Key="2" Point="0;0;0"/><Node Key="2" Point="1;0;0"/>
      <Node Key="3" Point="1;0;0"/><Node Key="4" Point="2;0;0"/>
      <Quad Key="1" NodeKey1="2" NodeKey2="3" NodeKey3="4" NodeKey4="99"/>
      <Quad Key="2" NodeKey1="2" NodeKey2="2" NodeKey3="3" NodeKey4="4"/>
      <Quad Key="bad" NodeKey1="2" NodeKey2="3" NodeKey3="4" NodeKey4="x"/>
    </RailBridge>'''
    value = inspect_hrx(data, max_geometry_items=1)
    assert value.validation["valid"] is False
    assert value.validation["duplicateNodeKeys"] == [2]
    assert value.validation["missingNodeReferences"][0]["nodes"] == [99]
    assert value.validation["repeatedNodeQuads"] == [2]
    assert value.validation["zeroAreaQuads"] == [2]
    assert any("invalid" in item for item in value.warnings)
    assert any("truncated" in item for item in value.warnings)
    assert "nodes" not in value.as_dict(include_geometry=False)


def test_inspection_without_generated_geometry():
    value = inspect_hrx(b'<RailBridge WizardType="Bridge"><WizardData/></RailBridge>')
    assert value.bounds is None
    assert value.counts == {"nodes": 0, "quads": 0}
    assert len(value.warnings) == 2


def test_variant_errors_and_list_changes(hrx_bytes, registry):
    base = base_document(hrx_bytes, registry)
    base["model"]["patches"] = [{"op": "set_attribute", "xpath": "/RailBridge", "attribute": "version", "value": "1"}]
    jobs = generate_variants(base, {"variants": [{"job_id": "v2", "changes": [{"path": "/model/patches/0/value", "value": "2"}]}]})
    assert jobs[0].model.patches[0].value == "2"
    with pytest.raises(VariantError, match="duplicate variant"):
        generate_variants(base, {"variants": [{"job_id": "x"}, {"job_id": "x"}]})
    for path in ["", "/job_id", "/schema_version"]:
        with pytest.raises((VariantError, ValidationError)):
            generate_variants(base, {"variants": [{"job_id": "x", "changes": [{"path": path, "value": 1}]}]})
    with pytest.raises(VariantError, match="invalid list index"):
        generate_variants(base, {"variants": [{"job_id": "x", "changes": [{"path": "/model/patches/nope/value", "value": 1}]}]})
    with pytest.raises(VariantError, match="valid JOB"):
        generate_variants(base, {"variants": [{"job_id": "bad id"}]})
