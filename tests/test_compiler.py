from lxml import etree
import pytest

from histra_builder.compiler import BUILDER_VERSION, compile_job
from histra_builder.errors import PatchError


def parse(data: bytes):
    return etree.fromstring(data)


def test_no_patches_preserves_exact_template_bytes(registry, base_job, template_bytes):
    artifact = compile_job(base_job, registry)
    assert artifact.hrx_bytes == template_bytes
    assert artifact.provenance["template_id"] == "base"
    assert artifact.provenance["builder_version"] == BUILDER_VERSION == "1.1.0"
    assert artifact.provenance["hrx_sha256"] == artifact.hrx_sha256


def test_compilation_is_deterministic(registry, base_job):
    base_job["model"]["patches"] = [
        {
            "op": "set_attribute",
            "xpath": "//Span[@id='main']",
            "attribute": "length",
            "value": 28.5,
        }
    ]
    first = compile_job(base_job, registry)
    second = compile_job(base_job, registry)
    assert first.hrx_bytes == second.hrx_bytes
    assert first.provenance == second.provenance


def test_all_patch_operations(registry, base_job):
    base_job["model"]["patches"] = [
        {
            "op": "set_attribute",
            "xpath": "//Span[@id='main']",
            "attribute": "length",
            "value": 31.25,
        },
        {
            "op": "set_text",
            "xpath": "//Material[@id='concrete']/YoungModulus",
            "value": "32000000000",
        },
        {"op": "delete", "xpath": "//Material[@id='steel']"},
        {
            "op": "replace_xml",
            "xpath": "//Analysis[@id='dead-load']",
            "xml": "<Analysis id='modal' type='modal'/>",
        },
        {
            "op": "append_xml",
            "xpath": "//Materials",
            "xml": "<Material id='timber'><YoungModulus>12000000000</YoungModulus></Material>",
        },
    ]
    root = parse(compile_job(base_job, registry).hrx_bytes)
    assert root.xpath("string(//Span/@length)") == "31.25"
    assert root.xpath("string(//Material[@id='concrete']/YoungModulus)") == "32000000000"
    assert not root.xpath("//Material[@id='steel']")
    assert root.xpath("//Analysis[@id='modal']")
    assert root.xpath("//Material[@id='timber']")


def test_patch_requires_a_match(registry, base_job):
    base_job["model"]["patches"] = [{"op": "set_text", "xpath": "//Missing", "value": "x"}]
    with pytest.raises(PatchError, match="matched no nodes"):
        compile_job(base_job, registry)


def test_cannot_delete_root(registry, base_job):
    base_job["model"]["patches"] = [{"op": "delete", "xpath": "/*"}]
    with pytest.raises(PatchError, match="document root"):
        compile_job(base_job, registry)


def test_invalid_fragment_is_rejected(registry, base_job):
    base_job["model"]["patches"] = [
        {"op": "append_xml", "xpath": "//Materials", "xml": "<broken>"}
    ]
    with pytest.raises(PatchError, match="invalid XML fragment"):
        compile_job(base_job, registry)


def test_invalid_job_is_wrapped(registry):
    from histra_builder.errors import InvalidJobError

    with pytest.raises(InvalidJobError):
        compile_job({"job_id": "incomplete"}, registry)


def test_invalid_template_xml_is_rejected(tmp_path, base_job):
    from histra_builder.canonical import sha256_hex
    from histra_builder.errors import InvalidJobError
    from histra_builder.templates import TemplateRegistry

    registry = TemplateRegistry(tmp_path)
    broken = b"<broken>"
    registry.register("broken", broken)
    base_job["model"]["template"] = {"id": "broken", "sha256": sha256_hex(broken)}
    base_job["model"]["patches"] = [{"op": "set_text", "xpath": "/*", "value": "x"}]
    with pytest.raises(InvalidJobError, match="not valid XML"):
        compile_job(base_job, registry)


def test_invalid_xpath_and_non_element_selection(registry, base_job):
    base_job["model"]["patches"] = [{"op": "set_text", "xpath": "//*[", "value": "x"}]
    with pytest.raises(PatchError, match="invalid XPath"):
        compile_job(base_job, registry)

    base_job["model"]["patches"] = [
        {"op": "set_text", "xpath": "//Span/@length", "value": "x"}
    ]
    with pytest.raises(PatchError, match="must select XML elements"):
        compile_job(base_job, registry)


def test_cannot_replace_root(registry, base_job):
    base_job["model"]["patches"] = [
        {"op": "replace_xml", "xpath": "/*", "xml": "<Replacement/>"}
    ]
    with pytest.raises(PatchError, match="document root"):
        compile_job(base_job, registry)
