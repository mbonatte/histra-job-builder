"""Multi-layer elevation fill tests for the C#-parity mesher."""
from __future__ import annotations

from collections import Counter

import pytest
from lxml import etree

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
from histra_builder.generator.csharp_wizard import _elevations as write_elevations
from histra_builder.generator.csharp_import import _elevations as read_elevations


def _multilayer_spec() -> CSharpBridgeSpec:
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=200.0,
            width_top_pile=200.0,
            nl=50.0,
            corsias=[Corsia(200.0)],
        ),
        elements=[
            Abutment(b2=60.0, H=0.0, Hf=0.0, kind="Sinistra"),
            Span(
                L=400.0,
                W=200.0,
                f=100.0,
                Tb=30.0,
                Tt=25.0,
                Asx=36.8699,
                Adx=36.8699,
            ),
            Pier(b2=70.0, H=150.0, Hf=0.0),
            Span(
                L=400.0,
                W=200.0,
                f=100.0,
                Tb=30.0,
                Tt=25.0,
                Asx=36.8699,
                Adx=36.8699,
            ),
            Abutment(b2=60.0, H=0.0, Hf=0.0, kind="Destra"),
        ],
        elevations=Elevations(
            [Elevation(X=0.0, H1=180.0, H2=50.0, H3=30.0)],
            layer1_material_key=19,
            layer2_material_key=20,
            layer3_material_key=21,
        ),
    )


def test_multilayer_fill_emits_all_layer_materials() -> None:
    mesh = build_csharp_bridge_mesh(_multilayer_spec())
    materials = Counter(quad.material_key for quad in mesh.quads.values())
    assert materials[19] > 0
    assert materials[20] > 0
    assert materials[21] > 0
    assert all(quad.thickness == 200.0 for quad in mesh.quads.values())
    assert mesh.deck_z == 260.0
    root = etree.fromstring(generate_csharp_bridge_hrx(_multilayer_spec()))
    assert float(root.find("Bridge").get("H")) == 260.0


@pytest.mark.parametrize("layer", [1, 2, 3])
def test_disabled_layer_does_not_emit_its_fill_quads(layer: int) -> None:
    spec = _multilayer_spec()
    setattr(spec.elevations, f"layer{layer}_generate", False)
    mesh = build_csharp_bridge_mesh(spec)
    materials = Counter(q.material_key for q in mesh.quads.values() if q.group == "CSharp_Fill")
    assert materials[18 + layer] == 0
    assert all(materials[18 + other] > 0 for other in (1, 2, 3) if other != layer)


def test_arch_is_still_generated_when_all_fill_layers_are_disabled() -> None:
    spec = _multilayer_spec()
    spec.elevations.layer1_generate = False
    spec.elevations.layer2_generate = False
    spec.elevations.layer3_generate = False
    mesh = build_csharp_bridge_mesh(spec)
    assert not any(q.group == "CSharp_Fill" for q in mesh.quads.values())
    assert any(q.group == "CSharp_Arch" for q in mesh.quads.values())


def test_nonuniform_layer_materials_round_trip_and_apply_by_row() -> None:
    spec = _multilayer_spec()
    spec.elevations.layer1_uniform = False
    spec.elevations.is_stratigraphy_variable = True
    spec.elevations.layer1_material_key2 = 141
    spec.elevations.layer1_row_index = 1
    parsed = read_elevations(write_elevations(spec.elevations))
    assert parsed.is_stratigraphy_variable is True
    assert parsed.get_material_key(1) == (19, 141, 1)
    mesh = build_csharp_bridge_mesh(spec)
    fill = Counter(q.material_key for q in mesh.quads.values() if q.group == "CSharp_Fill")
    assert fill[19] > 0
    assert fill[141] > 0


def test_fourth_layer_uses_second_layer3_material_when_nonuniform() -> None:
    elevations = _multilayer_spec().elevations
    elevations.layer3_uniform = False
    elevations.layer3_material_key2 = 141
    assert elevations.get_material_key(4) == (141, 141, -1)


def test_lane_material_override_only_accepts_masonry_templates() -> None:
    spec = _multilayer_spec()
    spec.definition.corsias[0].material_key = 301
    spec.material_templates = [{"Key": "301", "TypeOf": "HiStrA.Objects.SteelMaterial",
                                "PurposeType": "SteelMaterial"}]
    mesh = build_csharp_bridge_mesh(spec)
    assert any(q.group == "CSharp_Fill" and q.material_key == 19 for q in mesh.quads.values())
    assert not any(q.material_key == 301 for q in mesh.quads.values())


def test_multilayer_model_loads_and_prepares(tmp_path) -> None:
    pytest.importorskip("histra", reason="install histra-python to run the solver integration tests")
    from histra.io.hr_loader import load_model
    from histra.preprocessing.prepare_model import prepare_model

    path = tmp_path / "multilayer.hrx"
    path.write_bytes(
        generate_csharp_bridge_hrx(_multilayer_spec(), include_scour_analyses=False)
    )
    model = load_model(path)
    assert len(model.collections.quads) > 0
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.interfaces > 0
