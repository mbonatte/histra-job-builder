"""C#-parity mesh generation for the native two-span fixture."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from collections import Counter
from pathlib import Path

import pytest

from histra_builder.generator.csharp_mesher import CSharpMesher, build_csharp_bridge_mesh
from histra_builder.generator.geometry import Point3D
from histra_builder.generator.csharp_writer import serialize_csharp_mesh_to_hrx
from lxml import etree
from histra_builder.generator.csharp_model import (
    Abutment,
    BridgeDefinition,
    CSharpBridgeSpec,
    Corsia,
    Elevation,
    Elevations,
    Pier,
    Span,
)

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "model_chain_2span.json"


def test_mesh3_subdivides_each_row_across_its_width() -> None:
    mesher = CSharpMesher(_spec())
    points = [Point3D(0, 0, 0), Point3D(120, 0, 0),
              Point3D(100, 0, 80), Point3D(20, 0, 80)]
    quads = mesher._add_mesh3(points, 2, 3, 18, 30, False)
    assert len(quads) == 6
    for index, quad in enumerate(quads):
        nodes = [mesher.nodes[key] for key in quad.node_keys]
        assert nodes[0].z == nodes[1].z == (index // 3) * 40
        assert nodes[2].z == nodes[3].z == (index // 3 + 1) * 40
        assert nodes[1].x > nodes[0].x


def test_foundation_support_flags_and_stiffness_match_native_mapping() -> None:
    spec = _spec()
    abutment = spec.abutments[0]
    abutment.is_fix_dir_x = False
    abutment.is_fix_dir_y = False
    abutment.is_fix_dir_z = False
    abutment.is_fix_rot_dir_x = False
    abutment.is_fix_rot_dir_y = True
    abutment.is_fix_rot_dir_z = False
    abutment.Kz = 0.25
    mesh = build_csharp_bridge_mesh(spec)
    glr = mesh.geometry_line_restraints[0]
    assert glr.behaviours == ("Free", "Fixed", "Free", "Free", "Free", "Fixed")
    left, right = mesh.nodes[glr.node_key1], mesh.nodes[glr.node_key2]
    assert glr.k == (0.0, pytest.approx(0.25 * glr.b * abs(left.x - right.x)),
                     0.0, 0.0, 0.0, -1.0)
    root = etree.fromstring(serialize_csharp_mesh_to_hrx(mesh))
    glr_xml = root.find(f"GeometryLineRestraint[@Key='{glr.key}']")
    restraint = next(item for item in mesh.restraints if item.parent_key == glr.key)
    restraint_xml = root.find(f"Restraint[@Key='{restraint.key}']")
    assert [int(item.get("Value")) for item in glr_xml.findall("RestraintKeys/RestraintKey")] == [
        item.key for item in mesh.restraints if item.parent_key == glr.key
    ]
    reference = glr_xml.find("ReferenceSystem")
    assert reference is not None
    assert [float(v) for v in reference.get("Origin").split(";")] == pytest.approx(
        [(left.x + right.x) / 2, (left.y + right.y) / 2, (left.z + right.z) / 2]
    )
    for element in (glr_xml, restraint_xml):
        assert element is not None
        assert element.get("U1mechBehaviourType") == "Free"
        assert element.get("U2mechBehaviourType") == "Fixed"
        assert float(element.get("K2")) == pytest.approx(glr.k[1])
        assert float(element.get("Kr3")) == -1


def test_arch_reinforcement_follows_each_intrados_segment() -> None:
    spec = _spec()
    spec.spans[0].Treinf = 5.0
    spec.spans[0].material_reinforcement_key = 21
    mesh = build_csharp_bridge_mesh(spec)
    reinforcement = [q for q in mesh.quads.values() if q.group == "CSharp_ArchReinforcement"]
    assert reinforcement
    assert all(q.material_key == 21 for q in reinforcement)
    arch = [q for q in mesh.quads.values() if q.group == "CSharp_Arch"]
    # Each reinforcement quad shares its outer edge with an arch intrados.
    arch_edges = [{q.node_keys[0], q.node_keys[3]} for q in arch]
    arch_edges += [{q.node_keys[1], q.node_keys[2]} for q in arch]
    assert all(any(edge in ({q.node_keys[0], q.node_keys[3]},
                            {q.node_keys[1], q.node_keys[2]})
                   for edge in arch_edges) for q in reinforcement)


def test_straight_csharp_arch_uses_adx_for_both_halves() -> None:
    spec = _spec()
    changed = deepcopy(spec)
    changed.spans[0].Asx += 10.0
    original = build_csharp_bridge_mesh(spec)
    actual = build_csharp_bridge_mesh(changed)
    assert actual.nodes == original.nodes
    assert [(q.node_keys, q.material_key) for q in actual.quads.values()] == [
        (q.node_keys, q.material_key) for q in original.quads.values()
    ]


def test_longitudinal_slope_moves_mesh_and_support_geometry() -> None:
    spec = _spec()
    flat = build_csharp_bridge_mesh(spec)
    spec.definition.slope = 0.01
    graded = build_csharp_bridge_mesh(spec)
    assert graded.nodes.keys() == flat.nodes.keys()
    for key, point in flat.nodes.items():
        changed = graded.nodes[key]
        assert changed.z == pytest.approx(point.z + point.x * 0.01, abs=1e-4)
    for restraint in graded.restraints:
        a, b = graded.nodes[restraint.node_key1], graded.nodes[restraint.node_key2]
        assert restraint.g.z == pytest.approx((a.z + b.z) / 2)
        assert restraint.point1.z == a.z
        assert restraint.point2.z == b.z


def test_straight_inclined_strips_follow_native_skew_transform() -> None:
    spec = _spec()
    flat = build_csharp_bridge_mesh(spec)
    spec.definition.inclination_angle = 15.0
    mesh = build_csharp_bridge_mesh(spec)
    angle = math.radians(15)
    for key, point in flat.nodes.items():
        assert mesh.nodes[key].x == pytest.approx(point.x + point.y * math.tan(angle), abs=1e-4)
    for key, quad in flat.quads.items():
        changed = mesh.quads[key]
        assert changed.thickness == pytest.approx(quad.thickness / math.cos(angle))
        normal = changed.kinematics.normals[0]
        assert abs(normal.x) == pytest.approx(math.sin(angle))
        assert abs(normal.y) == pytest.approx(math.cos(angle))
    for glr in mesh.geometry_line_restraints:
        assert glr.b == pytest.approx(100 / math.cos(angle))
    for restraint in mesh.restraints:
        assert abs(restraint.point4.x - restraint.point1.x) == pytest.approx(100 * math.tan(angle))
        assert restraint.point4.y - restraint.point1.y == pytest.approx(100)


def test_inclined_tapered_support_is_not_silently_exported() -> None:
    spec = _spec()
    spec.definition.inclination_angle = 15.0
    spec.piers[0].w1 = 10.0
    with pytest.raises(NotImplementedError, match="tapered or offset"):
        build_csharp_bridge_mesh(spec)


def _float(raw: dict, key: str, default: float = 0.0) -> float:
    return float(raw.get(key, default))


def _spec() -> CSharpBridgeSpec:
    wizard = json.loads(FIXTURE.read_text(encoding="utf-8"))["wizard"]
    definition = wizard["bridge_definition"]

    def make_abutment(raw: dict) -> Abutment:
        return Abutment(
            b1=_float(raw, "b1"),
            b2=_float(raw, "b2"),
            b3=_float(raw, "b3"),
            w1=_float(raw, "w1"),
            w2=_float(raw, "w2"),
            w3=_float(raw, "w3"),
            H=_float(raw, "H"),
            Hf=_float(raw, "Hf"),
            B1f=_float(raw, "B1f"),
            B3f=_float(raw, "B3f"),
            W1f=_float(raw, "W1f"),
            W3f=_float(raw, "W3f"),
            material_key=int(raw.get("MaterialKey", 18)),
            material_foundation_key=int(raw.get("MaterialFoundationKey", 18)),
            kind=raw.get("AbutmentKind", "Sinistra"),
        )

    abutments = [make_abutment(raw) for raw in wizard["abutments"]]
    spans = [
        Span(
            L=_float(raw, "L"),
            W=_float(raw, "W"),
            f=_float(raw, "f"),
            S1=_float(raw, "S1"),
            S2=_float(raw, "S2"),
            Asx=_float(raw, "Asx"),
            Adx=_float(raw, "Adx"),
            Tb=_float(raw, "Tb"),
            Tb1=_float(raw, "Tb1"),
            Tb2=_float(raw, "Tb2"),
            Tt=_float(raw, "Tt"),
            Treinf=_float(raw, "Treinf"),
            Dz=_float(raw, "Dz"),
            L1=_float(raw, "L1"),
            f1=_float(raw, "f"),
            f2=_float(raw, "f2"),
            material_key=int(raw.get("MaterialKey", 18)),
            material_pulvino_key=int(raw.get("MaterialPulvinoKey", 22)),
        )
        for raw in wizard["spans"]
    ]
    piers = [
        Pier(
            b1=_float(raw, "b1"),
            b2=_float(raw, "b2"),
            b3=_float(raw, "b3"),
            w1=_float(raw, "w1"),
            w2=_float(raw, "w2"),
            w3=_float(raw, "w3"),
            H=_float(raw, "H"),
            Hf=_float(raw, "Hf"),
            material_key=int(raw.get("MaterialKey", 18)),
            material_foundation_key=int(raw.get("MaterialFoundationKey", 18)),
        )
        for raw in wizard["piers"]
    ]
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=_float(definition, "Width"),
            width_top_pile=_float(definition, "WidthTopPile"),
            nl=_float(definition, "Nl"),
            nt=_float(definition, "Nt"),
            corsias=[Corsia(width=100.0), Corsia(width=100.0), Corsia(width=100.0)],
        ),
        elements=[abutments[0], spans[0], piers[0], spans[1], abutments[1]],
        elevations=Elevations([Elevation(X=0.0, H1=126.5, H2=0.0, H3=0.0)]),
    )


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _quad_signature(points):
    # Vertex order is significant: C# stores it as-is and derives the
    # element reference system/normal winding from it.
    return tuple(
        (round(point[1], 1), round(point[0], 2), round(point[2], 2))
        for point in points
    )


def test_csharp_mesh_matches_native_structural_counts() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    assert len(mesh.nodes) == len(fixture["nodes"]) == 222
    assert len(mesh.quads) == len(fixture["quads"]) == 156


def test_csharp_mesh_material_distribution_matches_native() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    assert Counter(quad.material_key for quad in mesh.quads.values()) == Counter(
        quad["material"] for quad in fixture["quads"]
    )


def test_csharp_mesh_matches_native_quad_geometry() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    expected_nodes = {
        int(key): tuple(value) for key, value in fixture["nodes"].items()
    }
    expected = Counter(
        _quad_signature([expected_nodes[key] for key in quad["nodes"]])
        for quad in fixture["quads"]
    )
    actual = [
        _quad_signature(
            [
                (mesh.nodes[key].x, mesh.nodes[key].y, mesh.nodes[key].z)
                for key in quad.node_keys
            ]
        )
        for quad in mesh.quads.values()
    ]
    expected_list = [
        _quad_signature([expected_nodes[key] for key in quad["nodes"]])
        for quad in fixture["quads"]
    ]
    assert actual == expected_list


def test_csharp_mesh_nodes_match_native_geometry() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    expected = {
        (round(point[1], 1), round(point[0], 2), round(point[2], 2))
        for point in (tuple(value) for value in fixture["nodes"].values())
    }
    actual = {
        (round(node.y, 1), round(node.x, 2), round(node.z, 2))
        for node in mesh.nodes.values()
    }
    assert actual == expected


def test_csharp_mesh_has_three_strips_and_four_quads_per_pier_strip() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    y_values = {round(node.y, 1) for node in mesh.nodes.values()}
    assert y_values == {-100.0, 0.0, 100.0}
    pier_quads = [quad for quad in mesh.quads.values() if quad.group == "CSharp_Pier"]
    assert len(pier_quads) == 12  # 3 strips * 4 shaft quads


def test_csharp_mesh_normal_winding_matches_native() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    normals = Counter(
        round(quad.kinematics.normals[0].y, 1) for quad in mesh.quads.values()
    )
    # C# BridgeMesher flips the normal for the 12 negatively wound fill quads.
    assert normals == Counter({-1.0: 144, 1.0: 12})


def test_csharp_foundation_line_restraints_match_native() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    assert len(mesh.geometry_line_restraints) == 12
    for actual, expected in zip(mesh.geometry_line_restraints, fixture["geometry_line_restraints"]):
        assert actual.key == int(expected["Key"])
        assert actual.node_key1 == int(expected["NodeKey1"])
        assert actual.node_key2 == int(expected["NodeKey2"])
        assert actual.b == float(expected["B"])
        assert actual.h == float(expected["H"])
        assert actual.parent_key == int(expected["ParentKey"])
        assert actual.parent_type == expected["ParentType"]


def test_csharp_foundation_restraints_match_native() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    assert len(mesh.restraints) == 12
    for actual, expected in zip(mesh.restraints, fixture["restraints"]):
        assert actual.key == int(expected["Key"])
        assert actual.parent_key == int(expected["ParentKey"])
        assert actual.parent_type_element == expected["ParentTypeElement"]
        assert actual.node_key1 == int(expected["NodeKey1"])
        assert actual.node_key2 == int(expected["NodeKey2"])
        assert actual.computational_element_key == int(expected["ComputationalElementKey"])
        assert actual.computational_element_edge == int(expected["ComputationalElementEdge"])
        assert actual.point1.x == pytest.approx(float(expected["Point1"].split(";")[0]), abs=2e-3)
        assert actual.point1.y == pytest.approx(float(expected["Point1"].split(";")[1]), abs=2e-3)
        assert actual.point1.z == pytest.approx(float(expected["Point1"].split(";")[2]), abs=2e-3)
        assert actual.point3.y == pytest.approx(float(expected["Point3"].split(";")[1]), abs=2e-3)


def test_csharp_node_c_mapping_matches_native() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    fixture = _fixture()
    expected = {
        int(item["key"]): int(item["node_key"]) for item in fixture["node_cs"]
    }
    actual = {node_c.key: node_c.node_key for node_c in mesh.node_cs}
    assert actual == expected


def test_csharp_default_model_point_uses_highest_node_near_plan_center() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    assert len(mesh.monitoring_points) == 1
    point = mesh.monitoring_points[0]
    assert point.element_type == "Node"
    node = mesh.nodes[point.element_key]
    assert node.z == max(item.z for item in mesh.nodes.values())
    top = [item for item in mesh.nodes.values() if item.z == node.z]
    x_mid = (max(item.x for item in top) + min(item.x for item in top)) / 2.0
    y_mid = (max(item.y for item in top) + min(item.y for item in top)) / 2.0
    distance = (node.x - x_mid) ** 2 + (node.y - y_mid) ** 2
    assert distance == min(
        (item.x - x_mid) ** 2 + (item.y - y_mid) ** 2 for item in top
    )


def test_csharp_foundation_restraints_are_tagged_by_owner() -> None:
    mesh = build_csharp_bridge_mesh(_spec())
    tags = [restraint.foundation_tag for restraint in mesh.restraints]
    assert tags.count("abutment_left") == 3
    assert tags.count("pier_1") == 6
    assert tags.count("abutment_right") == 3
