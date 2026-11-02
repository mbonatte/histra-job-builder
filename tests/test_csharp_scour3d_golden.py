"""Golden checks against the native Bridge_scour_3d model."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "bridge_scour_3d_wizard.hrx"
GEOMETRY = FIXTURE.with_name("bridge_scour_3d_geometry.json")


def test_scour3d_wizard_has_eight_strips_and_pier_wings() -> None:
    spec = spec_from_hrx(FIXTURE)
    assert len(spec.definition.corsias) == 8
    assert all(corsia.width == 36.0 for corsia in spec.definition.corsias)
    assert len(spec.piers) == 2
    for pier in spec.piers:
        assert (pier.Hf, pier.B1f, pier.B3f, pier.W1f, pier.W3f) == (
            70.0,
            50.0,
            50.0,
            25.0,
            25.0,
        )


def test_scour3d_matches_native_quad_material_and_glr_counts() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    assert len(mesh.nodes) == 3216
    assert len(mesh.quads) == 2520
    assert len(mesh.geometry_line_restraints) == 96
    assert len(mesh.restraints) == 136
    assert len(mesh.node_cs) == 172
    assert Counter(quad.material_key for quad in mesh.quads.values()) == Counter(
        {19: 1664, 18: 448, 141: 360, 22: 48}
    )
    centers = Counter(
        round(mesh.nodes[quad.node_keys[0]].y, 1) for quad in mesh.quads.values()
    )
    assert set(centers) == {
        -156.5,
        -126.0,
        -90.0,
        -54.0,
        -18.0,
        18.0,
        54.0,
        90.0,
        126.0,
        156.5,
    }
    # The two wing foundations carry 36 quads each.
    assert centers[156.5] == 36
    assert centers[-156.5] == 36


def test_foundation_restraints_cover_each_subdivided_quad_edge() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    by_parent = {}
    for restraint in mesh.restraints:
        quad = mesh.quads[restraint.computational_element_key]
        assert {restraint.node_key1, restraint.node_key2} == set(quad.node_keys[:2])
        by_parent.setdefault(restraint.parent_key, []).append(restraint)

    assert any(len(restraints) > 1 for restraints in by_parent.values())
    for glr in mesh.geometry_line_restraints:
        parent_nodes = (mesh.nodes[glr.node_key1], mesh.nodes[glr.node_key2])
        segments = sorted(
            (mesh.nodes[r.node_key1].x, mesh.nodes[r.node_key2].x)
            for r in by_parent[glr.key]
        )
        assert abs(segments[0][0] - min(p.x for p in parent_nodes)) < 1e-4
        assert abs(segments[-1][1] - max(p.x for p in parent_nodes)) < 1e-4
        assert all(abs(a[1] - b[0]) < 1e-4 for a, b in zip(segments, segments[1:]))


def test_scour3d_native_geometry_and_restraint_footprints() -> None:
    reference = json.loads(GEOMETRY.read_text())
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))

    def signature(points):
        return tuple(sorted(tuple(round(value, 1) for value in point) for point in points))

    expected_quads = Counter(
        (tuple(tuple(point) for point in coords), material, thickness)
        for coords, material, thickness in reference["quads"]
    )
    actual_quads = Counter()
    for quad in mesh.quads.values():
        points = [mesh.nodes[key] for key in quad.node_keys]
        if abs(points[0].y - reference["strip_y"]) < 1e-6:
            actual_quads[(signature((p.x, p.y, p.z) for p in points),
                          quad.material_key, round(quad.thickness, 1))] += 1
    assert actual_quads == expected_quads

    expected_footprints = Counter(
        tuple(tuple(point) for point in footprint)
        for footprint in reference["restraint_footprints"]
    )
    actual_footprints = Counter(
        signature((p.x, p.y, p.z) for p in (r.point1, r.point2, r.point3, r.point4))
        for r in mesh.restraints
    )
    assert actual_footprints == expected_footprints
