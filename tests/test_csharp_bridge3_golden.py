"""Golden checks against the native Bridge_3 abutment model."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "bridge3_abutment_wizard.hrx"


def _strip_materials(mesh, y: float) -> Counter:
    return Counter(
        quad.material_key
        for quad in mesh.quads.values()
        if abs(mesh.nodes[quad.node_keys[0]].y - y) < 1.0e-6
    )


def test_bridge3_wizard_imports_with_three_strips_and_footings() -> None:
    spec = spec_from_hrx(FIXTURE)
    assert len(spec.spans) == 3
    assert len(spec.piers) == 2
    assert [corsia.width for corsia in spec.definition.corsias] == [33.0, 288.0, 33.0]
    assert [corsia.height for corsia in spec.definition.corsias] == [17.0, 0.0, 17.0]
    assert spec.abutments[0].Hf == 92.0
    assert spec.elevations.elevations[0].H1 == 122.5


def test_bridge3_exterior_strips_match_native_material_counts() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    # Native exterior strips: 320 spandrel quads, 56 arch quads, 4 pulvinos.
    for y in (160.5, -160.5):
        assert _strip_materials(mesh, y) == Counter({141: 320, 18: 56, 22: 4})
    assert len(mesh.geometry_line_restraints) == 18
    # Native RestraintMesher emits 48 restraints (multiple per GLR); that
    # expansion is tracked as a golden-dependent follow-up.


def test_bridge3_interior_strip_matches_native_fill_quad_count() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    # The native interior strip has 208 fill quads; our fill geometry matches.
    assert sum(
        1
        for quad in mesh.quads.values()
        if abs(mesh.nodes[quad.node_keys[0]].y) < 1.0e-6
        and quad.material_key == 19
    ) == 208
