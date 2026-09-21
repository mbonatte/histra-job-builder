"""Serializes generated bridge mesh models into valid HiStrA HRX XML."""
from __future__ import annotations

from typing import List, Optional
from lxml import etree

from .materials import DEFAULT_TEMPLATES
from .mesher import GeneratedBridgeMesh


def serialize_mesh_to_hrx(
    mesh: GeneratedBridgeMesh,
    include_scour_analyses: bool = True,
    pretty_print: bool = True,
) -> bytes:
    """Serialize a GeneratedBridgeMesh into byte-exact HRX XML conforming to HiStrA 2026.1.0."""
    spec = mesh.spec

    root = etree.Element(
        "HiStrA",
        attrib={
            "version": "2026.1.0",
            "GDL": "0",
            "WizardType": "RailBridge",
            "IsLocked": "false",
        },
    )

    # 1. WizardData (preserves high-level metadata for scenario generators and inspect tools)
    wiz = etree.SubElement(root, "WizardData", attrib={"TypeOf": "HiStrA.Objects.WizardBridge"})
    etree.SubElement(wiz, "SchemaCombinationDataList")
    etree.SubElement(
        wiz,
        "BridgeDefinition",
        attrib={
            "Width": str(spec.width),
            "WidthTopPile": str(spec.width),
            "IsWidthTopPileCustom": "false",
            "Nl": str(spec.target_mesh_size),
            "Nt": "20000",
            "InclinationAngle": "0",
            "Slope": "0",
            "Origin": "0;0;0",
        },
    )

    # Left Abutment
    etree.SubElement(
        wiz,
        "Abutment",
        attrib={
            "MaterialKey": str(spec.left_abutment.material_key),
            "MaterialFoundationKey": str(spec.left_abutment.foundation_material_key),
            "H": str(spec.left_abutment.height),
            "Hf": str(spec.left_abutment.foundation_height),
            "b2": str(spec.left_abutment.thickness),
            "B1f": "0",
            "B3f": "0",
            "W1f": "0",
            "W3f": "0",
            "Kz": "0.1",
            "AbutmentKind": "Sinistra",
        },
    )

    # Spans and Piers
    for s_idx, span in enumerate(spec.spans):
        etree.SubElement(
            wiz,
            "Span",
            attrib={
                "MaterialKey": str(span.material_key),
                "L": str(span.length),
                "f": str(span.rise),
                "Tb": str(span.thickness_springer),
                "Tt": str(span.thickness_crown),
                "W": str(spec.width),
                "Circolare": "false",
            },
        )
        if s_idx < len(spec.piers):
            pier = spec.piers[s_idx]
            p_meta = mesh.piers[s_idx]
            pier_elem = etree.SubElement(
                wiz,
                "Pier",
                attrib={
                    "MaterialKey": str(pier.material_key),
                    "MaterialFoundationKey": str(pier.foundation_material_key),
                    "H": str(pier.height),
                    "Hf": str(pier.foundation_height),
                    "b2": str(pier.thickness),
                    "B1f": "0",
                    "B3f": "0",
                    "W1f": "0",
                    "W3f": "0",
                    "Kz": str(pier.subgrade_modulus_kz),
                },
            )
            etree.SubElement(
                pier_elem,
                "ReferenceSystem",
                attrib={
                    "E1": "1;0;0",
                    "E2": "0;1;0",
                    "E3": "0;0;1",
                    "Origin": p_meta.origin.to_xml_str(),
                },
            )

    # Right Abutment
    etree.SubElement(
        wiz,
        "Abutment",
        attrib={
            "MaterialKey": str(spec.right_abutment.material_key),
            "MaterialFoundationKey": str(spec.right_abutment.foundation_material_key),
            "H": str(spec.right_abutment.height),
            "Hf": str(spec.right_abutment.foundation_height),
            "b2": str(spec.right_abutment.thickness),
            "B1f": "0",
            "B3f": "0",
            "W1f": "0",
            "W3f": "0",
            "Kz": "0.1",
            "AbutmentKind": "Destra",
        },
    )
    etree.SubElement(wiz, "Elevations", attrib={"IsStratigraphyVariable": "false"})

    # 2. AdvancedOptionsDefault
    etree.SubElement(
        root,
        "AdvancedOptionsDefault",
        attrib={
            "InterfaceNrow": "9",
            "InterfaceImax": "400",
            "MassMatrixType": "Lumped",
        },
    )

    # 3. Material Templates
    for t_dict in DEFAULT_TEMPLATES:
        etree.SubElement(root, "Template", attrib={k: str(v) for k, v in t_dict.items()})

    # 4. Structural Nodes
    for n_key in sorted(mesh.nodes.keys()):
        pt = mesh.nodes[n_key]
        etree.SubElement(
            root,
            "Node",
            attrib={
                "Key": str(n_key),
                "Point": pt.to_xml_str(),
                "Name": str(n_key),
            },
        )

    # 5. NodeC Entities
    for nc in mesh.node_cs:
        etree.SubElement(
            root,
            "NodeC",
            attrib={
                "Key": str(nc.key),
                "NodeKey": str(nc.node_key),
                "MasterElementKey": str(nc.master_element_key),
                "MasterElementType": nc.master_element_type,
                "IsIndipendent": "true" if nc.is_independent else "false",
            },
        )

    # 6. Quad Finite Elements
    for q_key in sorted(mesh.quads.keys()):
        quad = mesh.quads[q_key]
        k = quad.kinematics
        q_elem = etree.SubElement(
            root,
            "Quad",
            attrib={
                "Key": str(quad.key),
                "Name": str(quad.key),
                "ParentKey": str(quad.parent_key),
                "ParentTypeElement": quad.parent_type_element,
                "MaterialKey": str(quad.material_key),
                "LayerKey": str(quad.layer_key),
                "MasterElementKey": "0",
                "MasterElementType": "None",
                "NodeKey1": str(quad.node_keys[0]),
                "NodeKey2": str(quad.node_keys[1]),
                "NodeKey3": str(quad.node_keys[2]),
                "NodeKey4": str(quad.node_keys[3]),
                "Length1": f"{k.lengths[0]:.6f}",
                "Length2": f"{k.lengths[1]:.6f}",
                "Length3": f"{k.lengths[2]:.6f}",
                "Length4": f"{k.lengths[3]:.6f}",
                "Sin1": f"{k.sines[0]:.6f}",
                "Sin2": f"{k.sines[1]:.6f}",
                "Sin3": f"{k.sines[2]:.6f}",
                "Sin4": f"{k.sines[3]:.6f}",
                "Cos1": f"{k.cosines[0]:.6f}",
                "Cos2": f"{k.cosines[1]:.6f}",
                "Cos3": f"{k.cosines[2]:.6f}",
                "Cos4": f"{k.cosines[3]:.6f}",
                "Diago1": f"{k.diagonals[0]:.6f}",
                "Diago2": f"{k.diagonals[1]:.6f}",
                "Thickness1": f"{k.thicknesses[0]:.6f}",
                "Thickness2": f"{k.thicknesses[1]:.6f}",
                "Thickness3": f"{k.thicknesses[2]:.6f}",
                "Thickness4": f"{k.thicknesses[3]:.6f}",
                "Normal1": k.normals[0].to_xml_str(),
                "Normal2": k.normals[1].to_xml_str(),
                "Normal3": k.normals[2].to_xml_str(),
                "Normal4": k.normals[3].to_xml_str(),
                "G": k.centroid.to_xml_str(),
            },
        )
        etree.SubElement(
            q_elem,
            "ReferenceSystem",
            attrib={
                "E1": f"{k.ref_e1[0]:.6f};{k.ref_e1[1]:.6f};{k.ref_e1[2]:.6f}",
                "E2": f"{k.ref_e2[0]:.6f};{k.ref_e2[1]:.6f};{k.ref_e2[2]:.6f}",
                "E3": f"{k.ref_e3[0]:.6f};{k.ref_e3[1]:.6f};{k.ref_e3[2]:.6f}",
                "Origin": k.ref_origin.to_xml_str(),
            },
        )

    # 7. Boundary Restraints
    for res in mesh.restraints:
        etree.SubElement(
            root,
            "Restraint",
            attrib={
                "Key": str(res.key),
                "Name": str(res.name),
                "ParentKey": str(res.parent_key),
                "ParentTypeElement": res.parent_type_element,
                "NodeCKey1": str(res.node_c_key1),
                "NodeCKey2": str(res.node_c_key2),
                "NodeKey1": str(res.node_key1),
                "NodeKey2": str(res.node_key2),
                "ComputationalElementKey": str(res.computational_element_key),
                "ComputationalElementType": res.computational_element_type,
                "ComputationalElementEdge": str(res.computational_element_edge),
                "MaterialKey": str(res.material_key),
                "LayerKey": str(res.layer_key),
                "Zg": str(res.zg),
                "K1": "-1",
                "K2": "-1",
                "K3": "-1",
                "Kr1": "-1",
                "Kr2": "-1",
                "Kr3": "-1",
                "G": res.g.to_xml_str(),
                "Point1": res.point1.to_xml_str(),
                "Point2": res.point2.to_xml_str(),
                "Point3": res.point3.to_xml_str(),
                "Point4": res.point4.to_xml_str(),
                "MasterElementKey": "0",
                "MasterElementType": "None",
            },
        )

    # 8. Monitoring ModelPoints
    for mp in mesh.monitoring_points:
        etree.SubElement(
            root,
            "ModelPoint",
            attrib={
                "Key": str(mp.key),
                "IdElement": str(mp.element_key),
                "ElementKey": str(mp.element_key),
                "ElementType": mp.element_type,
                "IdVertex": str(mp.id_vertex),
                "Description": mp.description,
            },
        )

    # 9. Load Conditions
    etree.SubElement(
        root,
        "LoadCondition",
        attrib={
            "Id": "1",
            "Name": "Gravity",
            "Description": "Self weight - G1",
            "MassInDirX": "1",
            "MassInDirY": "1",
            "MassInDirZ": "1",
            "isMainLoad": "false",
            "isFavourable": "false",
            "isUnFavourable": "true",
            "Action": "1",
        },
    )

    # 10. Load Combinations
    lc = etree.SubElement(
        root,
        "LoadCombination",
        attrib={"Key": "6", "Name": "SEISMIC", "LimitState": "Seismic"},
    )
    etree.SubElement(
        lc,
        "Item",
        attrib={
            "LoadCombinationKey": "6",
            "ColumnKey": "1",
            "RowKey": "1",
            "Name": "1",
            "Schema": "NoSchema",
            "Position": "0",
            "Combination": "1",
            "TypeData": "Number",
            "SecondaryTypeData": "Number",
            "Val": "1",
        },
    )

    # 11. Load Functions
    etree.SubElement(root, "LoadFunction", attrib={"key": "1", "typeDiscr": "false", "DiscrVal": "0.05"})
    etree.SubElement(root, "LoadFunctionItem", attrib={"key": "1", "loadFunctionKey": "1", "pseudoTime": "0", "multiplier": "0"})
    etree.SubElement(root, "LoadFunctionItem", attrib={"key": "2", "loadFunctionKey": "1", "pseudoTime": "1", "multiplier": "1"})

    if include_scour_analyses:
        etree.SubElement(root, "LoadFunction", attrib={"key": "23", "typeDiscr": "false", "DiscrVal": "0.05"})
        etree.SubElement(root, "LoadFunctionItem", attrib={"key": "3", "loadFunctionKey": "23", "pseudoTime": "0", "multiplier": "0"})
        etree.SubElement(root, "LoadFunctionItem", attrib={"key": "4", "loadFunctionKey": "23", "pseudoTime": "1", "multiplier": "1"})

        etree.SubElement(root, "LoadFunction", attrib={"key": "24", "typeDiscr": "false", "DiscrVal": "0.05"})
        etree.SubElement(root, "LoadFunctionItem", attrib={"key": "5", "loadFunctionKey": "24", "pseudoTime": "0", "multiplier": "0"})
        etree.SubElement(root, "LoadFunctionItem", attrib={"key": "6", "loadFunctionKey": "24", "pseudoTime": "1", "multiplier": "1"})

    # 12. Analysis Configurations
    # Strict ForceMoment equilibrium criteria enforced
    vert_analysis = etree.SubElement(
        root,
        "Analysis",
        attrib={
            "Key": "1",
            "Name": "Vert",
            "AnalysisType": "2",
            "LoadCombinationKey": "6",
            "LoadFunctionKey": "1",
            "InitialAnalysisKey": "-100",
            "AdapticConvergenceCriteria": "ForceMoment",
            "ConvergenceTolerance": "0.0001",
            "ConvergenceToleranceForce": "0.0001",
            "ConvergenceToleranceMoment": "0.0001",
            "Method": "ModifiedRegulaFalsiLineSearch",
            "IntegrationMethod": "LoadControl",
            "TypeLoadDistribution": "LoadCombination",
        },
    )
    vert_amp = etree.SubElement(vert_analysis, "ActiveModelPoints")
    for mp in mesh.monitoring_points:
        etree.SubElement(vert_amp, "ActiveModelPoint", attrib={"Key": str(mp.key), "Value": "true"})

    if include_scour_analyses:
        scour_1 = etree.SubElement(
            root,
            "Analysis",
            attrib={
                "Key": "23",
                "Name": "Scour_1",
                "AnalysisType": "2",
                "LoadCombinationKey": "6",
                "LoadFunctionKey": "23",
                "InitialAnalysisKey": "1",
                "AdapticConvergenceCriteria": "ForceMoment",
                "ConvergenceTolerance": "0.0001",
                "ConvergenceToleranceForce": "0.0001",
                "ConvergenceToleranceMoment": "0.0001",
                "Method": "ModifiedRegulaFalsiLineSearch",
                "IntegrationMethod": "LoadControl",
                "TypeLoadDistribution": "LoadCombination",
            },
        )
        s1_amp = etree.SubElement(scour_1, "ActiveModelPoints")
        for mp in mesh.monitoring_points:
            etree.SubElement(s1_amp, "ActiveModelPoint", attrib={"Key": str(mp.key), "Value": "true"})

        scour_2 = etree.SubElement(
            root,
            "Analysis",
            attrib={
                "Key": "24",
                "Name": "Scour_2",
                "AnalysisType": "2",
                "LoadCombinationKey": "6",
                "LoadFunctionKey": "24",
                "InitialAnalysisKey": "23",
                "AdapticConvergenceCriteria": "ForceMoment",
                "ConvergenceTolerance": "0.0001",
                "ConvergenceToleranceForce": "0.0001",
                "ConvergenceToleranceMoment": "0.0001",
                "Method": "ModifiedRegulaFalsiLineSearch",
                "IntegrationMethod": "LoadControl",
                "TypeLoadDistribution": "LoadCombination",
            },
        )
        s2_amp = etree.SubElement(scour_2, "ActiveModelPoints")
        for mp in mesh.monitoring_points:
            etree.SubElement(s2_amp, "ActiveModelPoint", attrib={"Key": str(mp.key), "Value": "true"})

    return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=pretty_print)
