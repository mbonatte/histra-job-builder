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


def test_bridge3_exterior_strips_with_wizard_generated_footings() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    # The saved reference has 12 extra manually remeshed abutment quads per
    # strip. The wizard-generated footings use a different subdivision.
    for y in (160.5, -160.5):
        assert _strip_materials(mesh, y) == Counter({141: 308, 18: 56, 22: 6})
    assert len(mesh.geometry_line_restraints) == 18
    assert len(mesh.restraints) == 48


def test_bridge3_interior_strip_matches_native_fill_quad_count() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    # The native interior strip has 208 fill quads; our fill geometry matches.
    assert sum(
        1
        for quad in mesh.quads.values()
        if abs(mesh.nodes[quad.node_keys[0]].y) < 1.0e-6
        and quad.material_key == 19
    ) == 208


def test_bridge3_quad_thickness_follows_each_unequal_strip() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURE))
    for quad in mesh.quads.values():
        y = mesh.nodes[quad.node_keys[0]].y
        assert quad.thickness == (288.0 if abs(y) < 1e-6 else 33.0)
