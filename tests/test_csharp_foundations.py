"""C#-parity tests for abutment/pier shafts and foundations."""
from __future__ import annotations

from collections import Counter

import pytest

from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh
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
from histra_builder.generator.csharp_writer import generate_csharp_bridge_hrx
from histra_builder.generator.csharp_import import _abutment, _pier
from histra_builder.generator.materials import DEFAULT_TEMPLATES
from lxml import etree


def _foundation_spec() -> CSharpBridgeSpec:
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=200.0,
            width_top_pile=200.0,
            nl=50.0,
            corsias=[Corsia(200.0)],
        ),
        elements=[
            Abutment(
                b2=60.0,
                H=100.0,
                Hf=50.0,
                material_key=18,
                material_foundation_key=18,
                kind="Sinistra",
            ),
            Span(
                L=400.0,
                W=200.0,
                f=100.0,
                Tb=30.0,
                Tt=25.0,
                Asx=36.8699,
                Adx=36.8699,
                material_key=18,
            ),
            Pier(
                b2=60.0,
                H=150.0,
                Hf=60.0,
                material_key=18,
                material_foundation_key=18,
            ),
            Span(
                L=400.0,
                W=200.0,
                f=100.0,
                Tb=30.0,
                Tt=25.0,
                Asx=36.8699,
                Adx=36.8699,
                material_key=18,
            ),
            Abutment(
                b2=60.0,
                H=100.0,
                Hf=50.0,
                material_key=18,
                material_foundation_key=18,
                kind="Destra",
            ),
        ],
        elevations=Elevations([Elevation(0.0, 180.0, 0.0, 0.0)]),
    )


def test_csharp_supports_generate_shafts_and_foundations() -> None:
    mesh = build_csharp_bridge_mesh(_foundation_spec())
    groups = Counter(quad.group for quad in mesh.quads.values())
    assert groups["CSharp_Pier"] == 14
    assert groups["CSharp_Foundation"] == 8
    # Two pier springings and two shafted abutment springings.
    assert groups["CSharp_Pulvino"] == 4
    assert len(mesh.geometry_line_restraints) == 4
    assert len(mesh.restraints) == 6
    # One abutment edge + two pier edges + one right-abutment edge.
    assert [glr.b for glr in mesh.geometry_line_restraints] == [200.0] * 4


def test_csharp_supports_load_and_prepare(tmp_path) -> None:
    pytest.importorskip("histra", reason="install histra-python to run the solver integration tests")
    from histra.io.hr_loader import load_model
    from histra.preprocessing.prepare_model import prepare_model

    path = tmp_path / "foundations.hrx"
    path.write_bytes(generate_csharp_bridge_hrx(_foundation_spec(), include_scour_analyses=False))
    model = load_model(path)
    assert len(model.collections.restraints) == 6
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.restraint_interfaces == 6


def test_inclined_straight_model_loads_and_prepares(tmp_path) -> None:
    pytest.importorskip("histra", reason="install histra-python to run the solver integration tests")
    from histra.io.hr_loader import load_model
    from histra.preprocessing.prepare_model import prepare_model

    spec = _foundation_spec()
    spec.definition.inclination_angle = 15.0
    for support in [*spec.abutments, *spec.piers]:
        support.w2 = spec.definition.width
    path = tmp_path / "inclined.hrx"
    path.write_bytes(generate_csharp_bridge_hrx(spec, include_scour_analyses=False))
    report = prepare_model(load_model(path), force=True)
    assert report.prepared is True
    assert report.restraint_interfaces == 6


def test_csharp_footed_abutment_keeps_the_springing_pulvino() -> None:
    mesh = build_csharp_bridge_mesh(_foundation_spec())
    pulvinos = [quad for quad in mesh.quads.values() if quad.group == "CSharp_Pulvino"]
    assert len(pulvinos) == 4
    left_abutment = [
        quad
        for quad in pulvinos
        if all(mesh.nodes[key].x <= 60.0 + 1.0e-6 for key in quad.node_keys)
    ]
    assert len(left_abutment) == 1
    assert min(mesh.nodes[key].z for key in left_abutment[0].node_keys) == 0.0
    assert max(mesh.nodes[key].z for key in left_abutment[0].node_keys) > 0.0


def test_passive_pressure_is_not_silently_omitted() -> None:
    spec = _foundation_spec()
    spec.piers[0].spinta_passiva_sx = True
    with pytest.raises(NotImplementedError, match="Passive earth-pressure"):
        build_csharp_bridge_mesh(spec)


def test_shaft_reinforcement_adds_native_side_blocks_and_supports() -> None:
    spec = _foundation_spec()
    pier = spec.piers[0]
    pier.Hf = 0.0
    pier.is_reinf_left = pier.is_reinf_right = True
    pier.TreinfTopLeft, pier.TreinfBotLeft = 10.0, 20.0
    pier.TreinfTopRight, pier.TreinfBotRight = 15.0, 25.0
    mesh = build_csharp_bridge_mesh(spec)
    reinforcement = [q for q in mesh.quads.values() if q.group == "CSharp_Reinforcement"]
    assert len(reinforcement) == 6  # two sides, three rows each
    supports = [r for r in mesh.restraints if r.foundation_tag == "pier_1"]
    assert len(supports) == 4  # one per side, plus two main shaft columns
    bottom_edges = [r for r in supports if mesh.quads[r.computational_element_key].group == "CSharp_Reinforcement"]
    assert sorted(abs(mesh.nodes[r.node_key2].x - mesh.nodes[r.node_key1].x)
                  for r in bottom_edges) == [20.0, 25.0]


def test_import_preserves_reinforcement_material_keys() -> None:
    raw = {"MaterialReinforcementLeftKey": "41", "MaterialReinforcementRightKey": "42"}
    for parse in (_abutment, _pier):
        element = parse(raw)
        assert element.material_reinforcement_left_key == 41
        assert element.material_reinforcement_right_key == 42


def test_reinforcement_requires_its_material_template_for_export() -> None:
    spec = _foundation_spec()
    pier = spec.piers[0]
    pier.is_reinf_left = True
    pier.TreinfTopLeft = pier.TreinfBotLeft = 10.0
    with pytest.raises(ValueError, match="Missing material templates.*24"):
        generate_csharp_bridge_hrx(spec)
    template = dict(DEFAULT_TEMPLATES[0], Key="24", Name="Example reinforcement")
    root = etree.fromstring(generate_csharp_bridge_hrx(spec, templates=[*DEFAULT_TEMPLATES, template]))
    assert root.find("Template[@Key='24']") is not None
    assert root.find("Quad[@MaterialKey='24']") is not None
