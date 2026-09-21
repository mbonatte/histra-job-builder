"""Top-level entry points for parametric bridge generation."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .hrx_writer import serialize_mesh_to_hrx
from .mesher import BridgeMesher, GeneratedBridgeMesh
from .parameters import BridgeSpec


def build_bridge_mesh(spec: BridgeSpec) -> GeneratedBridgeMesh:
    """Discretize a parametric BridgeSpec into finite element nodes, quads, and restraints."""
    mesher = BridgeMesher(spec)
    return mesher.mesh()


def generate_bridge_hrx(spec: BridgeSpec, include_scour_analyses: bool = True) -> bytes:
    """Generate byte-exact HRX XML bytes from a parametric BridgeSpec."""
    mesh = build_bridge_mesh(spec)
    return serialize_mesh_to_hrx(mesh, include_scour_analyses=include_scour_analyses)


def generate_bridge_hrx_file(
    spec: BridgeSpec,
    output_path: Union[str, Path],
    include_scour_analyses: bool = True,
) -> Path:
    """Generate an HRX model file from a parametric BridgeSpec."""
    hrx_bytes = generate_bridge_hrx(spec, include_scour_analyses=include_scour_analyses)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hrx_bytes)
    return path
