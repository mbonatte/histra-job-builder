from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from lxml import etree

from .canonical import job_sha256, sha256_hex
from .errors import InvalidJobError, PatchError
from .models import JobSpec, PatchOperation
from .templates import TemplateRegistry

BUILDER_VERSION = "1.1.0"


@dataclass(frozen=True)
class BuildArtifact:
    output_path: str
    hrx_bytes: bytes
    provenance: dict[str, Any]

    @property
    def hrx_sha256(self) -> str:
        return str(self.provenance["hrx_sha256"])


def _secure_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False, strip_cdata=False)


def _parse_fragment(xml: str) -> etree._Element:
    try:
        return etree.fromstring(xml.encode("utf-8"), parser=_secure_parser())
    except etree.XMLSyntaxError as exc:
        raise PatchError(f"invalid XML fragment: {exc}") from exc


def _select(tree: etree._ElementTree, patch: PatchOperation) -> list[etree._Element]:
    try:
        nodes = tree.xpath(patch.xpath)
    except etree.XPathError as exc:
        raise PatchError(f"invalid XPath {patch.xpath!r}: {exc}") from exc
    if not nodes:
        raise PatchError(f"XPath matched no nodes: {patch.xpath}")
    if not all(isinstance(node, etree._Element) for node in nodes):
        raise PatchError("patch XPath must select XML elements")
    return list(nodes)


def _apply_patch(tree: etree._ElementTree, patch: PatchOperation) -> None:
    nodes = _select(tree, patch)
    if patch.op == "set_attribute":
        assert patch.attribute is not None and patch.value is not None
        for node in nodes:
            node.set(patch.attribute, str(patch.value))
    elif patch.op == "set_text":
        assert patch.value is not None
        for node in nodes:
            node.text = str(patch.value)
    elif patch.op == "delete":
        for node in nodes:
            parent = node.getparent()
            if parent is None:
                raise PatchError("cannot delete the document root")
            parent.remove(node)
    elif patch.op == "replace_xml":
        assert patch.xml is not None
        fragment = _parse_fragment(patch.xml)
        for node in nodes:
            parent = node.getparent()
            if parent is None:
                raise PatchError("cannot replace the document root")
            parent.replace(node, deepcopy(fragment))
    elif patch.op == "append_xml":
        assert patch.xml is not None
        fragment = _parse_fragment(patch.xml)
        for node in nodes:
            node.append(deepcopy(fragment))
    else:  # pragma: no cover - protected by model validation
        raise PatchError(f"unsupported patch operation: {patch.op}")


def compile_job(job: JobSpec | dict[str, Any], registry: TemplateRegistry) -> BuildArtifact:
    """Compile a canonical JOB into a deterministic HRX artifact."""
    try:
        spec = job if isinstance(job, JobSpec) else JobSpec.model_validate(job)
    except Exception as exc:
        raise InvalidJobError(str(exc)) from exc
    canonical = spec.model_dump(mode="json")
    asset = registry.load(spec.model.template.id, spec.model.template.sha256)
    if not spec.model.patches:
        output = asset.data
    else:
        try:
            root = etree.fromstring(asset.data, parser=_secure_parser())
        except etree.XMLSyntaxError as exc:
            raise InvalidJobError(f"template is not valid XML: {exc}") from exc
        tree = root.getroottree()
        for patch in spec.model.patches:
            _apply_patch(tree, patch)
        output = etree.tostring(tree, encoding="utf-8", xml_declaration=True, pretty_print=False)
    provenance = {
        "builder_version": BUILDER_VERSION,
        "job_sha256": job_sha256(canonical),
        "template_id": asset.template_id,
        "template_sha256": asset.sha256,
        "hrx_sha256": sha256_hex(output),
        "output_path": spec.model.output_path,
    }
    return BuildArtifact(spec.model.output_path, output, provenance)
