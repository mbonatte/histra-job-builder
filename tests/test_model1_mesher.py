from __future__ import annotations

from collections import Counter
from pathlib import Path

from lxml import etree

from app.mesh import generate_mesh
from app.schemas import MeshPatch

ROOT = Path(__file__).resolve().parents[1]
MODEL1 = ROOT / "tests" / "fixtures" / "Model1.hrx"


def _tree_with_nl(value: float):
    tree = etree.parse(str(MODEL1), etree.XMLParser(huge_tree=True))
    bridge = tree.getroot().find("./WizardData/BridgeDefinition")
    assert bridge is not None
    bridge.set("Nl", str(value))
    return tree



def test_model1_features_are_reconstructed_at_reference_target():
    mesh = generate_mesh(_tree_with_nl(100), MeshPatch())
    assert mesh.metadata["geometryValidation"]["valid"] is True
    assert [span["arcDivisions"] for span in mesh.metadata["spans"]] == [8, 12, 12, 12, 12]
    assert [layer["materialKey"] for layer in mesh.metadata["backfillLayers"]] == ["19", "20", "21"]

    materials = Counter(quad.material_key for quad in mesh.quads)
    # The arch topology is reproduced exactly.  Support/fill topology is cleaned
    # up deliberately, so its counts need not include HiStrA's duplicate nodes.
    assert materials["18"] == 280

    node_map = {node.key: node.point for node in mesh.nodes}
    outer_top = max(
        node_map[key][2]
        for quad in mesh.quads
        if quad.transverse_band_index in {0, 4} and quad.transverse_role == "deck"
        for key in quad.node_keys
    )
    centre_top = max(
        node_map[key][2]
        for quad in mesh.quads
        if quad.transverse_band_index == 2 and quad.transverse_role == "deck"
        for key in quad.node_keys
    )
    assert abs(outer_top - 590.0) < 1e-6
    assert abs(centre_top - 490.0) < 1e-6


def test_model1_shaped_pier_and_foundation_bounds():
    mesh = generate_mesh(_tree_with_nl(100), MeshPatch())
    node_map = {node.key: node.point for node in mesh.nodes}

    shaft_quads = [quad for quad in mesh.quads if quad.group == "pier-2-shaft"]
    shaft_points = [node_map[key] for quad in shaft_quads for key in quad.node_keys]
    assert abs(min(point[0] for point in shaft_points) - 980.0) < 1e-6
    assert abs(max(point[0] for point in shaft_points) - 1290.0) < 1e-6
    assert abs(min(point[2] for point in shaft_points) + 500.0) < 1e-6
    assert abs(max(point[2] for point in shaft_points) - 0.0) < 1e-6

    shaft_y_min = min(
        node_map[quad.node_keys[0]][1] - quad.thickness / 2 for quad in shaft_quads
    )
    shaft_y_max = max(
        node_map[quad.node_keys[0]][1] + quad.thickness / 2 for quad in shaft_quads
    )
    assert abs(shaft_y_min + 328.0) < 1e-6
    assert abs(shaft_y_max - 355.0) < 1e-6

    foundation_quads = [quad for quad in mesh.quads if quad.group == "pier-2-foundation"]
    foundation_points = [node_map[key] for quad in foundation_quads for key in quad.node_keys]
    assert abs(min(point[0] for point in foundation_points) - 930.0) < 1e-6
    assert abs(max(point[0] for point in foundation_points) - 1340.0) < 1e-6
    assert abs(min(point[2] for point in foundation_points) + 600.0) < 1e-6
    assert abs(max(point[2] for point in foundation_points) + 500.0) < 1e-6
    foundation_y_min = min(
        node_map[quad.node_keys[0]][1] - quad.thickness / 2 for quad in foundation_quads
    )
    foundation_y_max = max(
        node_map[quad.node_keys[0]][1] + quad.thickness / 2 for quad in foundation_quads
    )
    assert abs(foundation_y_min + 385.0) < 1e-6
    assert abs(foundation_y_max - 415.0) < 1e-6


def test_model1_target_mesh_99_100_101_never_collapses():
    counts = {}
    for target in (99, 100, 101):
        mesh = generate_mesh(_tree_with_nl(target), MeshPatch())
        validation = mesh.metadata["geometryValidation"]
        assert validation["valid"] is True
        assert validation["repeatedNodeQuads"] == 0
        assert validation["zeroAreaQuads"] == 0
        assert validation["selfIntersectingQuads"] == 0
        counts[target] = (len(mesh.nodes), len(mesh.quads))

    # 99 crosses the 100-unit ring-thickness threshold and therefore creates
    # two radial ring rows; 100 and 101 remain one-row meshes.
    assert counts[99][1] > counts[100][1]
    assert counts[100] == counts[101]


def _canonical_geometry(path: Path):
    tree = etree.parse(str(path), etree.XMLParser(huge_tree=True))
    root = tree.getroot()
    nodes = {
        int(node.get("Key")): tuple(round(float(value), 8) for value in node.get("Point").split(";"))
        for node in root.findall("./Node")
    }
    quads = []
    for quad in root.findall("./Quad"):
        points = [nodes[int(quad.get(f"NodeKey{i}"))] for i in range(1, 5)]
        candidates = []
        for sequence in (points, list(reversed(points))):
            for offset in range(4):
                candidates.append(tuple(sequence[offset:] + sequence[:offset]))
        thickness = tuple(sorted(round(float(quad.get(f"Thickness{i}")), 8) for i in range(1, 5)))
        quads.append((min(candidates), quad.get("MaterialKey"), quad.get("LayerKey"), thickness))
    return Counter(nodes.values()), Counter(quads)


def test_histra_101_reference_has_same_geometry_as_100():
    reference_101 = ROOT / "tests" / "fixtures" / "Model1_101.hrx"
    assert _canonical_geometry(MODEL1) == _canonical_geometry(reference_101)
