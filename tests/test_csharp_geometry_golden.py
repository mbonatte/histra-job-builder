"""Whole-model geometry snapshots extracted from saved C# models.

Coordinates and thickness are rounded to 0.1 cm before hashing. Material
keys are checked separately because saved models may contain later edits.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh

FIXTURES = Path(__file__).parent / "fixtures" / "csharp"


@pytest.mark.parametrize(
    ("wizard", "count", "digest"),
    [
        ("bridge1_wizard.hrx", 914, "c6f704f18cdfa86e686a833b59b6ba50de71690416488324a99658e4a8a9009d"),
        ("bridge_scour_3d_wizard.hrx", 2520, "d3d657ab17062c0d6f26a7a996f42c7890385566cfc9fb8078570479efd464a0"),
    ],
)
def test_native_quad_geometry_snapshot(wizard: str, count: int, digest: str) -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURES / wizard))

    def rounded(value: float) -> float:
        value = round(value, 1)
        return 0.0 if value == 0 else value

    rows = []
    for quad in mesh.quads.values():
        points = [mesh.nodes[key] for key in quad.node_keys]
        coords = sorted([[rounded(p.x), rounded(p.y), rounded(p.z)] for p in points])
        rows.append([coords, rounded(quad.thickness)])
    assert len(rows) == count
    actual = hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()
    assert actual == digest


def test_scour3d_all_native_quad_materials_and_geometry() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURES / "bridge_scour_3d_wizard.hrx"))

    def rounded(value: float) -> float:
        value = round(value, 1)
        return 0.0 if value == 0 else value

    rows = []
    for quad in mesh.quads.values():
        points = [mesh.nodes[key] for key in quad.node_keys]
        coords = sorted([[rounded(p.x), rounded(p.y), rounded(p.z)] for p in points])
        rows.append([coords, quad.material_key, rounded(quad.thickness)])
    actual = hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()
    assert actual == "1d4fc6c892746837312756261e4c4ca28e12b6dca14cb1077be045b66767eaa0"


def test_scour3d_native_quad_winding() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURES / "bridge_scour_3d_wizard.hrx"))

    def rounded(value: float) -> float:
        value = round(value, 1)
        return 0.0 if value == 0 else value

    rows = []
    for quad in mesh.quads.values():
        points = [mesh.nodes[key] for key in quad.node_keys]
        coords = [(rounded(p.x), rounded(p.y), rounded(p.z)) for p in points]
        rows.append(min(tuple(coords[i:] + coords[:i]) for i in range(4)))
    actual = hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()
    assert actual == "cb37d4f6a2a76909ecfc2f2e9a7324e7154f665e0eb546a2d82bf835a4e1b7fb"


def test_scour3d_native_restraint_to_quad_connections() -> None:
    mesh = build_csharp_bridge_mesh(spec_from_hrx(FIXTURES / "bridge_scour_3d_wizard.hrx"))

    def coords(points):
        def rounded(value):
            value = round(value, 1)
            return 0.0 if value == 0 else value
        return sorted([[rounded(p.x), rounded(p.y), rounded(p.z)] for p in points])

    rows = []
    for restraint in mesh.restraints:
        quad = mesh.quads[restraint.computational_element_key]
        nodes = [mesh.nodes[key] for key in quad.node_keys]
        footprint = (restraint.point1, restraint.point2, restraint.point3, restraint.point4)
        rows.append([coords(nodes), coords(footprint), restraint.computational_element_edge])
    actual = hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()
    assert len(rows) == 136
    assert actual == "5a71db15040177e4e1aecfa733b03bded5aa5cb2c3aab799f161c1e7302d39c9"
