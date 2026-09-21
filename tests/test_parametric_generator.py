"""Comprehensive unit test suite for the parametric bridge generator."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from lxml import etree

from histra_builder.generator import (
    AbutmentSpec,
    BridgeMesher,
    BridgeSpec,
    GeneratedBridgeMesh,
    PierSpec,
    Point3D,
    SpanSpec,
    build_bridge_mesh,
    compute_quad_kinematics,
    ellipse_arch_point,
    generate_bridge_hrx,
    generate_bridge_hrx_file,
    signed_area_xz,
)
from histra_builder.inspector import inspect_hrx
from histra_builder.scenarios import find_piers

from histra.io.hr_loader import load_model
from histra.preprocessing.prepare_model import prepare_model
from histra.solver.session import AnalysisSession


def test_point3d_operations() -> None:
    p1 = Point3D(10.0, 20.0, 30.0)
    p2 = Point3D(10.0, 20.0, 34.0)
    assert p1.distance_to(p2) == pytest.approx(4.0)
    assert p1.to_xml_str() == "10;20;30"
    p_add = p1 + Point3D(1.0, 2.0, 3.0)
    assert (p_add.x, p_add.y, p_add.z) == (11.0, 22.0, 33.0)
    p_sub = p1 - Point3D(1.0, 2.0, 3.0)
    assert (p_sub.x, p_sub.y, p_sub.z) == (9.0, 18.0, 27.0)
    p_mul = p1 * 2.0
    assert (p_mul.x, p_mul.y, p_mul.z) == (20.0, 40.0, 60.0)


def test_bridge_spec_validation_and_pier_population() -> None:
    # 1 span requires 0 piers
    spec1 = BridgeSpec(spans=[SpanSpec(length=400.0)])
    assert len(spec1.piers) == 0

    # 2 spans automatically populates 1 pier
    spec2 = BridgeSpec(spans=[SpanSpec(length=400.0), SpanSpec(length=400.0)])
    assert len(spec2.piers) == 1
    assert spec2.piers[0].height == 150.0

    # 3 spans automatically populates 2 piers
    spec3 = BridgeSpec(
        spans=[
            SpanSpec(length=350.0),
            SpanSpec(length=400.0),
            SpanSpec(length=350.0),
        ]
    )
    assert len(spec3.piers) == 2


def test_compute_quad_kinematics_accuracy() -> None:
    # Unit 10x10 square in X-Z
    nodes = [
        Point3D(0.0, 0.0, 0.0),
        Point3D(10.0, 0.0, 0.0),
        Point3D(10.0, 0.0, 10.0),
        Point3D(0.0, 0.0, 10.0),
    ]
    kin = compute_quad_kinematics(nodes, thickness=50.0)
    assert kin.signed_area == pytest.approx(100.0)
    assert kin.lengths == [10.0, 10.0, 10.0, 10.0]
    assert kin.diagonals[0] == pytest.approx(14.1421356, rel=1e-4)
    assert kin.diagonals[1] == pytest.approx(14.1421356, rel=1e-4)
    for c in kin.cosines:
        assert c == pytest.approx(0.0, abs=1e-6)
    for s in kin.sines:
        assert s == pytest.approx(1.0, abs=1e-6)
    assert kin.centroid == Point3D(5.0, 0.0, 5.0)
    assert kin.ref_e1 == (1.0, 0.0, 0.0)
    assert kin.ref_e3 == (0.0, -1.0, 0.0)
    assert kin.ref_e2 == (0.0, 0.0, 1.0)


def test_single_span_bridge_generation() -> None:
    spec = BridgeSpec(
        name="SingleSpanTest",
        width=200.0,
        target_mesh_size=35.0,
        num_transverse_strips=1,
        deck_clearance=25.0,
        spans=[SpanSpec(length=380.0, rise=90.0, thickness_springer=30.0, thickness_crown=25.0)],
        left_abutment=AbutmentSpec(height=120.0, thickness=60.0),
        right_abutment=AbutmentSpec(height=120.0, thickness=60.0),
    )
    hrx_bytes = generate_bridge_hrx(spec)
    inspection = inspect_hrx(hrx_bytes)
    assert inspection.validation["valid"] is True
    assert inspection.counts["nodes"] > 50
    assert inspection.counts["quads"] > 30

    with tempfile.NamedTemporaryFile(suffix=".hrx", mode="wb", delete=False) as tmp:
        tmp.write(hrx_bytes)
        tmp_path = tmp.name

    model = load_model(tmp_path)
    assert len(model.collections.nodes) == inspection.counts["nodes"]
    assert len(model.collections.quads) == inspection.counts["quads"]
    assert len(model.collections.restraints) > 0

    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.gdl > 0
    assert len(model.collections.interfaces) > 0

    for r in model.collections.restraints.values():
        assert r.computational_element_type == "Quad"
        assert all(abs(val - (-1.0)) < 1e-9 for val in r.k)


def test_two_span_bridge_generation_and_pier_metadata() -> None:
    spec = BridgeSpec(
        name="TwoSpanBridge",
        width=250.0,
        target_mesh_size=35.0,
        num_transverse_strips=1,
        deck_clearance=30.0,
        spans=[
            SpanSpec(length=400.0, rise=100.0),
            SpanSpec(length=420.0, rise=110.0),
        ],
        piers=[PierSpec(height=160.0, thickness=60.0, foundation_height=60.0)],
    )
    mesh = build_bridge_mesh(spec)
    assert len(mesh.piers) == 1
    assert mesh.piers[0].id == "pier_1"
    assert len(mesh.piers[0].restraint_keys) > 0

    hrx_bytes = generate_bridge_hrx(spec)
    inspection = inspect_hrx(hrx_bytes)
    assert inspection.validation["valid"] is True

    piers = find_piers(hrx_bytes)
    assert len(piers) == 1
    assert piers[0]["id"] == "pier_1"

    with tempfile.NamedTemporaryFile(suffix=".hrx", mode="wb", delete=False) as tmp:
        tmp.write(hrx_bytes)
        tmp_path = tmp.name

    model = load_model(tmp_path)
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.gdl > 0


def test_three_span_bridge_generation() -> None:
    spec = BridgeSpec(
        name="ThreeSpanBridge",
        width=200.0,
        target_mesh_size=40.0,
        num_transverse_strips=1,
        deck_clearance=30.0,
        spans=[
            SpanSpec(length=350.0, rise=90.0),
            SpanSpec(length=400.0, rise=100.0),
            SpanSpec(length=350.0, rise=90.0),
        ],
        piers=[
            PierSpec(height=140.0, thickness=50.0),
            PierSpec(height=140.0, thickness=50.0),
        ],
    )
    hrx_bytes = generate_bridge_hrx(spec)
    inspection = inspect_hrx(hrx_bytes)
    assert inspection.validation["valid"] is True

    piers = find_piers(hrx_bytes)
    assert len(piers) == 2
    assert [p["id"] for p in piers] == ["pier_1", "pier_2"]

    with tempfile.NamedTemporaryFile(suffix=".hrx", mode="wb", delete=False) as tmp:
        tmp.write(hrx_bytes)
        tmp_path = tmp.name

    model = load_model(tmp_path)
    report = prepare_model(model, force=True)
    assert report.prepared is True
    assert report.gdl > 0


def test_varying_mesh_densities() -> None:
    spec_coarse = BridgeSpec(
        target_mesh_size=55.0,
        spans=[SpanSpec(length=400.0, rise=100.0)],
    )
    mesh_coarse = build_bridge_mesh(spec_coarse)

    spec_fine = BridgeSpec(
        target_mesh_size=25.0,
        spans=[SpanSpec(length=400.0, rise=100.0)],
    )
    mesh_fine = build_bridge_mesh(spec_fine)

    assert len(mesh_fine.quads) > len(mesh_coarse.quads)
    assert len(mesh_fine.nodes) > len(mesh_coarse.nodes)


def test_multi_strip_transverse_slicing() -> None:
    spec = BridgeSpec(
        width=300.0,
        target_mesh_size=35.0,
        num_transverse_strips=2,
        spans=[SpanSpec(length=380.0, rise=90.0)],
    )
    mesh = build_bridge_mesh(spec)
    hrx_bytes = generate_bridge_hrx(spec)
    inspection = inspect_hrx(hrx_bytes)
    assert inspection.validation["valid"] is True

    # Nodes span two transverse Y coordinate planes
    y_coords = {mesh.nodes[k].y for k in mesh.nodes}
    assert len(y_coords) == 2

    with tempfile.NamedTemporaryFile(suffix=".hrx", mode="wb", delete=False) as tmp:
        tmp.write(hrx_bytes)
        tmp_path = tmp.name

    model = load_model(tmp_path)
    report = prepare_model(model, force=True)
    assert report.prepared is True


def test_materials_and_templates_present() -> None:
    spec = BridgeSpec(spans=[SpanSpec(length=400.0, rise=100.0)])
    hrx_bytes = generate_bridge_hrx(spec)
    root = etree.fromstring(hrx_bytes)

    template_keys = {elem.get("Key") for elem in root.xpath("/HiStrA/Template")}
    assert "18" in template_keys  # Masonry
    assert "22" in template_keys  # Pier cap
    assert "141" in template_keys  # Foundation
    assert "146" in template_keys  # Soil
    assert "147" in template_keys  # Soil_removed


def test_analysis_and_equilibrium_invariants() -> None:
    spec = BridgeSpec(spans=[SpanSpec(length=400.0, rise=100.0)])
    hrx_bytes = generate_bridge_hrx(spec)
    root = etree.fromstring(hrx_bytes)

    # Verify Gravity LoadCondition has Action="1"
    gravity = root.xpath("/HiStrA/LoadCondition[@Id='1']")[0]
    assert gravity.get("Action") == "1"

    # Verify LoadCombination Key 6 exists
    comb = root.xpath("/HiStrA/LoadCombination[@Key='6']")[0]
    assert comb.get("Name") == "SEISMIC"

    # Verify Vert analysis enforces ForceMoment equilibrium criteria
    vert = root.xpath("/HiStrA/Analysis[@Name='Vert']")[0]
    assert vert.get("AdapticConvergenceCriteria") == "ForceMoment"
    assert float(vert.get("ConvergenceTolerance", "1.0")) <= 0.0001
    assert float(vert.get("ConvergenceToleranceForce", "1.0")) <= 0.0001
    assert float(vert.get("ConvergenceToleranceMoment", "1.0")) <= 0.0001


def test_generate_bridge_hrx_file(tmp_path: Path) -> None:
    spec = BridgeSpec(spans=[SpanSpec(length=400.0, rise=100.0)])
    out_file = tmp_path / "subdir" / "test_bridge.hrx"
    result_path = generate_bridge_hrx_file(spec, out_file)
    assert result_path.is_file()
    assert result_path.stat().st_size > 1000


def test_vert_equilibrium_solve() -> None:
    spec = BridgeSpec(
        name="SolverTestBridge",
        width=200.0,
        target_mesh_size=40.0,
        num_transverse_strips=1,
        deck_clearance=30.0,
        spans=[SpanSpec(length=380.0, rise=90.0)],
    )
    hrx_bytes = generate_bridge_hrx(spec)
    with tempfile.NamedTemporaryFile(suffix=".hrx", mode="wb", delete=False) as tmp:
        tmp.write(hrx_bytes)
        tmp_path = tmp.name

    model = load_model(tmp_path)
    prepare_model(model, force=True)
    sess = AnalysisSession(model)
    res = sess.run("Vert")
    assert res.outcome.value == "completed"
    assert len(res.steps) == 20


def test_conformal_topology_and_isolated_pier_solve() -> None:
    from histra_builder.generator import generate_pier_hrx

    # 1. Verify two-span bridge mesh has 0 T-junctions and authentic Pulvino
    spec = BridgeSpec(
        name="ConformalTwoSpanAudit",
        width=200.0,
        target_mesh_size=35.0,
        spans=[
            SpanSpec(length=400.0, rise=100.0, thickness_springer=35.0, thickness_crown=25.0),
            SpanSpec(length=400.0, rise=100.0, thickness_springer=35.0, thickness_crown=25.0),
        ],
        piers=[PierSpec(height=200.0, thickness=60.0, foundation_height=60.0, foundation_length=100.0)],
        left_abutment=AbutmentSpec(height=0.0, thickness=70.0, foundation_height=0.0),
        right_abutment=AbutmentSpec(height=0.0, thickness=70.0, foundation_height=0.0),
    )
    mesh = build_bridge_mesh(spec)

    # Check for Pier_Cap quads (Mat 22)
    cap_quads = [q for q in mesh.quads.values() if q.material_key == 22]
    assert len(cap_quads) >= 2  # Left and right Pulvino quads

    # Strict point-on-segment geometric audit for T-junctions
    all_nodes = {k: (pt.x, pt.y, pt.z) for k, pt in mesh.nodes.items()}
    edges = set()
    for q in mesh.quads.values():
        n = q.node_keys
        for i in range(4):
            e = tuple(sorted([n[i], n[(i + 1) % 4]]))
            edges.add(e)

    def is_point_on_segment(px, pz, ax, az, bx, bz, tol=1e-3):
        cross = abs((px - ax) * (bz - az) - (pz - az) * (bx - ax))
        if cross > tol:
            return False
        dot = (px - ax) * (bx - ax) + (pz - az) * (bz - az)
        if dot < tol:
            return False
        sq_len = (bx - ax) ** 2 + (bz - az) ** 2
        if dot > sq_len - tol:
            return False
        return True

    t_junctions = 0
    for e in edges:
        pA = all_nodes[e[0]]
        pB = all_nodes[e[1]]
        for n_k, pN in all_nodes.items():
            if n_k == e[0] or n_k == e[1]:
                continue
            if abs(pN[1] - pA[1]) > 1e-3:
                continue
            if is_point_on_segment(pN[0], pN[2], pA[0], pA[2], pB[0], pB[2]):
                t_junctions += 1

    assert t_junctions == 0, f"Found {t_junctions} T-junctions in bridge mesh!"

    # 2. Verify isolated pier model generation and full 20-step equilibrium solve
    pier_spec = PierSpec(
        height=200.0,
        thickness=60.0,
        cap_height=35.0,
        foundation_height=60.0,
        foundation_length=100.0,
        foundation_width=200.0,
        material_key=18,
        cap_material_key=22,
        foundation_material_key=141,
    )
    pier_hrx = generate_pier_hrx(pier_spec, width=200.0, target_mesh_size=35.0, include_cap=True)
    with tempfile.NamedTemporaryFile(suffix=".hrx", mode="wb", delete=False) as tmp:
        tmp.write(pier_hrx)
        tmp_path = tmp.name

    p_model = load_model(tmp_path)
    prepare_model(p_model, force=True)
    p_sess = AnalysisSession(p_model)
    p_res = p_sess.run("Vert")
    assert p_res.outcome.value == "completed"
    assert len(p_res.steps) == 20

