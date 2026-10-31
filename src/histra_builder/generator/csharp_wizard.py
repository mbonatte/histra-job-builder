"""C#-style ``WizardData`` serialization for parity models."""
from __future__ import annotations

from typing import Iterable

from lxml import etree

from .csharp_model import (
    Abutment,
    BridgeDefinition,
    CSharpBridgeSpec,
    Corsia,
    Elevation,
    Elevations,
    Pier,
    Span,
)


def _s(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _add_children(parent: etree._Element, tag: str, item_tag: str, items: Iterable[dict]) -> None:
    container = etree.SubElement(parent, tag)
    for attrs in items:
        etree.SubElement(container, item_tag, attrib={key: _s(value) for key, value in attrs.items()})


def _bridge_definition(spec: CSharpBridgeSpec) -> etree._Element:
    definition: BridgeDefinition = spec.definition
    element = etree.Element(
        "BridgeDefinition",
        attrib={
            "Width": _s(definition.width),
            "WidthTopPile": _s(definition.width_top_pile),
            "IsWidthTopPileCustom": "false",
            "Nl": _s(definition.nl),
            "Nt": _s(definition.nt),
            "InclinationAngle": _s(definition.inclination_angle),
            "Slope": _s(definition.slope),
            "ThicknessBallast": _s(definition.thickness_ballast),
            "ThicknessRiempimento": _s(definition.thickness_riempimento),
            "Zlevel": _s(definition.zlevel),
            "Origin": "0;0;0",
        },
    )
    _add_children(
        element,
        "Corsie",
        "Corsia",
        [
            {
                "Key": index,
                "Name": corsia.name,
                "Description": corsia.name,
                "Width": corsia.width,
                "Height": corsia.height,
                "AllowVehicle": "false",
                "MaterialKey": corsia.material_key,
                "LaneLoadsSchema1": 0,
                "LaneLoadsSchema1Vehicle": 0,
                "LaneLoadsSchema2": 0,
                "LaneLoadsSchema3": 0,
                "LaneLoadsSchema4": 0,
                "LaneLoadsSchema5": 0,
            }
            for index, corsia in enumerate(definition.corsias)
        ],
    )
    _add_children(
        element,
        "Trunks",
        "Trunk",
        [
            {
                "Id": 1,
                "Key": 1,
                "Name": "Straight",
                "Trunk": "Straight",
                "R": 4000,
                "X": 0,
            }
        ],
    )
    etree.SubElement(element, "Zlevels")
    etree.SubElement(element, "Binaries")
    etree.SubElement(element, "MasonryBridgeWalls")
    return element


def _element_attributes(element: Abutment | Pier | Span) -> dict[str, str]:
    base = {
        "MaterialKey": _s(element.material_key),
        "MaterialFoundationKey": _s(getattr(element, "material_foundation_key", 0)),
        "MaterialGeo1Key": _s(getattr(element, "material_geo1_key", 60)),
        "MaterialGeo2Key": _s(getattr(element, "material_geo2_key", 60)),
    }
    if isinstance(element, Span):
        base.update(
            {
                "MaterialReinforcementKey": _s(element.material_reinforcement_key),
                "MaterialPulvinoKey": _s(element.material_pulvino_key),
                "L": _s(element.L),
                "W": _s(element.W),
                "Circolare": _s(element.circolare),
                "f": _s(element.f),
                "L1": _s(element.L1),
                "L2": _s(element.L - element.L1),
                "f2": _s(element.f2),
                "ThicknessRiempimento": _s(element.thickness_riempimento),
                "Tb": _s(element.Tb),
                "Treinf": _s(element.Treinf),
                "Tb1": _s(element.Tb1),
                "Tb2": _s(element.Tb2),
                "Tt": _s(element.Tt),
                "LawS": "Constant",
                "dcMax": "100",
                "Asx": _s(element.Asx),
                "Adx": _s(element.Adx),
                "S1": _s(element.S1),
                "S2": _s(element.S2),
                "Dz": _s(element.Dz),
            }
        )
        return base

    base.update(
        {
            "H": _s(element.H),
            "Hf": _s(element.Hf),
            "b1": _s(element.b1),
            "b2": _s(element.b2),
            "b3": _s(element.b3),
            "w1": _s(element.w1),
            "w2": _s(element.w2),
            "w3": _s(element.w3),
            "VerticalAllignment": element.vertical_alignment,
            "beta1": _s(element.beta1),
            "beta2": _s(element.beta2),
            "ReinforcementLeft": _s(element.is_reinf_left),
            "TreinfTopLeft": _s(element.TreinfTopLeft),
            "TreinfBotLeft": _s(element.TreinfBotLeft),
            "MaterialReinforcementLeftKey": _s(element.material_reinforcement_left_key),
            "ReinforcementRight": _s(element.is_reinf_right),
            "TreinfTopRight": _s(element.TreinfTopRight),
            "TreinfBotRight": _s(element.TreinfBotRight),
            "MaterialReinforcementRightKey": _s(element.material_reinforcement_right_key),
            "B1f": _s(element.B1f),
            "B3f": _s(element.B3f),
            "W1f": _s(element.W1f),
            "W3f": _s(element.W3f),
            "Kx": _s(element.Kx),
            "Ky": _s(element.Ky),
            "Kz": _s(element.Kz),
            "Krx": _s(element.Krx),
            "Kry": _s(element.Kry),
            "Krz": _s(element.Krz),
            "IsFixDirX": _s(element.is_fix_dir_x),
            "IsFixDirY": _s(element.is_fix_dir_y),
            "IsFixDirZ": _s(element.is_fix_dir_z),
            "IsFixRotDirX": _s(element.is_fix_rot_dir_x),
            "IsFixRotDirY": _s(element.is_fix_rot_dir_y),
            "IsFixRotDirZ": _s(element.is_fix_rot_dir_z),
            "SpintaPassivaSX": _s(getattr(element, "spinta_passiva_sx", False)),
            "SpintaPassivaDX": _s(getattr(element, "spinta_passiva_dx", False)),
            "Hsp1": _s(getattr(element, "Hsp1", 0.0)),
            "Hsp2": _s(getattr(element, "Hsp2", 0.0)),
            "Xstart": "0",
            "Xend": "0",
            "Blength": "0",
        }
    )
    if isinstance(element, Abutment):
        base["AbutmentKind"] = element.kind
    if isinstance(element, Pier):
        base["PierRimpimentoCriterion"] = "IntersezioneVerticale"
        base["Tr1"] = _s(element.Tr1)
        base["Tr2"] = _s(element.Tr2)
    return base


def _elevations(elevations: Elevations) -> etree._Element:
    element = etree.Element("Elevations", attrib={"IsStratigraphyVariable": "false"})
    sections = etree.SubElement(element, "Elevations")
    for section in elevations.elevations:
        etree.SubElement(
            sections,
            "Elevation",
            attrib={
                "X": _s(section.X),
                "H1": _s(section.H1),
                "H2": _s(section.H2),
                "H3": _s(section.H3),
            },
        )
    for index, (material1, material2, row_index, generate) in enumerate(
        (
            (
                elevations.layer1_material_key,
                elevations.layer1_material_key2,
                elevations.layer1_row_index,
                elevations.layer1_generate,
            ),
            (
                elevations.layer2_material_key,
                elevations.layer2_material_key2,
                elevations.layer2_row_index,
                elevations.layer2_generate,
            ),
            (
                elevations.layer3_material_key,
                elevations.layer3_material_key2,
                elevations.layer3_row_index,
                elevations.layer3_generate,
            ),
        ),
        start=1,
    ):
        etree.SubElement(
            element,
            f"Layer{index}",
            attrib={
                "MaterialKey": _s(material1),
                "MaterialKey2": _s(material2),
                "UniformMaterial": "true",
                "RowIndexMaterial": _s(row_index),
                "GenerateComputationalElements": _s(generate),
            },
        )
    return element


def build_wizard_data(spec: CSharpBridgeSpec) -> etree._Element:
    wizard = etree.Element("WizardData", attrib={"TypeOf": "HiStrA.Objects.WizardBridge"})
    etree.SubElement(wizard, "SchemaCombinationDataList")
    wizard.append(_bridge_definition(spec))
    for element in spec.elements:
        if isinstance(element, Span):
            tag = "Span"
        elif isinstance(element, Pier):
            tag = "Pier"
        elif isinstance(element, Abutment):
            tag = "Abutment"
        else:
            continue
        node = etree.SubElement(wizard, tag, attrib=_element_attributes(element))
        if isinstance(element, Pier):
            etree.SubElement(
                node,
                "ReferenceSystem",
                E1="1;0;0",
                E2="0;1;0",
                E3="0;0;1",
                Origin=f"{spec_width_center(element, spec)};0;0",
            )
    wizard.append(_elevations(spec.elevations))
    return wizard


def spec_width_center(element: Pier, spec: CSharpBridgeSpec) -> str:
    """Pier reference origin written by the legacy writer; kept local to avoid coupling."""
    from .csharp_mesher import CSharpMesher

    centre = CSharpMesher(spec)._element_origin(element)
    return _s(centre)


def replace_wizard_data(root: etree._Element, spec: CSharpBridgeSpec) -> None:
    old = root.find("WizardData")
    new = build_wizard_data(spec)
    if old is None:
        root.insert(0, new)
        return
    index = root.index(old)
    root.remove(old)
    root.insert(index, new)
