"""Native HRX writer integration for the C#-parity mesh."""
from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

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

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "model_chain_2span.json"


def _number(raw: dict, key: str, default: float = 0.0) -> float:
    return float(raw.get(key, default))


def _spec() -> CSharpBridgeSpec:
    wizard = json.loads(FIXTURE.read_text(encoding="utf-8"))["wizard"]
    definition = wizard["bridge_definition"]

    def abutment(raw: dict) -> Abutment:
        return Abutment(
            b1=_number(raw, "b1"),
            b2=_number(raw, "b2"),
            b3=_number(raw, "b3"),
            w1=_number(raw, "w1"),
            w2=_number(raw, "w2"),
            w3=_number(raw, "w3"),
            H=_number(raw, "H"),
            Hf=_number(raw, "Hf"),
            material_key=int(raw.get("MaterialKey", 18)),
            material_foundation_key=int(raw.get("MaterialFoundationKey", 18)),
            kind=raw.get("AbutmentKind", "Sinistra"),
        )

    abutments = [abutment(raw) for raw in wizard["abutments"]]
    spans = [
        Span(
            L=_number(raw, "L"),
            W=_number(raw, "W"),
            f=_number(raw, "f"),
            S1=_number(raw, "S1"),
            S2=_number(raw, "S2"),
            Asx=_number(raw, "Asx"),
            Adx=_number(raw, "Adx"),
            Tb=_number(raw, "Tb"),
            Tb1=_number(raw, "Tb1"),
            Tb2=_number(raw, "Tb2"),
            Tt=_number(raw, "Tt"),
            Treinf=_number(raw, "Treinf"),
            Dz=_number(raw, "Dz"),
            L1=_number(raw, "L1"),
            f1=_number(raw, "f"),
            f2=_number(raw, "f2"),
            material_key=int(raw.get("MaterialKey", 18)),
            material_pulvino_key=int(raw.get("MaterialPulvinoKey", 22)),
        )
        for raw in wizard["spans"]
    ]
    piers = [
        Pier(
            b1=_number(raw, "b1"),
            b2=_number(raw, "b2"),
            b3=_number(raw, "b3"),
            w1=_number(raw, "w1"),
            w2=_number(raw, "w2"),
            w3=_number(raw, "w3"),
            H=_number(raw, "H"),
            Hf=_number(raw, "Hf"),
            material_key=int(raw.get("MaterialKey", 18)),
            material_foundation_key=int(raw.get("MaterialFoundationKey", 18)),
        )
        for raw in wizard["piers"]
    ]
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=_number(definition, "Width"),
            width_top_pile=_number(definition, "WidthTopPile"),
            nl=_number(definition, "Nl"),
            corsias=[Corsia(100), Corsia(100), Corsia(100)],
        ),
        elements=[abutments[0], spans[0], piers[0], spans[1], abutments[1]],
        elevations=Elevations([Elevation(0, 126.5, 0, 0)]),
    )


def test_csharp_writer_emits_native_bridge_hierarchy(tmp_path: Path) -> None:
    hrx = generate_csharp_bridge_hrx(_spec(), include_scour_analyses=False)
    root = etree.fromstring(hrx)
    assert len(root.findall("Node")) == 222
    assert len(root.findall("Quad")) == 156
    assert len(root.findall("NodeC")) == 21
    assert len(root.findall("GeometryLineRestraint")) == 12
    assert len(root.findall("Restraint")) == 12
    bridge = root.find("Bridge")
    assert bridge is not None
    assert bridge.get("Key") == "1"
    assert len(bridge.findall("QuadKeys/QuadKey")) == 156
    assert len(bridge.findall("GeometryLineRestraintKeys/GeometryLineRestraintKey")) == 12
    for quad in root.findall("Quad"):
        assert quad.get("ParentKey") == "1"
        assert quad.get("ParentTypeElement") == "Bridge"
    for mean in root.findall("Restraint"):
        assert mean.get("ParentTypeElement") == "GeometryLineRestraint"
        assert mean.get("H") == "30"


def test_csharp_writer_output_loads_and_prepares(tmp_path: Path) -> None:
    path = tmp_path / "csharp_parity.hrx"
    path.write_bytes(generate_csharp_bridge_hrx(_spec(), include_scour_analyses=False))
    model = load_model(path)
    assert len(model.collections.nodes) == 222
    assert len(model.collections.quads) == 156
    assert len(model.collections.restraints) == 12
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.restraint_interfaces == 12
    assert report.interfaces > 0


def test_csharp_parity_api_is_public() -> None:
    import histra_builder

    assert histra_builder.CSharpBridgeSpec is CSharpBridgeSpec
    assert histra_builder.build_csharp_bridge_mesh is not None
    assert histra_builder.generate_csharp_bridge_hrx is not None
