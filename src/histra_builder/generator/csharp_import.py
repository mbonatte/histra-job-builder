"""Import native C# ``WizardData`` into :class:`CSharpBridgeSpec`."""
from __future__ import annotations

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


def _f(raw: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(raw.get(key, default))
    except (TypeError, ValueError):
        return default


def _i(raw: dict, key: str, default: int = 0) -> int:
    try:
        return int(raw.get(key, default))
    except (TypeError, ValueError):
        return default


def _b(raw: dict, key: str, default: bool = False) -> bool:
    value = raw.get(key)
    if value is None:
        return default
    return str(value).strip().lower() == "true"


def _abutment(raw: dict) -> Abutment:
    return Abutment(
        b1=_f(raw, "b1"),
        b2=_f(raw, "b2"),
        b3=_f(raw, "b3"),
        w1=_f(raw, "w1"),
        w2=_f(raw, "w2"),
        w3=_f(raw, "w3"),
        H=_f(raw, "H"),
        Hf=_f(raw, "Hf"),
        B1f=_f(raw, "B1f"),
        B3f=_f(raw, "B3f"),
        W1f=_f(raw, "W1f"),
        W3f=_f(raw, "W3f"),
        material_key=_i(raw, "MaterialKey", 18),
        material_foundation_key=_i(raw, "MaterialFoundationKey", 18),
        vertical_alignment=raw.get("VerticalAllignment", "Center"),
        beta1=_f(raw, "beta1"),
        beta2=_f(raw, "beta2"),
        is_reinf_left=_b(raw, "ReinforcementLeft"),
        is_reinf_right=_b(raw, "ReinforcementRight"),
        TreinfTopLeft=_f(raw, "TreinfTopLeft"),
        TreinfBotLeft=_f(raw, "TreinfBotLeft"),
        TreinfTopRight=_f(raw, "TreinfTopRight"),
        TreinfBotRight=_f(raw, "TreinfBotRight"),
        material_reinforcement_left_key=_i(raw, "MaterialReinforcementLeftKey", 24),
        material_reinforcement_right_key=_i(raw, "MaterialReinforcementRightKey", 24),
        Kx=_f(raw, "Kx"),
        Ky=_f(raw, "Ky"),
        Kz=_f(raw, "Kz", 0.1),
        Krx=_f(raw, "Krx"),
        Kry=_f(raw, "Kry"),
        Krz=_f(raw, "Krz"),
        is_fix_dir_x=_b(raw, "IsFixDirX", True),
        is_fix_dir_y=_b(raw, "IsFixDirY", True),
        is_fix_dir_z=_b(raw, "IsFixDirZ", True),
        is_fix_rot_dir_x=_b(raw, "IsFixRotDirX", True),
        is_fix_rot_dir_y=_b(raw, "IsFixRotDirY", True),
        is_fix_rot_dir_z=_b(raw, "IsFixRotDirZ", True),
        spinta_passiva_sx=_b(raw, "SpintaPassivaSX"),
        spinta_passiva_dx=_b(raw, "SpintaPassivaDX"),
        Hsp1=_f(raw, "Hsp1"),
        Hsp2=_f(raw, "Hsp2"),
        material_geo1_key=_i(raw, "MaterialGeo1Key", 60),
        material_geo2_key=_i(raw, "MaterialGeo2Key", 60),
        kind=raw.get("AbutmentKind", "Sinistra"),
    )


def _pier(raw: dict) -> Pier:
    return Pier(
        b1=_f(raw, "b1"),
        b2=_f(raw, "b2"),
        b3=_f(raw, "b3"),
        w1=_f(raw, "w1"),
        w2=_f(raw, "w2"),
        w3=_f(raw, "w3"),
        H=_f(raw, "H"),
        Hf=_f(raw, "Hf"),
        B1f=_f(raw, "B1f"),
        B3f=_f(raw, "B3f"),
        W1f=_f(raw, "W1f"),
        W3f=_f(raw, "W3f"),
        material_key=_i(raw, "MaterialKey", 18),
        material_foundation_key=_i(raw, "MaterialFoundationKey", 18),
        vertical_alignment=raw.get("VerticalAllignment", "Center"),
        beta1=_f(raw, "beta1"),
        beta2=_f(raw, "beta2"),
        is_reinf_left=_b(raw, "ReinforcementLeft"),
        is_reinf_right=_b(raw, "ReinforcementRight"),
        TreinfTopLeft=_f(raw, "TreinfTopLeft"),
        TreinfBotLeft=_f(raw, "TreinfBotLeft"),
        TreinfTopRight=_f(raw, "TreinfTopRight"),
        TreinfBotRight=_f(raw, "TreinfBotRight"),
        material_reinforcement_left_key=_i(raw, "MaterialReinforcementLeftKey", 24),
        material_reinforcement_right_key=_i(raw, "MaterialReinforcementRightKey", 24),
        Kx=_f(raw, "Kx"),
        Ky=_f(raw, "Ky"),
        Kz=_f(raw, "Kz", 0.1),
        Krx=_f(raw, "Krx"),
        Kry=_f(raw, "Kry"),
        Krz=_f(raw, "Krz"),
        is_fix_dir_x=_b(raw, "IsFixDirX", True),
        is_fix_dir_y=_b(raw, "IsFixDirY", True),
        is_fix_dir_z=_b(raw, "IsFixDirZ", True),
        is_fix_rot_dir_x=_b(raw, "IsFixRotDirX", True),
        is_fix_rot_dir_y=_b(raw, "IsFixRotDirY", True),
        is_fix_rot_dir_z=_b(raw, "IsFixRotDirZ", True),
        spinta_passiva_sx=_b(raw, "SpintaPassivaSX"),
        spinta_passiva_dx=_b(raw, "SpintaPassivaDX"),
        Hsp1=_f(raw, "Hsp1"),
        Hsp2=_f(raw, "Hsp2"),
        material_geo1_key=_i(raw, "MaterialGeo1Key", 60),
        material_geo2_key=_i(raw, "MaterialGeo2Key", 60),
        Tr1=_f(raw, "Tr1"),
        Tr2=_f(raw, "Tr2"),
    )


def _span(raw: dict) -> Span:
    return Span(
        L=_f(raw, "L"),
        W=_f(raw, "W"),
        f=_f(raw, "f"),
        S1=_f(raw, "S1"),
        S2=_f(raw, "S2"),
        Asx=_f(raw, "Asx"),
        Adx=_f(raw, "Adx"),
        Tb=_f(raw, "Tb"),
        Tb1=_f(raw, "Tb1"),
        Tb2=_f(raw, "Tb2", 100.0),
        Tt=_f(raw, "Tt"),
        Treinf=_f(raw, "Treinf"),
        Dz=_f(raw, "Dz"),
        L1=_f(raw, "L1"),
        f1=_f(raw, "f", _f(raw, "f1")),
        f2=_f(raw, "f2"),
        thickness_riempimento=_f(raw, "ThicknessRiempimento"),
        material_key=_i(raw, "MaterialKey", 18),
        material_pulvino_key=_i(raw, "MaterialPulvinoKey", 22),
        material_reinforcement_key=_i(raw, "MaterialReinforcementKey", 24),
        circolare=_b(raw, "Circolare"),
    )


def _elevations(raw: etree._Element | None) -> Elevations:
    if raw is None:
        return Elevations()
    sections = [
        Elevation(
            X=_f(section.attrib, "X"),
            H1=_f(section.attrib, "H1"),
            H2=_f(section.attrib, "H2"),
            H3=_f(section.attrib, "H3"),
        )
        for section in raw.findall("Elevations/Elevation")
    ]
    layers = {index: raw.find(f"Layer{index}") for index in (1, 2, 3)}
    attrs = {index: dict(element.attrib) if element is not None else {} for index, element in layers.items()}
    return Elevations(
        elevations=sections or [Elevation()],
        layer1_material_key=_i(attrs[1], "MaterialKey", 19),
        layer2_material_key=_i(attrs[2], "MaterialKey", 20),
        layer3_material_key=_i(attrs[3], "MaterialKey", 21),
        layer1_material_key2=_i(attrs[1], "MaterialKey2", 19),
        layer2_material_key2=_i(attrs[2], "MaterialKey2", 20),
        layer3_material_key2=_i(attrs[3], "MaterialKey2", 21),
        layer1_row_index=_i(attrs[1], "RowIndexMaterial", 1),
        layer2_row_index=_i(attrs[2], "RowIndexMaterial", 1),
        layer3_row_index=_i(attrs[3], "RowIndexMaterial", 1),
        layer1_uniform=_b(attrs[1], "UniformMaterial", True),
        layer2_uniform=_b(attrs[2], "UniformMaterial", True),
        layer3_uniform=_b(attrs[3], "UniformMaterial", True),
        layer1_generate=_b(attrs[1], "GenerateComputationalElements", True),
        layer2_generate=_b(attrs[2], "GenerateComputationalElements", True),
        layer3_generate=_b(attrs[3], "GenerateComputationalElements", True),
        is_stratigraphy_variable=_b(raw.attrib, "IsStratigraphyVariable"),
    )


def spec_from_wizard_data(wizard: etree._Element) -> CSharpBridgeSpec:
    """Build a mesh spec from a native ``WizardData`` element."""
    definition_element = wizard.find("BridgeDefinition")
    if definition_element is None:
        raise ValueError("WizardData has no BridgeDefinition")
    raw = dict(definition_element.attrib)
    corsias = [
        Corsia(
            width=_f(corsia.attrib, "Width"),
            height=_f(corsia.attrib, "Height"),
            material_key=_i(corsia.attrib, "MaterialKey"),
            name=corsia.attrib.get("Name", "lane"),
            attributes=dict(corsia.attrib),
        )
        for corsia in definition_element.findall("Corsie/Corsia")
    ]
    elements = []
    for element in wizard:
        if element.tag == "Abutment":
            elements.append(_abutment(element.attrib))
        elif element.tag == "Pier":
            elements.append(_pier(element.attrib))
        elif element.tag == "Span":
            elements.append(_span(element.attrib))
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=_f(raw, "Width"),
            width_top_pile=_f(raw, "WidthTopPile", _f(raw, "Width")),
            nl=_f(raw, "Nl", 100.0),
            nt=_f(raw, "Nt", 20000.0),
            inclination_angle=_f(raw, "InclinationAngle"),
            slope=_f(raw, "Slope"),
            zlevel=_f(raw, "Zlevel", 500.0),
            thickness_ballast=_f(raw, "ThicknessBallast"),
            thickness_riempimento=_f(raw, "ThicknessRiempimento"),
            corsias=corsias,
            trunks=[dict(trunk.attrib) for trunk in definition_element.findall("Trunks/Trunk")],
            attributes=raw,
        ),
        elements=elements,
        elevations=_elevations(wizard.find("Elevations")),
        wizard_type=(wizard.getparent().get("WizardType", "RailBridge")
                     if wizard.getparent() is not None else "RailBridge"),
    )


def spec_from_hrx(path) -> CSharpBridgeSpec:
    """Read wizard input and leaf material templates from a native HRX file."""
    context = etree.iterparse(str(path), events=("start", "end"), huge_tree=True)
    spec = None
    templates = []
    wizard = None
    template = None
    template_has_children = False
    for event, element in context:
        parent = element.getparent()
        if event == "start":
            if wizard is None and parent is not None and parent.tag == "HiStrA":
                if element.tag == "WizardData":
                    wizard = element
                elif element.tag == "Template":
                    template = element
                    template_has_children = False
            elif template is not None and parent is template:
                template_has_children = True
            continue
        if wizard is not None:
            if element is not wizard:
                continue
            spec = spec_from_wizard_data(element)
            wizard = None
        elif element is template:
            if ("Material" in element.get("TypeOf", "") and not template_has_children
                  and element.get("Key") is not None):
                templates.append(dict(element.attrib))
            template = None
        if parent is None:
            continue
        element.clear()
        while element.getprevious() is not None:
            del parent[0]
    if spec is None:
        raise ValueError(f"{path} has no WizardData")
    spec.material_templates = templates
    return spec
