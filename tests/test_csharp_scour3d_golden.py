"""Golden checks against the native Bridge_scour_3d model."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "bridge_scour_3d_wizard.hrx"


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
    assert len(mesh.quads) == 2520
    assert len(mesh.geometry_line_restraints) == 96
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
