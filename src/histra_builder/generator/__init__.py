"""Parametric bridge generation and meshing package for HiStrA."""
from __future__ import annotations

from .bridge_builder import (
    build_bridge_mesh,
    generate_bridge_hrx,
    generate_bridge_hrx_file,
    build_isolated_pier_mesh,
    generate_pier_hrx,
    generate_pier_hrx_file,
)
from .geometry import (
    Point3D,
    QuadKinematics,
    compute_quad_kinematics,
    ellipse_arch_point,
    signed_area_xz,
)
from .hrx_writer import serialize_mesh_to_hrx
from .materials import (
    DEFAULT_TEMPLATES,
    MASONRY_18,
    BACKFILL_19,
    PIER_CAP_22,
    FOUNDATION_141,
    SOIL_146,
    SOIL_REMOVED_147,
)
from .mesher import (
    BridgeMesher,
    GeneratedBridgeMesh,
    GeneratedQuad,
    MonitoringPoint,
    PierMetadata,
)
from .parameters import (
    AbutmentSpec,
    BridgeSpec,
    PierSpec,
    SpanSpec,
)
from .restraints import (
    GeneratedNodeC,
    GeneratedRestraint,
    create_foundation_edge_restraint,
)
from .csharp_model import (
    Abutment as CSharpAbutment,
    BridgeDefinition as CSharpBridgeDefinition,
    BridgeElement as CSharpBridgeElement,
    CSharpBridgeSpec,
    Corsia as CSharpCorsia,
    Elevation as CSharpElevation,
    Elevations as CSharpElevations,
    Pier as CSharpPier,
    Span as CSharpSpan,
)
from .csharp_mesher import CSharpBridgeMesh, CSharpMesher, build_csharp_bridge_mesh
from .csharp_writer import generate_csharp_bridge_hrx, serialize_csharp_mesh_to_hrx

__all__ = [
    "BridgeSpec",
    "SpanSpec",
    "PierSpec",
    "AbutmentSpec",
    "build_bridge_mesh",
    "generate_bridge_hrx",
    "generate_bridge_hrx_file",
    "build_isolated_pier_mesh",
    "generate_pier_hrx",
    "generate_pier_hrx_file",
    "BridgeMesher",
    "GeneratedBridgeMesh",
    "GeneratedQuad",
    "MonitoringPoint",
    "PierMetadata",
    "GeneratedRestraint",
    "GeneratedNodeC",
    "Point3D",
    "QuadKinematics",
    "compute_quad_kinematics",
    "ellipse_arch_point",
    "signed_area_xz",
    "serialize_mesh_to_hrx",
    "DEFAULT_TEMPLATES",
    "MASONRY_18",
    "BACKFILL_19",
    "PIER_CAP_22",
    "FOUNDATION_141",
    "SOIL_146",
    "SOIL_REMOVED_147",
    "create_foundation_edge_restraint",
    "CSharpAbutment",
    "CSharpBridgeDefinition",
    "CSharpBridgeElement",
    "CSharpBridgeSpec",
    "CSharpCorsia",
    "CSharpElevation",
    "CSharpElevations",
    "CSharpPier",
    "CSharpSpan",
    "CSharpBridgeMesh",
    "CSharpMesher",
    "build_csharp_bridge_mesh",
    "generate_csharp_bridge_hrx",
    "serialize_csharp_mesh_to_hrx",
]
