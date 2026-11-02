"""C#-equivalent bridge wizard data model.

The classes in this module mirror the fields consumed by the C#
``BridgeMesher``.  They are intentionally explicit instead of being another
generic ``BridgeSpec``: a C# node, span or pier carries many dimensions that
the simplified generator previously dropped.

Only the fields required by the first straight/wizard mesh path are active
today; the remaining C# fields are present so later meshing tasks can use them
without changing the public model again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple


@dataclass
class Corsia:
    """C# ``Corsia``: one transverse lane/strip."""

    width: float
    height: float = 0.0
    material_key: int = 0
    name: str = "lane"
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class BridgeElement:
    """Fields shared by C# ``Pier`` and ``Abutment``."""

    b1: float = 0.0
    b2: float = 0.0
    b3: float = 0.0
    w1: float = 0.0
    w2: float = 0.0
    w3: float = 0.0
    H: float = 0.0
    Hf: float = 0.0
    B1f: float = 0.0
    B3f: float = 0.0
    W1f: float = 0.0
    W3f: float = 0.0
    material_key: int = 18
    material_foundation_key: int = 18
    vertical_alignment: str = "Center"
    beta1: float = 0.0
    beta2: float = 0.0
    is_fix_dir_x: bool = True
    is_fix_dir_y: bool = True
    is_fix_dir_z: bool = True
    is_fix_rot_dir_x: bool = True
    is_fix_rot_dir_y: bool = True
    is_fix_rot_dir_z: bool = True
    Kx: float = 0.0
    Ky: float = 0.0
    Kz: float = 0.1
    Krx: float = 0.0
    Kry: float = 0.0
    Krz: float = 0.0
    is_reinf_left: bool = False
    is_reinf_right: bool = False
    TreinfTopLeft: float = 0.0
    TreinfBotLeft: float = 0.0
    TreinfTopRight: float = 0.0
    TreinfBotRight: float = 0.0
    material_reinforcement_left_key: int = 24
    material_reinforcement_right_key: int = 24

    # Compatibility aliases used by the existing HRX writer.
    @property
    def height(self) -> float:
        return self.H

    @property
    def foundation_height(self) -> float:
        return self.Hf

    @property
    def thickness(self) -> float:
        return self.b2

    @property
    def foundation_material_key(self) -> int:
        return self.material_foundation_key


@dataclass
class Abutment(BridgeElement):
    """C# ``Abutment``."""

    kind: str = "Sinistra"
    spinta_passiva_sx: bool = False
    spinta_passiva_dx: bool = False
    Hsp1: float = 0.0
    Hsp2: float = 0.0
    material_geo1_key: int = 60
    material_geo2_key: int = 60


@dataclass
class Pier(BridgeElement):
    """C# ``Pier``."""

    spinta_passiva_sx: bool = False
    spinta_passiva_dx: bool = False
    Hsp1: float = 0.0
    Hsp2: float = 0.0
    material_geo1_key: int = 60
    material_geo2_key: int = 60
    Tr1: float = 0.0
    Tr2: float = 0.0

    @property
    def subgrade_modulus_kz(self) -> float:
        return self.Kz


@dataclass
class Span:
    """C# ``Span`` fields consumed by the arch mesher."""

    L: float
    W: float
    f: float
    S1: float = 0.0
    S2: float = 0.0
    Asx: float = 0.0
    Adx: float = 0.0
    Tb: float = 100.0
    Tb1: float = 0.0
    Tb2: float = 100.0
    Tt: float = 100.0
    Treinf: float = 0.0
    Dz: float = 0.0
    L1: float = 0.0
    f1: float = 0.0
    f2: float = 0.0
    thickness_riempimento: float = 0.0
    material_key: int = 18
    material_pulvino_key: int = 22
    material_reinforcement_key: int = 24
    discr_left: int = 1
    discr_right: int = 1
    circolare: bool = False

    # Compatibility aliases used by the existing HRX writer.
    @property
    def length(self) -> float:
        return self.L

    @property
    def rise(self) -> float:
        return self.f

    @property
    def thickness_springer(self) -> float:
        return self.Tb

    @property
    def thickness_crown(self) -> float:
        return self.Tt


@dataclass
class Elevation:
    """C# ``Elevation`` section."""

    X: float = 0.0
    H1: float = 200.0
    H2: float = 210.0
    H3: float = 80.0

    @property
    def Z1(self) -> float:
        return self.H1

    @property
    def Z2(self) -> float:
        return self.H1 + self.H2

    @property
    def Z3(self) -> float:
        return self.H1 + self.H2 + self.H3

    def get_z(self, layer: int, hmuro: float = 0.0) -> float:
        if layer == 0:
            return 0.0
        if layer == 1:
            return self.Z1
        if layer == 2:
            return self.Z2
        if layer == 3:
            return self.Z3
        if layer == 4:
            return self.Z3 + hmuro
        return 0.0


@dataclass
class Elevations:
    """C# ``Elevations``: ground/backfill layer sections."""

    elevations: List[Elevation] = field(default_factory=lambda: [Elevation()])
    layer1_material_key: int = 19
    layer2_material_key: int = 20
    layer3_material_key: int = 21
    layer1_material_key2: int = 19
    layer2_material_key2: int = 20
    layer3_material_key2: int = 21
    layer1_row_index: int = 1
    layer2_row_index: int = 1
    layer3_row_index: int = 1
    layer1_generate: bool = True
    layer2_generate: bool = True
    layer3_generate: bool = True
    layer1_uniform: bool = True
    layer2_uniform: bool = True
    layer3_uniform: bool = True
    is_stratigraphy_variable: bool = False

    def get_z(self, x: float, layer: int, hmuro: float = 0.0, add_slope: bool = False) -> float:
        """Port of ``Elevations.GetZ`` with linear interpolation by X."""
        if not self.elevations:
            raise ValueError("Elevations requires at least one section")
        points = sorted(
            ((section.X, section.get_z(layer, hmuro)) for section in self.elevations),
            key=lambda item: item[0],
        )
        if len(points) == 1 or x <= points[0][0]:
            return points[0][1]
        if x >= points[-1][0]:
            return points[-1][1]
        for (x0, z0), (x1, z1) in zip(points, points[1:]):
            if x0 <= x <= x1:
                if x1 == x0:
                    return z0
                return (z1 - z0) / (x1 - x0) * (x - x0) + z0
        return points[-1][1]

    def get_material_key(self, layer: int) -> Tuple[int, int, int]:
        """Return ``(material_key1, material_key2, row_index)`` for a layer."""
        if layer not in (1, 2, 3, 4):
            return (-1, -1, -1)
        index = min(layer, 3)
        first = getattr(self, f"layer{index}_material_key")
        second = getattr(self, f"layer{index}_material_key2")
        uniform = getattr(self, f"layer{index}_uniform")
        if layer == 4:
            value = first if uniform else second
            return (value, value, -1)
        if uniform:
            return (first, first, -1)
        return (first, second, getattr(self, f"layer{index}_row_index"))

    def generates_layer(self, layer: int) -> bool:
        if layer == 1:
            return self.layer1_generate
        if layer == 2:
            return self.layer2_generate
        if layer == 3:
            return self.layer3_generate
        return True


@dataclass
class BridgeDefinition:
    """C# ``BridgeDefinition`` subset consumed by the mesher."""

    width: float = 600.0
    width_top_pile: float = 600.0
    nl: float = 100.0
    nt: float = 20000.0
    inclination_angle: float = 0.0
    slope: float = 0.0
    zlevel: float = 500.0
    thickness_ballast: float = 0.0
    thickness_riempimento: float = 0.0
    corsias: List[Corsia] = field(default_factory=list)
    trunks: List[dict[str, str]] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class CSharpBridgeSpec:
    """Complete input for the C#-parity straight wizard mesher."""

    definition: BridgeDefinition
    elements: Sequence[object]
    elevations: Elevations = field(default_factory=Elevations)
    material_templates: List[dict[str, str]] = field(default_factory=list)
    wizard_type: str = "RailBridge"

    def __post_init__(self) -> None:
        self.elements = tuple(self.elements)
        if not self.elements:
            raise ValueError("bridge requires at least one element")
        spans = [element for element in self.elements if isinstance(element, Span)]
        if not spans:
            raise ValueError("bridge requires at least one Span")
        if not self.definition.corsias:
            raise ValueError("bridge requires at least one Corsia strip")

    @property
    def width(self) -> float:
        return self.definition.width

    @property
    def target_mesh_size(self) -> float:
        return self.definition.nl

    @property
    def spans(self) -> List[Span]:
        return [element for element in self.elements if isinstance(element, Span)]

    @property
    def abutments(self) -> List[Abutment]:
        return [element for element in self.elements if isinstance(element, Abutment)]

    @property
    def piers(self) -> List[Pier]:
        return [element for element in self.elements if isinstance(element, Pier)]

    @property
    def left_abutment(self) -> Abutment:
        abutments = self.abutments
        if not abutments:
            raise ValueError("bridge has no left abutment")
        return abutments[0]

    @property
    def right_abutment(self) -> Abutment:
        abutments = self.abutments
        if not abutments:
            raise ValueError("bridge has no right abutment")
        return abutments[-1]

    @property
    def num_transverse_strips(self) -> int:
        return len(self.definition.corsias)

    @property
    def deck_clearance(self) -> float:
        return 0.0
