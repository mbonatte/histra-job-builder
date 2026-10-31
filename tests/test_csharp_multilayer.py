"""Multi-layer elevation fill tests for the C#-parity mesher."""
from __future__ import annotations

from collections import Counter

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
from histra.io.hr_loader import load_model
from histra.preprocessing.prepare_model import prepare_model


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


def test_multilayer_model_loads_and_prepares(tmp_path) -> None:
    path = tmp_path / "multilayer.hrx"
    path.write_bytes(
        generate_csharp_bridge_hrx(_multilayer_spec(), include_scour_analyses=False)
    )
    model = load_model(path)
    assert len(model.collections.quads) > 0
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.interfaces > 0
