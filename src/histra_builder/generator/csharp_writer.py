"""Native HRX serialization for the C#-parity bridge mesh.

The existing ``hrx_writer`` already knows how to emit nodes, quads, materials,
loads and analyses.  This module adds the native objects that the first parity
slice needs:

* a ``Bridge`` element with its structural key lists;
* ``GeometryLineRestraint`` foundation supports;
* restraint parents pointing at the corresponding GLR.
"""
from __future__ import annotations

from typing import Any

from lxml import etree

from .csharp_mesher import CSharpBridgeMesh, build_csharp_bridge_mesh
from .csharp_model import CSharpBridgeSpec
from .hrx_writer import serialize_mesh_to_hrx
from .csharp_wizard import replace_wizard_data
from .materials import DEFAULT_TEMPLATES


def _key_list(parent: etree._Element, tag: str, item_tag: str, keys) -> None:
    container = etree.SubElement(parent, tag)
    for key in keys:
        etree.SubElement(container, item_tag, Value=str(key))


def _format_vector(values) -> str:
    if hasattr(values, "x"):
        values = (values.x, values.y, values.z)
    return ";".join(format(float(value), ".17g") for value in values)


def _add_bridge_element(root: etree._Element, mesh: CSharpBridgeMesh) -> etree._Element:
    bridge = etree.SubElement(
        root,
        "Bridge",
        attrib={
            "H": format(mesh.deck_z, ".17g"),
            "B": format(mesh.spec.width, ".17g"),
            "L": format(mesh.total_length, ".17g"),
            "MasterElementKey": "0",
            "MasterElementType": "None",
            "LayerKey": "0",
            "IsPropertyModified": "false",
            "Key": "1",
            "Name": "1",
        },
    )
    _key_list(bridge, "VertexKeys", "VertexKey", ())
    _key_list(bridge, "SolidKeys", "SolidKey", ())
    _key_list(bridge, "TrussKeys", "TrussKey", ())
    _key_list(bridge, "QuadKeys", "QuadKey", sorted(mesh.quads))
    _key_list(
        bridge,
        "GeometryLineRestraintKeys",
        "GeometryLineRestraintKey",
        [glr.key for glr in mesh.geometry_line_restraints],
    )
    _key_list(bridge, "QuadSpanKeys", "QuadSpanKey", ())
    surface = etree.SubElement(bridge, "SurfaceRestraints")
    del surface
    etree.SubElement(
        bridge,
        "ReferenceSystem",
        E1="1;0;0",
        E2="0;1;0",
        E3="0;0;1",
        Origin="0;0;0",
    )
    return bridge


def _add_geometry_line_restraints(root: etree._Element, mesh: CSharpBridgeMesh) -> None:
    for glr in mesh.geometry_line_restraints:
        element = etree.SubElement(
            root,
            "GeometryLineRestraint",
            attrib={
                "NodeKey1": str(glr.node_key1),
                "NodeKey2": str(glr.node_key2),
                "ParentKey": str(glr.parent_key),
                "ParentType": glr.parent_type,
                "ParentEdge": str(glr.parent_edge),
                "MaterialKey": str(glr.material_key),
                "LoadConditionKey": str(glr.load_condition_key),
                "Zg": format(glr.zg, ".17g"),
                "B": format(glr.b, ".17g"),
                "H": format(glr.h, ".17g"),
                "Alignment": glr.alignment,
                "Dy": format(glr.dy, ".17g"),
                "MechanicalType": glr.mechanical_type,
                "K": "|".join(format(value, ".17g") for value in glr.k),
                "MasterElementKey": "0",
                "MasterElementType": "None",
                "LayerKey": "0",
                "IsPropertyModified": "false",
                "Key": str(glr.key),
                "Name": glr.name,
            },
        )
        for index, direction in enumerate(("U1", "U2", "U3", "R1", "R2", "R3"), start=1):
            element.set(f"{direction}mechBehaviourType", glr.behaviours[index - 1])
            stiffness = "K" if index <= 3 else "Kr"
            element.set(f"{stiffness}{index if index <= 3 else index - 3}", format(glr.k[index - 1], ".17g"))
        children = [restraint for restraint in mesh.restraints if restraint.parent_key == glr.key]
        _key_list(element, "RestraintKeys", "RestraintKey", (item.key for item in children))
        if children:
            child = root.find(f"Restraint[@Key='{children[0].key}']/ReferenceSystem")
            if child is not None:
                node1, node2 = mesh.nodes[glr.node_key1], mesh.nodes[glr.node_key2]
                attrs = dict(child.attrib)
                attrs["Origin"] = _format_vector(((node1.x + node2.x) / 2,
                                                  (node1.y + node2.y) / 2,
                                                  (node1.z + node2.z) / 2))
                etree.SubElement(element, "ReferenceSystem", attrib=attrs)


def _reparent_restraints(root: etree._Element, mesh: CSharpBridgeMesh) -> None:
    glrs = {glr.key: glr for glr in mesh.geometry_line_restraints}
    for element in root.findall("Restraint"):
        key = int(element.get("Key", "0"))
        restraint = next((item for item in mesh.restraints if item.key == key), None)
        if restraint is None:
            continue
        glr = glrs[restraint.parent_key]
        element.set("ParentKey", str(glr.key))
        element.set("ParentTypeElement", "GeometryLineRestraint")
        element.set("H", format(glr.h, ".17g"))
        element.set("LoadConditionKey", str(glr.load_condition_key))
        element.set("MechanicalType", glr.mechanical_type)
        for index, direction in enumerate(("U1", "U2", "U3", "R1", "R2", "R3")):
            element.set(f"{direction}mechBehaviourType", restraint.behaviours[index])
            stiffness = "K" if index < 3 else "Kr"
            element.set(f"{stiffness}{index + 1 if index < 3 else index - 2}", format(restraint.k[index], ".17g"))


def serialize_csharp_mesh_to_hrx(
    mesh: CSharpBridgeMesh,
    *,
    include_scour_analyses: bool = True,
    pretty_print: bool = True,
    templates: list[dict[str, str]] | None = None,
) -> bytes:
    """Write a native-style HRX for a C#-parity mesh."""
    if templates is None:
        by_key = {int(template["Key"]): template for template in DEFAULT_TEMPLATES}
        by_key.update({int(template["Key"]): template for template in mesh.spec.material_templates})
        material_templates = list(by_key.values())
    else:
        material_templates = templates
    available = {int(template["Key"]) for template in material_templates}
    missing = sorted({quad.material_key for quad in mesh.quads.values()} - available)
    if missing:
        raise ValueError(f"Missing material templates for quad keys: {missing}")
    raw = serialize_mesh_to_hrx(
        mesh,  # type: ignore[arg-type]
        include_scour_analyses=include_scour_analyses,
        pretty_print=False,
        templates=material_templates,
    )
    root = etree.fromstring(raw)
    root.set("WizardType", mesh.spec.wizard_type)
    replace_wizard_data(root, mesh.spec)
    _add_bridge_element(root, mesh)
    _add_geometry_line_restraints(root, mesh)
    _reparent_restraints(root, mesh)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="utf-8",
        pretty_print=pretty_print,
    )


def generate_csharp_bridge_hrx(
    spec: CSharpBridgeSpec,
    *,
    include_scour_analyses: bool = True,
    pretty_print: bool = True,
    templates: list[dict[str, str]] | None = None,
) -> bytes:
    mesh = build_csharp_bridge_mesh(spec)
    return serialize_csharp_mesh_to_hrx(
        mesh,
        include_scour_analyses=include_scour_analyses,
        pretty_print=pretty_print,
        templates=templates,
    )
