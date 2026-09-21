"""Top-level entry points for parametric bridge generation."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .hrx_writer import serialize_mesh_to_hrx
from .mesher import BridgeMesher, GeneratedBridgeMesh, build_isolated_pier_mesh
from .parameters import BridgeSpec, PierSpec


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


def generate_pier_hrx(
    pier: PierSpec,
    width: float = 200.0,
    target_mesh_size: float = 30.0,
    num_transverse_strips: int = 1,
    include_cap: bool = True,
    include_scour_analyses: bool = True,
) -> bytes:
    """Generate byte-exact HRX XML bytes for an isolated pier matching the bridge pier."""
    mesh = build_isolated_pier_mesh(
        pier=pier,
        width=width,
        target_mesh_size=target_mesh_size,
        num_transverse_strips=num_transverse_strips,
        include_cap=include_cap,
    )
    return serialize_mesh_to_hrx(mesh, include_scour_analyses=include_scour_analyses)


def generate_pier_hrx_file(
    pier: PierSpec,
    output_path: Union[str, Path],
    width: float = 200.0,
    target_mesh_size: float = 30.0,
    num_transverse_strips: int = 1,
    include_cap: bool = True,
    include_scour_analyses: bool = True,
) -> Path:
    """Generate an HRX model file for an isolated pier."""
    hrx_bytes = generate_pier_hrx(
        pier=pier,
        width=width,
        target_mesh_size=target_mesh_size,
        num_transverse_strips=num_transverse_strips,
        include_cap=include_cap,
        include_scour_analyses=include_scour_analyses,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hrx_bytes)
    return path
