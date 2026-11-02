"""Native HRX writer integration for the C#-parity mesh."""
from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

import pytest

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
from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_import import spec_from_wizard_data
from histra_builder.generator.csharp_wizard import _bridge_definition

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "model_chain_2span.json"


def test_import_preserves_native_material_templates_on_regeneration(tmp_path: Path) -> None:
    root = etree.fromstring(generate_csharp_bridge_hrx(_spec()))
    template = root.find("Template[@Key='18']")
    assert template is not None
    template.set("Name", "Project masonry")
    template.set("E_med", "1234")
    path = tmp_path / "source.hrx"
    path.write_bytes(etree.tostring(root))
    spec = spec_from_hrx(path)
    regenerated = etree.fromstring(generate_csharp_bridge_hrx(spec))
    actual = regenerated.find("Template[@Key='18']")
    assert actual is not None
    assert actual.get("Name") == "Project masonry"
    assert actual.get("E_med") == "1234"


def test_streaming_import_preserves_captured_subtrees_amid_nested_results(tmp_path: Path, monkeypatch) -> None:
    root = etree.fromstring(generate_csharp_bridge_hrx(_spec()))
    results = etree.Element("Results")
    for index in range(100):
        step = etree.SubElement(results, "Step", Key=str(index))
        for value in range(10):
            etree.SubElement(step, "Result", Value=str(value))
    root.insert(0, results)
    before = etree.Element("Template", Key="301", TypeOf="HiStrA.Objects.MasonryMaterial", Name="Before")
    root.insert(0, before)
    etree.SubElement(root, "Template", Key="302", TypeOf="HiStrA.Objects.MasonryMaterial", Name="After")
    nested = etree.SubElement(root, "Template", Key="303", TypeOf="HiStrA.Objects.MasonryMaterial")
    etree.SubElement(nested, "Child")
    path = tmp_path / "nested-results.hrx"
    path.write_bytes(etree.tostring(root))

    original_iterparse = etree.iterparse
    cleaned = []

    def checked_iterparse(*args, **kwargs):
        for event, element in original_iterparse(*args, **kwargs):
            yield event, element
            if event == "end" and element.tag == "Result":
                cleaned.append(element.getprevious() is None)

    monkeypatch.setattr(etree, "iterparse", checked_iterparse)
    spec = spec_from_hrx(path)
    materials = {item["Key"]: item for item in spec.material_templates}
    assert materials["301"]["Name"] == "Before"
    assert materials["302"]["Name"] == "After"
    assert "303" not in materials
    assert len(spec.spans) == 2
    assert len(spec.definition.corsias) == 3
    assert len(cleaned) == 1000
    assert all(cleaned)


def test_curved_trunk_is_preserved_and_not_silently_meshed_as_straight() -> None:
    root = etree.fromstring(generate_csharp_bridge_hrx(_spec()))
    wizard = root.find("WizardData")
    trunk = wizard.find("BridgeDefinition/Trunks/Trunk")
    trunk.set("Trunk", "CurveOnLeft")
    trunk.set("R", "2500")
    spec = spec_from_wizard_data(wizard)
    actual = _bridge_definition(spec).find("Trunks/Trunk")
    assert actual.get("Trunk") == "CurveOnLeft"
    assert actual.get("R") == "2500"
    with pytest.raises(NotImplementedError, match="Curved"):
        generate_csharp_bridge_hrx(spec)


def test_railbridge2_wizard_is_recognized_and_not_silently_meshed() -> None:
    root = etree.fromstring(generate_csharp_bridge_hrx(_spec()))
    root.set("WizardType", "RailBridge2")
    spec = spec_from_wizard_data(root.find("WizardData"))
    assert spec.wizard_type == "RailBridge2"
    with pytest.raises(NotImplementedError, match="RailBridge2"):
        generate_csharp_bridge_hrx(spec)


def test_import_preserves_lane_load_configuration() -> None:
    root = etree.fromstring(generate_csharp_bridge_hrx(_spec()))
    definition = root.find("WizardData/BridgeDefinition")
    definition.set("IsVehicleLoad", "true")
    definition.set("VehicleLoadName", "Custom vehicle")
    lane = root.find("WizardData/BridgeDefinition/Corsie/Corsia")
    lane.set("AllowVehicle", "true")
    lane.set("LaneLoadsSchema1", "37")
    lane.set("LaneLoadsSchema1Vehicle", "14")
    lane.set("Description", "User lane")
    spec = spec_from_wizard_data(root.find("WizardData"))
    actual_definition = _bridge_definition(spec)
    assert actual_definition.get("IsVehicleLoad") == "true"
    assert actual_definition.get("VehicleLoadName") == "Custom vehicle"
    actual = actual_definition.find("Corsie/Corsia")
    assert actual.get("AllowVehicle") == "true"
    assert actual.get("LaneLoadsSchema1") == "37"
    assert actual.get("LaneLoadsSchema1Vehicle") == "14"
    assert actual.get("Description") == "User lane"
    with pytest.raises(NotImplementedError, match="vehicle-load"):
        generate_csharp_bridge_hrx(spec)


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
    pytest.importorskip("histra", reason="install histra-python to run the solver integration tests")
    from histra.io.hr_loader import load_model
    from histra.preprocessing.prepare_model import prepare_model

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


def test_generate_bridge_hrx_dispatches_csharp_spec() -> None:
    from histra_builder.generator import generate_bridge_hrx

    root = etree.fromstring(
        generate_bridge_hrx(_spec(), include_scour_analyses=False)
    )
    assert len(root.findall("Quad")) == 156
    assert root.find("Bridge") is not None
    assert len(root.findall("GeometryLineRestraint")) == 12


def test_csharp_wizard_data_matches_native_children_and_core_attributes() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    native_wizard = fixture["wizard"]
    root = etree.fromstring(
        generate_csharp_bridge_hrx(_spec(), include_scour_analyses=False)
    )
    wizard = root.find("WizardData")
    assert wizard is not None
    assert wizard.get("TypeOf") == "HiStrA.Objects.WizardBridge"

    native_definition = native_wizard["bridge_definition"]
    definition = wizard.find("BridgeDefinition")
    assert definition is not None
    assert set(definition.attrib) == set(native_definition), "BridgeDefinition attributes differ"
    for attribute in (
        "Width",
        "WidthTopPile",
        "Nl",
        "Nt",
        "InclinationAngle",
        "Slope",
        "Zlevel",
        "ThicknessBallast",
        "ThicknessRiempimento",
    ):
        assert float(definition.get(attribute)) == pytest.approx(
            float(native_definition[attribute])
        )

    corsias = definition.findall("Corsie/Corsia")
    assert [float(item.get("Width")) for item in corsias] == [100.0, 100.0, 100.0]
    assert len(definition.findall("Trunks/Trunk")) == 1
    assert definition.find("Zlevels") is not None
    assert definition.find("Binaries") is not None
    assert definition.find("MasonryBridgeWalls") is not None

    for tag, native_items in (
        ("Abutment", native_wizard["abutments"]),
        ("Span", native_wizard["spans"]),
        ("Pier", native_wizard["piers"]),
    ):
        generated = wizard.findall(tag)
        assert len(generated) == len(native_items)
        for actual, expected in zip(generated, native_items):
            assert set(actual.attrib) == set(expected), f"{tag} attribute set differs from native"
            for attribute in ("MaterialKey", "MaterialFoundationKey"):
                if attribute in expected:
                    assert actual.get(attribute) == expected[attribute]
            if tag != "Span":
                for attribute in ("H", "Hf", "b1", "b2", "b3", "w1", "w2", "w3"):
                    assert float(actual.get(attribute)) == pytest.approx(
                        float(expected[attribute])
                    )
            else:
                for attribute in (
                    "L",
                    "W",
                    "f",
                    "Tb",
                    "Tb1",
                    "Tb2",
                    "Tt",
                    "Asx",
                    "Adx",
                    "S1",
                    "S2",
                    "Dz",
                ):
                    assert float(actual.get(attribute)) == pytest.approx(
                        float(expected[attribute])
                    )

    sections = wizard.findall("Elevations/Elevations/Elevation")
    assert len(sections) == 1
    assert float(sections[0].get("H1")) == pytest.approx(126.5)
    layers = [
        wizard.find("Elevations/Layer1"),
        wizard.find("Elevations/Layer2"),
        wizard.find("Elevations/Layer3"),
    ]
    assert [layer.get("MaterialKey") for layer in layers] == ["19", "20", "21"]
    assert all(layer.get("GenerateComputationalElements") == "true" for layer in layers)


def test_csharp_writer_emits_native_model_point_and_analysis_linkage() -> None:
    root = etree.fromstring(
        generate_csharp_bridge_hrx(_spec(), include_scour_analyses=False)
    )
    points = root.findall("ModelPoint")
    assert len(points) == 1
    assert points[0].get("ElementType") == "Node"
    node_key = points[0].get("ElementKey")
    assert root.xpath(f"/HiStrA/Node[@Key='{node_key}']")[0].get("IsModelPoint") == "true"
    vert = root.xpath("/HiStrA/Analysis[@Name='Vert']")[0]
    assert vert.get("MasterPoint") == points[0].get("Key")
    assert "Base Analysis" in vert.get("Description", "")


def test_csharp_writer_emits_native_quad_nodec_modelpoint_attributes() -> None:
    root = etree.fromstring(
        generate_csharp_bridge_hrx(_spec(), include_scour_analyses=False)
    )
    node = root.find("Node")
    assert node is not None
    assert node.get("LayerKey") == "0"
    assert node.get("IsPropertyModified") == "false"
    quad = root.find("Quad")
    assert quad is not None
    assert quad.get("IsPropertyModified") == "false"
    assert quad.get("U7") == "0"
    node_c = root.find("NodeC")
    assert node_c is not None
    assert len(node_c.findall("AfferenceMatrices/AfferenceMatrix")) == 6
    assert node_c.find("ReferenceSystem") is not None
    model_point = root.find("ModelPoint")
    assert model_point is not None
    assert model_point.get("Point")
    assert model_point.get("Ux") == "0"
    analysis = root.find("Analysis")
    assert analysis is not None
    assert analysis.find("DynamicLoads") is not None
    assert analysis.find("AdapticPhases") is not None


def test_csharp_writer_native_name_and_gamma_attributes() -> None:
    root = etree.fromstring(
        generate_csharp_bridge_hrx(_spec(), include_scour_analyses=False)
    )
    assert root.find("NodeC").get("Name") == root.find("NodeC").get("Key")
    assert root.find("ModelPoint").get("Name") == root.find("ModelPoint").get("Key")
    gravity = root.find("LoadCondition")
    for attribute in (
        "GammaFavEQU",
        "GammaUnfavEQU",
        "GammaFavSTR",
        "GammaUnfavSTR",
        "GammaFavGEO",
        "GammaUnfavGEO",
    ):
        assert gravity.get(attribute) == "1"
