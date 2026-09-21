"""Procedural 2D/3D finite element mesher for parametric masonry arch bridges."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .geometry import (
    Point3D,
    QuadKinematics,
    compute_quad_kinematics,
    ellipse_arch_point,
    signed_area_xz,
)
from .parameters import BridgeSpec, SpanSpec, PierSpec, AbutmentSpec
from .restraints import (
    GeneratedNodeC,
    GeneratedRestraint,
    create_foundation_edge_restraint,
)


@dataclass
class GeneratedQuad:
    key: int
    node_keys: Tuple[int, int, int, int]
    material_key: int
    thickness: float
    kinematics: QuadKinematics
    group: str
    layer_key: int = 0
    parent_key: int = 1
    parent_type_element: str = "Bridge"


@dataclass
class MonitoringPoint:
    key: int
    element_key: int
    element_type: str = "Node"
    id_vertex: int = 0
    description: str = ""
    point: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 0.0))


@dataclass
class PierMetadata:
    id: str
    index: int
    origin: Point3D
    x_start: float
    x_end: float
    restraint_keys: List[int] = field(default_factory=list)


@dataclass
class GeneratedBridgeMesh:
    spec: BridgeSpec
    nodes: Dict[int, Point3D]
    quads: Dict[int, GeneratedQuad]
    restraints: List[GeneratedRestraint]
    node_cs: List[GeneratedNodeC]
    piers: List[PierMetadata]
    monitoring_points: List[MonitoringPoint]
    deck_z: float
    total_length: float


class BridgeMesher:
    """Procedural mesher that discretizes a BridgeSpec into finite elements."""

    def __init__(self, spec: BridgeSpec) -> None:
        self.spec = spec
        self.nodes: Dict[int, Point3D] = {}
        self.node_lookup: Dict[Tuple[float, float, float], int] = {}
        self.next_node_key: int = 1

        self.quads: Dict[int, GeneratedQuad] = {}
        self.next_quad_key: int = 1

        self.node_cs: List[GeneratedNodeC] = []
        self.node_c_map: Dict[int, int] = {}
        self.next_node_c_key: int = 1

        self.restraints: List[GeneratedRestraint] = []
        self.next_restraint_key: int = 1

        self.piers: List[PierMetadata] = []
        self.monitoring_points: List[MonitoringPoint] = []
        self.next_model_point_key: int = 1

    def _get_or_create_node(self, x: float, y: float, z: float) -> int:
        coord_key = (round(x, 4), round(y, 4), round(z, 4))
        if coord_key in self.node_lookup:
            return self.node_lookup[coord_key]
        key = self.next_node_key
        self.next_node_key += 1
        pt = Point3D(round(x, 4), round(y, 4), round(z, 4))
        self.nodes[key] = pt
        self.node_lookup[coord_key] = key
        return key

    def _add_quad(
        self,
        n0: int,
        n1: int,
        n2: int,
        n3: int,
        material_key: int,
        thickness: float,
        group: str,
        out_of_plane_normal: Tuple[float, float, float] = (0.0, 1.0, 0.0),
    ) -> GeneratedQuad:
        p0 = self.nodes[n0]
        p1 = self.nodes[n1]
        p2 = self.nodes[n2]
        p3 = self.nodes[n3]

        # Verify positive area in X-Z; if reversed, flip orientation
        area = signed_area_xz([p0, p1, p2, p3])
        if area < 0:
            n0, n1, n2, n3 = n0, n3, n2, n1
            p0, p1, p2, p3 = p0, p3, p2, p1

        kin = compute_quad_kinematics(
            [p0, p1, p2, p3],
            thickness=thickness,
            out_of_plane_normal=out_of_plane_normal,
        )

        key = self.next_quad_key
        self.next_quad_key += 1

        quad = GeneratedQuad(
            key=key,
            node_keys=(n0, n1, n2, n3),
            material_key=material_key,
            thickness=thickness,
            kinematics=kin,
            group=group,
        )
        self.quads[key] = quad
        return quad

    def mesh(self) -> GeneratedBridgeMesh:
        spec = self.spec
        mesh_sz = spec.target_mesh_size

        # 1. Standard springing angle and springing offsets
        # Standard HiStrA springing angle alpha (cos_a = 0.8, sin_a = 0.6)
        alpha = 36.8699 * math.pi / 180.0
        cos_a = math.cos(alpha)
        sin_a = math.sin(alpha)

        # Compute per-span springer offsets
        span_dx: List[float] = [round(s.thickness_springer * cos_a, 4) for s in spec.spans]
        span_dz: List[float] = [round(s.thickness_springer * sin_a, 4) for s in spec.spans]
        dz_springing = max(span_dz)

        # 2. Establish deck elevation
        z_crown_max = max(s.rise + s.thickness_crown for s in spec.spans)
        deck_z = z_crown_max + spec.deck_clearance

        # Vertical rows for superstructure backfill
        N_rows = max(2, int(round((deck_z - dz_springing) / mesh_sz)))
        z_rows = [dz_springing + k * (deck_z - dz_springing) / N_rows for k in range(N_rows + 1)]

        # 3. Longitudinal layout
        # Left Abutment
        x_al_start = 0.0
        x_al_end = spec.left_abutment.thickness
        x_cur = x_al_end

        span_int_bounds: List[Tuple[float, float]] = []
        pier_bounds: List[Tuple[float, float, float]] = []

        for i, span in enumerate(spec.spans):
            x_sp_start = x_cur
            x_sp_end = x_cur + span.length
            span_int_bounds.append((x_sp_start, x_sp_end))
            x_cur = x_sp_end

            if i < len(spec.piers):
                pier = spec.piers[i]
                x_p_start = x_cur
                x_p_end = x_cur + pier.thickness
                x_p_center = (x_p_start + x_p_end) / 2.0
                pier_bounds.append((x_p_start, x_p_end, x_p_center))
                x_cur = x_p_end

        # Right Abutment
        x_ar_start = x_cur
        x_ar_end = x_cur + spec.right_abutment.thickness
        x_total = x_ar_end

        # 4. Transverse strips
        nt = max(1, spec.num_transverse_strips)
        strip_thick = spec.width / nt
        y_strips = [
            -spec.width / 2.0 + (j + 0.5) * strip_thick for j in range(nt)
        ]

        pier_restraints_map: Dict[int, List[int]] = {i: [] for i in range(len(spec.piers))}

        # 5. Generate mesh per transverse strip
        for strip_idx, y in enumerate(y_strips):
            is_exterior = (nt > 1) and (strip_idx == 0 or strip_idx == nt - 1)
            fill_grp_suffix = "Spandrel" if is_exterior else "Backfill"

            # A. Left Abutment
            b_ab_l = spec.left_abutment.thickness
            dx_0 = span_dx[0]
            ab_m_l = max(1, int(round((b_ab_l - dx_0) / mesh_sz)))
            x_ab_cols_top = [c * (b_ab_l - dx_0) / ab_m_l for c in range(ab_m_l + 1)]
            x_ab_cols_bot = [c * b_ab_l / ab_m_l for c in range(ab_m_l + 1)]

            h_fnd_al = spec.left_abutment.foundation_height
            h_shaft_al = spec.left_abutment.height
            z_al_bot = -h_shaft_al - h_fnd_al

            if z_al_bot < -1e-4:
                n_fnd_al = max(1, int(round(h_fnd_al / mesh_sz))) if h_fnd_al > 0 else 0
                n_shaft_al = max(1, int(round(h_shaft_al / mesh_sz))) if h_shaft_al > 0 else 0
                z_al_sub: List[float] = []
                for r in range(n_fnd_al):
                    z_al_sub.append(z_al_bot + (r / max(1, n_fnd_al)) * h_fnd_al)
                z_shaft_bot = -h_shaft_al
                for r in range(n_shaft_al):
                    z_al_sub.append(z_shaft_bot + (r / max(1, n_shaft_al)) * h_shaft_al)
                z_al_sub.append(0.0)

                for c in range(ab_m_l):
                    for r in range(len(z_al_sub) - 1):
                        n0 = self._get_or_create_node(x_ab_cols_bot[c], y, z_al_sub[r])
                        n1 = self._get_or_create_node(x_ab_cols_bot[c + 1], y, z_al_sub[r])
                        n2 = self._get_or_create_node(x_ab_cols_bot[c + 1], y, z_al_sub[r + 1])
                        n3 = self._get_or_create_node(x_ab_cols_bot[c], y, z_al_sub[r + 1])
                        mat = spec.left_abutment.foundation_material_key if r < n_fnd_al else spec.left_abutment.material_key
                        grp = "Abutment_Left_Foundation" if r < n_fnd_al else "Abutment_Left_Shaft"
                        q = self._add_quad(n0, n1, n2, n3, mat, strip_thick, grp)
                        if r == 0:
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=self.nodes[n0],
                                p1=self.nodes[n1],
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag="abutment_left",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)

            # Left Abutment Cap: Z in [0, dz_springing]
            for c in range(ab_m_l):
                n0 = self._get_or_create_node(x_ab_cols_bot[c], y, 0.0)
                n1 = self._get_or_create_node(x_ab_cols_bot[c + 1], y, 0.0)
                n2 = self._get_or_create_node(x_ab_cols_top[c + 1], y, dz_springing)
                n3 = self._get_or_create_node(x_ab_cols_top[c], y, dz_springing)
                q = self._add_quad(n0, n1, n2, n3, spec.left_abutment.cap_material_key, strip_thick, "Abutment_Left_Cap")
                if z_al_bot >= -1e-4:
                    res, self.next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=self.next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=self.nodes[n0],
                        p1=self.nodes[n1],
                        node_c_map=self.node_c_map,
                        next_node_c_key=self.next_node_c_key,
                        node_cs=self.node_cs,
                        thickness=strip_thick,
                        foundation_tag="abutment_left",
                    )
                    self.next_restraint_key += 1
                    self.restraints.append(res)

            # Left Abutment Backfill: Z in [dz_springing, deck_z]
            fill_mat_al = spec.left_abutment.spandrel_material_key if is_exterior else spec.left_abutment.backfill_material_key
            for c in range(ab_m_l):
                for k in range(N_rows):
                    n0 = self._get_or_create_node(x_ab_cols_top[c], y, z_rows[k])
                    n1 = self._get_or_create_node(x_ab_cols_top[c + 1], y, z_rows[k])
                    n2 = self._get_or_create_node(x_ab_cols_top[c + 1], y, z_rows[k + 1])
                    n3 = self._get_or_create_node(x_ab_cols_top[c], y, z_rows[k + 1])
                    self._add_quad(n0, n1, n2, n3, fill_mat_al, strip_thick, f"Abutment_Left_{fill_grp_suffix}")

            # B. Piers
            for p_idx, pier in enumerate(spec.piers):
                x_p_start, x_p_end, x_p_center = pier_bounds[p_idx]
                dx_L = span_dx[p_idx]
                dx_R = span_dx[p_idx + 1]

                # 1) Spread Footing: Z in [-H - Hf, -H]
                h_shaft_p = pier.height
                h_fnd_p = pier.foundation_height
                z_fnd_bot_p = -h_shaft_p - h_fnd_p
                z_shaft_bot_p = -h_shaft_p

                n_fnd_p = max(1, int(round(h_fnd_p / mesh_sz)))
                z_fnd_rows = [z_fnd_bot_p + r * (h_fnd_p / n_fnd_p) for r in range(n_fnd_p + 1)]

                b_wing = max(0.0, (pier.foundation_length - pier.thickness) / 2.0)
                x_fnd_left = x_p_start - b_wing
                x_fnd_right = x_p_end + b_wing

                # Footing wings & center
                if b_wing > 1e-4:
                    for r in range(n_fnd_p):
                        n0 = self._get_or_create_node(x_fnd_left, y, z_fnd_rows[r])
                        n1 = self._get_or_create_node(x_p_start, y, z_fnd_rows[r])
                        n2 = self._get_or_create_node(x_p_start, y, z_fnd_rows[r + 1])
                        n3 = self._get_or_create_node(x_fnd_left, y, z_fnd_rows[r + 1])
                        q = self._add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, f"Pier_{p_idx + 1}_Foundation")
                        if r == 0:
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=self.nodes[n0],
                                p1=self.nodes[n1],
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

                # Shaft columns setup
                p_m = 2 # 2 columns under shaft
                x_p_cols = [x_p_start, x_p_center, x_p_end]
                for c in range(p_m):
                    for r in range(n_fnd_p):
                        n0 = self._get_or_create_node(x_p_cols[c], y, z_fnd_rows[r])
                        n1 = self._get_or_create_node(x_p_cols[c + 1], y, z_fnd_rows[r])
                        n2 = self._get_or_create_node(x_p_cols[c + 1], y, z_fnd_rows[r + 1])
                        n3 = self._get_or_create_node(x_p_cols[c], y, z_fnd_rows[r + 1])
                        q = self._add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, f"Pier_{p_idx + 1}_Foundation")
                        if r == 0:
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=self.nodes[n0],
                                p1=self.nodes[n1],
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

                if b_wing > 1e-4:
                    for r in range(n_fnd_p):
                        n0 = self._get_or_create_node(x_p_end, y, z_fnd_rows[r])
                        n1 = self._get_or_create_node(x_fnd_right, y, z_fnd_rows[r])
                        n2 = self._get_or_create_node(x_fnd_right, y, z_fnd_rows[r + 1])
                        n3 = self._get_or_create_node(x_p_end, y, z_fnd_rows[r + 1])
                        q = self._add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, f"Pier_{p_idx + 1}_Foundation")
                        if r == 0:
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=self.nodes[n0],
                                p1=self.nodes[n1],
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

                # 2) Pier Shaft: Z in [-H, 0]
                n_shaft_p = max(2, int(round(h_shaft_p / mesh_sz)))
                z_shaft_rows = [z_shaft_bot_p + r * (h_shaft_p / n_shaft_p) for r in range(n_shaft_p + 1)]
                for c in range(p_m):
                    for r in range(n_shaft_p):
                        n0 = self._get_or_create_node(x_p_cols[c], y, z_shaft_rows[r])
                        n1 = self._get_or_create_node(x_p_cols[c + 1], y, z_shaft_rows[r])
                        n2 = self._get_or_create_node(x_p_cols[c + 1], y, z_shaft_rows[r + 1])
                        n3 = self._get_or_create_node(x_p_cols[c], y, z_shaft_rows[r + 1])
                        self._add_quad(n0, n1, n2, n3, pier.material_key, strip_thick, f"Pier_{p_idx + 1}_Shaft")

                # 3) Trapezoidal Pulvino Pier Cap: Z in [0, dz_springing]
                n0 = self._get_or_create_node(x_p_start, y, 0.0)
                n1 = self._get_or_create_node(x_p_center, y, 0.0)
                n2 = self._get_or_create_node(x_p_center, y, dz_springing)
                n3 = self._get_or_create_node(x_p_start + dx_L, y, dz_springing)
                self._add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, f"Pier_{p_idx + 1}_Cap")

                n0 = self._get_or_create_node(x_p_center, y, 0.0)
                n1 = self._get_or_create_node(x_p_end, y, 0.0)
                n2 = self._get_or_create_node(x_p_end - dx_R, y, dz_springing)
                n3 = self._get_or_create_node(x_p_center, y, dz_springing)
                self._add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, f"Pier_{p_idx + 1}_Cap")

                # 4) Pier Backfill above Pulvino: Z in [dz_springing, deck_z]
                fill_mat_p = spec.spans[p_idx].spandrel_material_key if is_exterior else spec.spans[p_idx].backfill_material_key
                for k in range(N_rows):
                    n0 = self._get_or_create_node(x_p_start + dx_L, y, z_rows[k])
                    n1 = self._get_or_create_node(x_p_center, y, z_rows[k])
                    n2 = self._get_or_create_node(x_p_center, y, z_rows[k + 1])
                    n3 = self._get_or_create_node(x_p_start + dx_L, y, z_rows[k + 1])
                    self._add_quad(n0, n1, n2, n3, fill_mat_p, strip_thick, f"Pier_{p_idx + 1}_{fill_grp_suffix}")

                for k in range(N_rows):
                    n0 = self._get_or_create_node(x_p_center, y, z_rows[k])
                    n1 = self._get_or_create_node(x_p_end - dx_R, y, z_rows[k])
                    n2 = self._get_or_create_node(x_p_end - dx_R, y, z_rows[k + 1])
                    n3 = self._get_or_create_node(x_p_center, y, z_rows[k + 1])
                    self._add_quad(n0, n1, n2, n3, fill_mat_p, strip_thick, f"Pier_{p_idx + 1}_{fill_grp_suffix}")

            # C. Right Abutment
            b_ab_r = spec.right_abutment.thickness
            dx_end = span_dx[-1]
            ab_m_r = max(1, int(round((b_ab_r - dx_end) / mesh_sz)))
            x_abr_cols_bot = [x_ar_start + c * b_ab_r / ab_m_r for c in range(ab_m_r + 1)]
            x_abr_cols_top = [x_ar_start + dx_end + c * (b_ab_r - dx_end) / ab_m_r for c in range(ab_m_r + 1)]

            h_fnd_ar = spec.right_abutment.foundation_height
            h_shaft_ar = spec.right_abutment.height
            z_ar_bot = -h_shaft_ar - h_fnd_ar

            if z_ar_bot < -1e-4:
                n_fnd_ar = max(1, int(round(h_fnd_ar / mesh_sz))) if h_fnd_ar > 0 else 0
                n_shaft_ar = max(1, int(round(h_shaft_ar / mesh_sz))) if h_shaft_ar > 0 else 0
                z_ar_sub: List[float] = []
                for r in range(n_fnd_ar):
                    z_ar_sub.append(z_ar_bot + (r / max(1, n_fnd_ar)) * h_fnd_ar)
                z_shaft_bot = -h_shaft_ar
                for r in range(n_shaft_ar):
                    z_ar_sub.append(z_shaft_bot + (r / max(1, n_shaft_ar)) * h_shaft_ar)
                z_ar_sub.append(0.0)

                for c in range(ab_m_r):
                    for r in range(len(z_ar_sub) - 1):
                        n0 = self._get_or_create_node(x_abr_cols_bot[c], y, z_ar_sub[r])
                        n1 = self._get_or_create_node(x_abr_cols_bot[c + 1], y, z_ar_sub[r])
                        n2 = self._get_or_create_node(x_abr_cols_bot[c + 1], y, z_ar_sub[r + 1])
                        n3 = self._get_or_create_node(x_abr_cols_bot[c], y, z_ar_sub[r + 1])
                        mat = spec.right_abutment.foundation_material_key if r < n_fnd_ar else spec.right_abutment.material_key
                        grp = "Abutment_Right_Foundation" if r < n_fnd_ar else "Abutment_Right_Shaft"
                        q = self._add_quad(n0, n1, n2, n3, mat, strip_thick, grp)
                        if r == 0:
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=self.nodes[n0],
                                p1=self.nodes[n1],
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag="abutment_right",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)

            # Right Abutment Cap: Z in [0, dz_springing]
            for c in range(ab_m_r):
                n0 = self._get_or_create_node(x_abr_cols_bot[c], y, 0.0)
                n1 = self._get_or_create_node(x_abr_cols_bot[c + 1], y, 0.0)
                n2 = self._get_or_create_node(x_abr_cols_top[c + 1], y, dz_springing)
                n3 = self._get_or_create_node(x_abr_cols_top[c], y, dz_springing)
                q = self._add_quad(n0, n1, n2, n3, spec.right_abutment.cap_material_key, strip_thick, "Abutment_Right_Cap")
                if z_ar_bot >= -1e-4:
                    res, self.next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=self.next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=self.nodes[n0],
                        p1=self.nodes[n1],
                        node_c_map=self.node_c_map,
                        next_node_c_key=self.next_node_c_key,
                        node_cs=self.node_cs,
                        thickness=strip_thick,
                        foundation_tag="abutment_right",
                    )
                    self.next_restraint_key += 1
                    self.restraints.append(res)

            # Right Abutment Backfill: Z in [dz_springing, deck_z]
            fill_mat_ar = spec.right_abutment.spandrel_material_key if is_exterior else spec.right_abutment.backfill_material_key
            for c in range(ab_m_r):
                for k in range(N_rows):
                    n0 = self._get_or_create_node(x_abr_cols_top[c], y, z_rows[k])
                    n1 = self._get_or_create_node(x_abr_cols_top[c + 1], y, z_rows[k])
                    n2 = self._get_or_create_node(x_abr_cols_top[c + 1], y, z_rows[k + 1])
                    n3 = self._get_or_create_node(x_abr_cols_top[c], y, z_rows[k + 1])
                    self._add_quad(n0, n1, n2, n3, fill_mat_ar, strip_thick, f"Abutment_Right_{fill_grp_suffix}")

            # D. Arch Spans and Superstructure Backfill
            for s_idx, span in enumerate(spec.spans):
                x_int_start, x_int_end = span_int_bounds[s_idx]
                dx_s = span_dx[s_idx]
                x_ext_start = x_int_start - dx_s
                x_ext_end = x_int_end + dx_s

                L = span.length
                f = span.rise
                Tt = span.thickness_crown
                xc_int = (x_int_start + x_int_end) / 2.0
                xc_ext = xc_int
                zc_ext = f + Tt

                m_span = max(4, 2 * int(round(L / (2.0 * mesh_sz))))
                half_m = m_span // 2

                pts_int = []
                pts_ext = []

                for s in range(m_span + 1):
                    th = s * math.pi / m_span
                    xi = xc_int - (L / 2.0) * math.cos(th)
                    zi = f * math.sin(th)
                    if s == 0:
                        xi = x_int_start
                        zi = 0.0
                    elif s == m_span:
                        xi = x_int_end
                        zi = 0.0

                    if s <= half_m:
                        t_half = s / half_m
                        th_h = t_half * (math.pi / 2.0)
                        xe = xc_ext - (xc_ext - x_ext_start) * math.cos(th_h)
                        ze = dz_springing + (zc_ext - dz_springing) * math.sin(th_h)
                    else:
                        t_half = (s - half_m) / half_m
                        th_h = t_half * (math.pi / 2.0)
                        xe = xc_ext + (x_ext_end - xc_ext) * math.sin(th_h)
                        ze = zc_ext - (zc_ext - dz_springing) * (1.0 - math.cos(th_h))

                    pts_int.append((round(xi, 4), round(zi, 4)))
                    pts_ext.append((round(xe, 4), round(ze, 4)))

                # 1) Arch Ring Quads
                for s in range(m_span):
                    xi0, zi0 = pts_int[s]
                    xi1, zi1 = pts_int[s + 1]
                    xe0, ze0 = pts_ext[s]
                    xe1, ze1 = pts_ext[s + 1]

                    n0 = self._get_or_create_node(xi0, y, zi0)
                    n1 = self._get_or_create_node(xi1, y, zi1)
                    n2 = self._get_or_create_node(xe1, y, ze1)
                    n3 = self._get_or_create_node(xe0, y, ze0)
                    self._add_quad(n0, n1, n2, n3, span.material_key, strip_thick, f"Span_{s_idx + 1}_Arch")

                # 2) Backfill / Spandrel Quads
                fill_mat_s = span.spandrel_material_key if is_exterior else span.backfill_material_key
                for s in range(m_span):
                    xe0, ze0 = pts_ext[s]
                    xe1, ze1 = pts_ext[s + 1]

                    z_col0 = [ze0 + k * (deck_z - ze0) / N_rows for k in range(N_rows + 1)]
                    z_col1 = [ze1 + k * (deck_z - ze1) / N_rows for k in range(N_rows + 1)]

                    for k in range(N_rows):
                        n0 = self._get_or_create_node(xe0, y, z_col0[k])
                        n1 = self._get_or_create_node(xe1, y, z_col1[k])
                        n2 = self._get_or_create_node(xe1, y, z_col1[k + 1])
                        n3 = self._get_or_create_node(xe0, y, z_col0[k + 1])
                        self._add_quad(n0, n1, n2, n3, fill_mat_s, strip_thick, f"Span_{s_idx + 1}_{fill_grp_suffix}")

        # 6. Metadata and Monitoring Points
        piers_meta: List[PierMetadata] = []
        for p_idx, pier in enumerate(spec.piers):
            x_p_start, x_p_end, x_p_center = pier_bounds[p_idx]
            piers_meta.append(
                PierMetadata(
                    id=f"pier_{p_idx + 1}",
                    index=p_idx + 1,
                    origin=Point3D(x_p_center, 0.0, 0.0),
                    x_start=x_p_start,
                    x_end=x_p_end,
                    restraint_keys=sorted(list(set(pier_restraints_map[p_idx]))),
                )
            )

        if len(pier_bounds) > 0:
            mon_x = pier_bounds[0][2]
            mon_desc = "Pier 1 Centerline Deck"
        else:
            mon_x = span_int_bounds[0][0] + spec.spans[0].length / 2.0
            mon_desc = "Midspan Deck Centerline"

        mon_node = self._get_or_create_node(mon_x, y_strips[0], deck_z)
        self.monitoring_points = [
            MonitoringPoint(
                key=1,
                element_key=mon_node,
                element_type="Node",
                id_vertex=0,
                description=mon_desc,
                point=self.nodes[mon_node],
            )
        ]
        self.piers = piers_meta

        return GeneratedBridgeMesh(
            spec=spec,
            nodes=self.nodes,
            quads=self.quads,
            restraints=self.restraints,
            node_cs=self.node_cs,
            piers=self.piers,
            monitoring_points=self.monitoring_points,
            deck_z=deck_z,
            total_length=x_total,
        )


def build_isolated_pier_mesh(
    pier: PierSpec,
    width: float = 200.0,
    target_mesh_size: float = 30.0,
    num_transverse_strips: int = 1,
    include_cap: bool = True,
) -> GeneratedBridgeMesh:
    """Generate an authentic isolated pier finite element model matching the bridge pier."""
    nodes: Dict[int, Point3D] = {}
    node_lookup: Dict[Tuple[float, float, float], int] = {}
    next_node_key = 1

    def get_or_create_node(x: float, y: float, z: float) -> int:
        nonlocal next_node_key
        coord_key = (round(x, 4), round(y, 4), round(z, 4))
        if coord_key in node_lookup:
            return node_lookup[coord_key]
        k = next_node_key
        next_node_key += 1
        nodes[k] = Point3D(round(x, 4), round(y, 4), round(z, 4))
        node_lookup[coord_key] = k
        return k

    quads: Dict[int, GeneratedQuad] = {}
    next_quad_key = 1

    def add_quad(
        n0: int,
        n1: int,
        n2: int,
        n3: int,
        mat: int,
        thick: float,
        grp: str,
    ) -> GeneratedQuad:
        nonlocal next_quad_key
        p0, p1, p2, p3 = nodes[n0], nodes[n1], nodes[n2], nodes[n3]
        area = signed_area_xz([p0, p1, p2, p3])
        if area < 0:
            n0, n1, n2, n3 = n0, n3, n2, n1
            p0, p1, p2, p3 = p0, p3, p2, p1
        kin = compute_quad_kinematics([p0, p1, p2, p3], thickness=thick)
        q = GeneratedQuad(
            key=next_quad_key,
            node_keys=(n0, n1, n2, n3),
            material_key=mat,
            thickness=thick,
            kinematics=kin,
            group=grp,
        )
        quads[next_quad_key] = q
        next_quad_key += 1
        return q

    restraints: List[GeneratedRestraint] = []
    node_cs: List[GeneratedNodeC] = []
    node_c_map: Dict[int, int] = {}
    next_restraint_key = 1
    next_node_c_key = 1

    # Geometry setup
    mesh_sz = target_mesh_size
    nt = max(1, num_transverse_strips)
    strip_thick = width / nt
    y_strips = [-width / 2.0 + (j + 0.5) * strip_thick for j in range(nt)]

    # Standard HiStrA springing angle alpha (cos_a = 0.8, sin_a = 0.6)
    alpha = 36.8699 * math.pi / 180.0
    cos_a = math.cos(alpha)
    sin_a = math.sin(alpha)
    tb = pier.cap_height if pier.cap_height > 0 else 35.0
    dx = round(tb * cos_a, 4)
    dz = round(tb * sin_a, 4)

    p_m = 2
    x_p_cols = [0.0, pier.thickness / 2.0, pier.thickness]

    h_fnd_p = pier.foundation_height
    h_shaft_p = pier.height
    z_fnd_bot_p = -h_shaft_p - h_fnd_p
    z_shaft_bot_p = -h_shaft_p

    n_fnd_p = max(1, int(round(h_fnd_p / mesh_sz)))
    z_fnd_rows = [z_fnd_bot_p + (r / n_fnd_p) * h_fnd_p for r in range(n_fnd_p + 1)]

    b_wing = max(0.0, (pier.foundation_length - pier.thickness) / 2.0)
    x_fnd_left = -b_wing
    x_fnd_right = pier.thickness + b_wing

    pier_restraint_keys: List[int] = []

    for y in y_strips:
        # 1. Foundation Footing (Spread Footing at Z in [-H - Hf, -H])
        if b_wing > 1e-4:
            for r in range(n_fnd_p):
                n0 = get_or_create_node(x_fnd_left, y, z_fnd_rows[r])
                n1 = get_or_create_node(0.0, y, z_fnd_rows[r])
                n2 = get_or_create_node(0.0, y, z_fnd_rows[r + 1])
                n3 = get_or_create_node(x_fnd_left, y, z_fnd_rows[r + 1])
                q = add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, "Pier_Foundation")
                if r == 0:
                    res, next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=nodes[n0],
                        p1=nodes[n1],
                        node_c_map=node_c_map,
                        next_node_c_key=next_node_c_key,
                        node_cs=node_cs,
                        thickness=strip_thick,
                        foundation_tag="pier",
                    )
                    next_restraint_key += 1
                    restraints.append(res)
                    pier_restraint_keys.append(res.key)

        for c in range(p_m):
            for r in range(n_fnd_p):
                n0 = get_or_create_node(x_p_cols[c], y, z_fnd_rows[r])
                n1 = get_or_create_node(x_p_cols[c + 1], y, z_fnd_rows[r])
                n2 = get_or_create_node(x_p_cols[c + 1], y, z_fnd_rows[r + 1])
                n3 = get_or_create_node(x_p_cols[c], y, z_fnd_rows[r + 1])
                q = add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, "Pier_Foundation")
                if r == 0:
                    res, next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=nodes[n0],
                        p1=nodes[n1],
                        node_c_map=node_c_map,
                        next_node_c_key=next_node_c_key,
                        node_cs=node_cs,
                        thickness=strip_thick,
                        foundation_tag="pier",
                    )
                    next_restraint_key += 1
                    restraints.append(res)
                    pier_restraint_keys.append(res.key)

        if b_wing > 1e-4:
            for r in range(n_fnd_p):
                n0 = get_or_create_node(pier.thickness, y, z_fnd_rows[r])
                n1 = get_or_create_node(x_fnd_right, y, z_fnd_rows[r])
                n2 = get_or_create_node(x_fnd_right, y, z_fnd_rows[r + 1])
                n3 = get_or_create_node(pier.thickness, y, z_fnd_rows[r + 1])
                q = add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, "Pier_Foundation")
                if r == 0:
                    res, next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=nodes[n0],
                        p1=nodes[n1],
                        node_c_map=node_c_map,
                        next_node_c_key=next_node_c_key,
                        node_cs=node_cs,
                        thickness=strip_thick,
                        foundation_tag="pier",
                    )
                    next_restraint_key += 1
                    restraints.append(res)
                    pier_restraint_keys.append(res.key)

        # 2. Pier Shaft Quads: Strictly Z in [-H, 0]
        n_shaft_p = max(2, int(round(h_shaft_p / mesh_sz)))
        z_shaft_rows = [z_shaft_bot_p + (r / n_shaft_p) * h_shaft_p for r in range(n_shaft_p + 1)]
        for c in range(p_m):
            for r in range(n_shaft_p):
                n0 = get_or_create_node(x_p_cols[c], y, z_shaft_rows[r])
                n1 = get_or_create_node(x_p_cols[c + 1], y, z_shaft_rows[r])
                n2 = get_or_create_node(x_p_cols[c + 1], y, z_shaft_rows[r + 1])
                n3 = get_or_create_node(x_p_cols[c], y, z_shaft_rows[r + 1])
                add_quad(n0, n1, n2, n3, pier.material_key, strip_thick, "Pier_Shaft")

        # 3. Authentic Pulvino Pier Cap (Trapezoidal impost block): Z in [0, dz]
        if include_cap and dz > 1e-4:
            if pier.thickness > 2.0 * dx:
                # Left Pulvino trapezoid
                n0 = get_or_create_node(0.0, y, 0.0)
                n1 = get_or_create_node(pier.thickness / 2.0, y, 0.0)
                n2 = get_or_create_node(pier.thickness / 2.0, y, dz)
                n3 = get_or_create_node(dx, y, dz)
                add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, "Pier_Cap")

                # Right Pulvino trapezoid
                n0 = get_or_create_node(pier.thickness / 2.0, y, 0.0)
                n1 = get_or_create_node(pier.thickness, y, 0.0)
                n2 = get_or_create_node(pier.thickness - dx, y, dz)
                n3 = get_or_create_node(pier.thickness / 2.0, y, dz)
                add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, "Pier_Cap")
            else:
                for c in range(p_m):
                    n0 = get_or_create_node(x_p_cols[c], y, 0.0)
                    n1 = get_or_create_node(x_p_cols[c + 1], y, 0.0)
                    n2 = get_or_create_node(x_p_cols[c + 1], y, dz)
                    n3 = get_or_create_node(x_p_cols[c], y, dz)
                    add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, "Pier_Cap")

    top_z = dz if include_cap else 0.0
    top_mid_node = get_or_create_node(pier.thickness / 2.0, y_strips[0], top_z)
    monitoring = [
        MonitoringPoint(
            key=1,
            element_key=top_mid_node,
            element_type="Node",
            description=f"Pier Top Center (X={pier.thickness / 2.0:.1f}, Z={top_z:.1f})",
            point=nodes[top_mid_node],
        )
    ]

    spec = BridgeSpec(
        name="IsolatedPier",
        width=width,
        target_mesh_size=target_mesh_size,
        num_transverse_strips=num_transverse_strips,
        spans=[],
        piers=[pier],
    )

    piers_meta = [
        PierMetadata(
            id="pier_1",
            index=1,
            origin=Point3D(pier.thickness / 2.0, 0.0, 0.0),
            x_start=0.0,
            x_end=pier.thickness,
            restraint_keys=sorted(list(set(pier_restraint_keys))),
        )
    ]

    return GeneratedBridgeMesh(
        spec=spec,
        nodes=nodes,
        quads=quads,
        restraints=restraints,
        node_cs=node_cs,
        piers=piers_meta,
        monitoring_points=monitoring,
        deck_z=top_z,
        total_length=pier.foundation_length,
    )
