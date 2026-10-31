"""Asymmetric arch and long multi-span parity checks."""
from __future__ import annotations

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


def _asymmetric_spec() -> CSharpBridgeSpec:
    spans = [
        Span(
            L=300.0 + index * 40.0,
            W=240.0,
            f=70.0 + index * 8.0,
            Tb=25.0 + index * 2.0,
            Tt=22.0 + index,
            S1=2.0 + index,
            S2=3.0 + index,
            Asx=32.0 + index,
            Adx=38.0 + index,
        )
        for index in range(4)
    ]
    elements = [Abutment(b2=60.0, H=80.0, Hf=40.0, kind="Sinistra")]
    for index, span in enumerate(spans):
        elements.append(span)
        if index < 3:
            elements.append(
                Pier(
                    b2=70.0 + index * 5.0,
                    H=150.0 + index * 20.0,
                    Hf=50.0,
                    material_foundation_key=141,
                )
            )
    elements.append(Abutment(b2=60.0, H=80.0, Hf=40.0, kind="Destra"))
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=240.0,
            width_top_pile=240.0,
            nl=60.0,
            corsias=[Corsia(120.0), Corsia(120.0)],
        ),
        elements=elements,
        elevations=Elevations([Elevation(0.0, 200.0, 0.0, 0.0)]),
    )


def test_asymmetric_four_span_chain_builds_and_prepares(tmp_path) -> None:
    mesh = build_csharp_bridge_mesh(_asymmetric_spec())
    assert len(mesh.nodes) > 0
    assert len(mesh.quads) > 0
    assert len(mesh.geometry_line_restraints) == 32
    assert len(mesh.piers) == 3

    path = tmp_path / "asymmetric.hrx"
    path.write_bytes(
        generate_csharp_bridge_hrx(_asymmetric_spec(), include_scour_analyses=False)
    )
    model = load_model(path)
    assert len(model.collections.quads) == len(mesh.quads)
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.restraint_interfaces == 32
