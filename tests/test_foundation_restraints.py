from __future__ import annotations

from app.hrx import build_restraint_topology, support_bearing_quad_keys
from app.mesh import Mesh, MeshBuilder


def _add_rect(
    builder: MeshBuilder,
    *,
    x0: float,
    x1: float,
    z0: float,
    z1: float,
    group: str,
    band: int,
    thickness: float,
    y: float = 0.0,
) -> None:
    builder.add_quad(
        [
            [x0, y, z0],
            [x1, y, z0],
            [x1, y, z1],
            [x0, y, z1],
        ],
        material_key="1",
        layer_key=1,
        thickness=thickness,
        group=group,
        transverse_band_index=band,
        transverse_band_name=str(band),
        transverse_role="test",
    )


def _mesh(builder: MeshBuilder) -> Mesh:
    return Mesh(nodes=builder.nodes, quads=builder.quads, metadata={})


def test_pier_with_foundation_is_restrained_only_at_foundation_bottom() -> None:
    builder = MeshBuilder()

    # Deliberately use different transverse metadata. This reproduces the old
    # failure where shaft and foundation were grouped separately and both fixed.
    _add_rect(
        builder,
        x0=0.0,
        x1=2.0,
        z0=0.0,
        z1=2.0,
        group="pier-1-shaft",
        band=0,
        thickness=1.0,
    )
    for x0, x1 in zip((-1.0, 0.0, 1.0, 2.0), (0.0, 1.0, 2.0, 3.0)):
        _add_rect(
            builder,
            x0=x0,
            x1=x1,
            z0=-1.0,
            z1=0.0,
            group="pier-1-foundation",
            band=1,
            thickness=2.0,
        )

    mesh = _mesh(builder)
    topology = build_restraint_topology(mesh)
    restraints = [item for line in topology.line_groups for item in line.restraints]

    assert restraints
    assert all(item.quad.group == "pier-1-foundation" for item in restraints)
    assert all(item.point1[2] == -1.0 and item.point2[2] == -1.0 for item in restraints)
    groups = {quad.group for quad in mesh.quads if quad.key in support_bearing_quad_keys(mesh)}
    assert groups == {"pier-1-foundation"}


def test_pier_without_foundation_uses_shaft_bottom_as_fallback() -> None:
    builder = MeshBuilder()
    _add_rect(builder, x0=0.0, x1=1.0, z0=0.0, z1=2.0, group="pier-1-shaft", band=0, thickness=1.0)
    _add_rect(builder, x0=1.0, x1=2.0, z0=0.0, z1=2.0, group="pier-1-shaft", band=0, thickness=1.0)

    topology = build_restraint_topology(_mesh(builder))
    restraints = [item for line in topology.line_groups for item in line.restraints]

    assert restraints
    assert all(item.quad.group == "pier-1-shaft" for item in restraints)


def test_abutment_fill_never_receives_ground_restraints() -> None:
    builder = MeshBuilder()
    _add_rect(builder, x0=0.0, x1=2.0, z0=-1.0, z1=1.0, group="left-abutment-body", band=0, thickness=1.0)
    _add_rect(builder, x0=0.0, x1=2.0, z0=-2.0, z1=-1.0, group="left-abutment-fill", band=1, thickness=2.0)

    topology = build_restraint_topology(_mesh(builder))
    restraints = [item for line in topology.line_groups for item in line.restraints]

    assert restraints
    assert all(item.quad.group == "left-abutment-body" for item in restraints)