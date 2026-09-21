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

        # 1. Establish deck elevation
        # 1. Establish deck elevation
        z_crown_max = max(s.rise + s.thickness_crown for s in spec.spans)
        deck_z = z_crown_max + spec.deck_clearance
        z_cap = max(s.thickness_springer for s in spec.spans)

        # 2. Longitudinal layout
        # Left Abutment
        x_cur = 0.0
        x_al_start = x_cur
        x_al_end = x_cur + spec.left_abutment.thickness
        x_cur = x_al_end

        span_layouts: List[Tuple[float, float]] = []
        pier_layouts: List[Tuple[float, float, float]] = []

        for i, span in enumerate(spec.spans):
            x_sp_start = x_cur
            x_sp_end = x_cur + span.length
            span_layouts.append((x_sp_start, x_sp_end))
            x_cur = x_sp_end

            if i < len(spec.piers):
                pier = spec.piers[i]
                x_p_start = x_cur
                x_p_end = x_cur + pier.thickness
                x_p_center = x_p_start + pier.thickness / 2.0
                pier_layouts.append((x_p_start, x_p_end, x_p_center))
                x_cur = x_p_end

        # Right Abutment
        x_ar_start = x_cur
        x_ar_end = x_cur + spec.right_abutment.thickness
        x_total = x_ar_end

        # 3. Transverse strip layout
        nt = spec.num_transverse_strips
        strip_thick = spec.width / nt
        y_strips = [
            -spec.width / 2.0 + (j + 0.5) * strip_thick for j in range(nt)
        ]

        # Tracking pier restraints per pier index
        pier_restraints_map: Dict[int, List[int]] = {i: [] for i in range(len(spec.piers))}

        # 4. Generate mesh per transverse strip
        for strip_idx, y in enumerate(y_strips):
            is_exterior = (nt > 1) and (strip_idx == 0 or strip_idx == nt - 1)
            fill_mat = spec.spans[0].spandrel_material_key if is_exterior else spec.spans[0].backfill_material_key
            fill_grp_suffix = "Spandrel" if is_exterior else "Backfill"

            # A. Left Abutment
            al_thick = spec.left_abutment.thickness
            al_m = max(2, int(round(al_thick / mesh_sz)))
            x_al_cols = [x_al_start + (c / al_m) * al_thick for c in range(al_m + 1)]

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

                for c in range(al_m):
                    for r in range(len(z_al_sub) - 1):
                        n0 = self._get_or_create_node(x_al_cols[c], y, z_al_sub[r])
                        n1 = self._get_or_create_node(x_al_cols[c + 1], y, z_al_sub[r])
                        n2 = self._get_or_create_node(x_al_cols[c + 1], y, z_al_sub[r + 1])
                        n3 = self._get_or_create_node(x_al_cols[c], y, z_al_sub[r + 1])
                        mat = spec.left_abutment.foundation_material_key if r < n_fnd_al else spec.left_abutment.material_key
                        grp = "Abutment_Left_Foundation" if r < n_fnd_al else "Abutment_Left_Shaft"
                        q = self._add_quad(n0, n1, n2, n3, mat, strip_thick, grp)
                        if r == 0:
                            p0 = self.nodes[n0]
                            p1 = self.nodes[n1]
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=p0,
                                p1=p1,
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag="abutment_left",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)

            # Above Z = 0: Impost cap layer [0, z_cap]
            for c in range(al_m):
                n0 = self._get_or_create_node(x_al_cols[c], y, 0.0)
                n1 = self._get_or_create_node(x_al_cols[c + 1], y, 0.0)
                n2 = self._get_or_create_node(x_al_cols[c + 1], y, z_cap)
                n3 = self._get_or_create_node(x_al_cols[c], y, z_cap)
                q = self._add_quad(n0, n1, n2, n3, spec.left_abutment.cap_material_key, strip_thick, "Abutment_Left_Cap")
                if z_al_bot >= -1e-4:
                    p0 = self.nodes[n0]
                    p1 = self.nodes[n1]
                    res, self.next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=self.next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=p0,
                        p1=p1,
                        node_c_map=self.node_c_map,
                        next_node_c_key=self.next_node_c_key,
                        node_cs=self.node_cs,
                        thickness=strip_thick,
                        foundation_tag="abutment_left",
                    )
                    self.next_restraint_key += 1
                    self.restraints.append(res)

            # Left Abutment Fill above Impost [z_cap, deck_z]
            n_deck_al = max(1, int(round((deck_z - z_cap) / mesh_sz)))
            for c in range(al_m):
                for r in range(n_deck_al):
                    z0 = z_cap + (r / n_deck_al) * (deck_z - z_cap)
                    z1 = z_cap + ((r + 1) / n_deck_al) * (deck_z - z_cap)
                    n0 = self._get_or_create_node(x_al_cols[c], y, z0)
                    n1 = self._get_or_create_node(x_al_cols[c + 1], y, z0)
                    n2 = self._get_or_create_node(x_al_cols[c + 1], y, z1)
                    n3 = self._get_or_create_node(x_al_cols[c], y, z1)
                    self._add_quad(n0, n1, n2, n3, fill_mat, strip_thick, f"Abutment_Left_{fill_grp_suffix}")

            # B. Intermediate Piers
            for p_idx, pier in enumerate(spec.piers):
                x_p_start, x_p_end, x_p_center = pier_layouts[p_idx]
                p_m = max(2, int(round(pier.thickness / mesh_sz)))
                x_p_cols = [x_p_start + (c / p_m) * pier.thickness for c in range(p_m + 1)]

                h_fnd_p = pier.foundation_height
                h_shaft_p = pier.height
                z_fnd_bot_p = -h_shaft_p - h_fnd_p
                z_shaft_bot_p = -h_shaft_p

                # 1) Pier Foundation Footing (Spread Footing at Z in [-H - Hf, -H])
                n_fnd_p = max(1, int(round(h_fnd_p / mesh_sz)))
                z_fnd_rows = [z_fnd_bot_p + (r / n_fnd_p) * h_fnd_p for r in range(n_fnd_p + 1)]

                b_wing = max(0.0, (pier.foundation_length - pier.thickness) / 2.0)
                x_fnd_left = x_p_start - b_wing
                x_fnd_right = x_p_end + b_wing

                # Left footing wing
                if b_wing > 1e-4:
                    for r in range(n_fnd_p):
                        n0 = self._get_or_create_node(x_fnd_left, y, z_fnd_rows[r])
                        n1 = self._get_or_create_node(x_p_start, y, z_fnd_rows[r])
                        n2 = self._get_or_create_node(x_p_start, y, z_fnd_rows[r + 1])
                        n3 = self._get_or_create_node(x_fnd_left, y, z_fnd_rows[r + 1])
                        q = self._add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, f"Pier_{p_idx + 1}_Foundation")
                        if r == 0:
                            p0 = self.nodes[n0]
                            p1 = self.nodes[n1]
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=p0,
                                p1=p1,
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

                # Center footing (under shaft columns)
                for c in range(p_m):
                    for r in range(n_fnd_p):
                        n0 = self._get_or_create_node(x_p_cols[c], y, z_fnd_rows[r])
                        n1 = self._get_or_create_node(x_p_cols[c + 1], y, z_fnd_rows[r])
                        n2 = self._get_or_create_node(x_p_cols[c + 1], y, z_fnd_rows[r + 1])
                        n3 = self._get_or_create_node(x_p_cols[c], y, z_fnd_rows[r + 1])
                        q = self._add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, f"Pier_{p_idx + 1}_Foundation")
                        if r == 0:
                            p0 = self.nodes[n0]
                            p1 = self.nodes[n1]
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=p0,
                                p1=p1,
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

                # Right footing wing
                if b_wing > 1e-4:
                    for r in range(n_fnd_p):
                        n0 = self._get_or_create_node(x_p_end, y, z_fnd_rows[r])
                        n1 = self._get_or_create_node(x_fnd_right, y, z_fnd_rows[r])
                        n2 = self._get_or_create_node(x_fnd_right, y, z_fnd_rows[r + 1])
                        n3 = self._get_or_create_node(x_p_end, y, z_fnd_rows[r + 1])
                        q = self._add_quad(n0, n1, n2, n3, pier.foundation_material_key, strip_thick, f"Pier_{p_idx + 1}_Foundation")
                        if r == 0:
                            p0 = self.nodes[n0]
                            p1 = self.nodes[n1]
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=p0,
                                p1=p1,
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

                # 2) Pier Shaft Quads: Strictly Z in [-H, 0]!
                n_shaft_p = max(2, int(round(h_shaft_p / mesh_sz)))
                z_shaft_rows = [z_shaft_bot_p + (r / n_shaft_p) * h_shaft_p for r in range(n_shaft_p + 1)]
                for c in range(p_m):
                    for r in range(n_shaft_p):
                        n0 = self._get_or_create_node(x_p_cols[c], y, z_shaft_rows[r])
                        n1 = self._get_or_create_node(x_p_cols[c + 1], y, z_shaft_rows[r])
                        n2 = self._get_or_create_node(x_p_cols[c + 1], y, z_shaft_rows[r + 1])
                        n3 = self._get_or_create_node(x_p_cols[c], y, z_shaft_rows[r + 1])
                        self._add_quad(n0, n1, n2, n3, pier.material_key, strip_thick, f"Pier_{p_idx + 1}_Shaft")

                # 3) Pier Cap Quads: Z in [0, z_cap]
                for c in range(p_m):
                    n0 = self._get_or_create_node(x_p_cols[c], y, 0.0)
                    n1 = self._get_or_create_node(x_p_cols[c + 1], y, 0.0)
                    n2 = self._get_or_create_node(x_p_cols[c + 1], y, z_cap)
                    n3 = self._get_or_create_node(x_p_cols[c], y, z_cap)
                    self._add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, f"Pier_{p_idx + 1}_Cap")

                # 4) Backfill / Spandrel above Pier Cap: Z in [z_cap, deck_z]
                n_deck_p = max(1, int(round((deck_z - z_cap) / mesh_sz)))
                for c in range(p_m):
                    for r in range(n_deck_p):
                        z0 = z_cap + (r / n_deck_p) * (deck_z - z_cap)
                        z1 = z_cap + ((r + 1) / n_deck_p) * (deck_z - z_cap)
                        n0 = self._get_or_create_node(x_p_cols[c], y, z0)
                        n1 = self._get_or_create_node(x_p_cols[c + 1], y, z0)
                        n2 = self._get_or_create_node(x_p_cols[c + 1], y, z1)
                        n3 = self._get_or_create_node(x_p_cols[c], y, z1)
                        self._add_quad(n0, n1, n2, n3, fill_mat, strip_thick, f"Pier_{p_idx + 1}_{fill_grp_suffix}")

            # C. Right Abutment
            ar_thick = spec.right_abutment.thickness
            ar_m = max(2, int(round(ar_thick / mesh_sz)))
            x_ar_cols = [x_ar_start + (c / ar_m) * ar_thick for c in range(ar_m + 1)]

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

                for c in range(ar_m):
                    for r in range(len(z_ar_sub) - 1):
                        n0 = self._get_or_create_node(x_ar_cols[c], y, z_ar_sub[r])
                        n1 = self._get_or_create_node(x_ar_cols[c + 1], y, z_ar_sub[r])
                        n2 = self._get_or_create_node(x_ar_cols[c + 1], y, z_ar_sub[r + 1])
                        n3 = self._get_or_create_node(x_ar_cols[c], y, z_ar_sub[r + 1])
                        mat = spec.right_abutment.foundation_material_key if r < n_fnd_ar else spec.right_abutment.material_key
                        grp = "Abutment_Right_Foundation" if r < n_fnd_ar else "Abutment_Right_Shaft"
                        q = self._add_quad(n0, n1, n2, n3, mat, strip_thick, grp)
                        if r == 0:
                            p0 = self.nodes[n0]
                            p1 = self.nodes[n1]
                            res, self.next_node_c_key = create_foundation_edge_restraint(
                                restraint_key=self.next_restraint_key,
                                quad_key=q.key,
                                n0_key=n0,
                                n1_key=n1,
                                p0=p0,
                                p1=p1,
                                node_c_map=self.node_c_map,
                                next_node_c_key=self.next_node_c_key,
                                node_cs=self.node_cs,
                                thickness=strip_thick,
                                foundation_tag="abutment_right",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)

            # Above Z = 0: Impost cap layer [0, z_cap]
            for c in range(ar_m):
                n0 = self._get_or_create_node(x_ar_cols[c], y, 0.0)
                n1 = self._get_or_create_node(x_ar_cols[c + 1], y, 0.0)
                n2 = self._get_or_create_node(x_ar_cols[c + 1], y, z_cap)
                n3 = self._get_or_create_node(x_ar_cols[c], y, z_cap)
                q = self._add_quad(n0, n1, n2, n3, spec.right_abutment.cap_material_key, strip_thick, "Abutment_Right_Cap")
                if z_ar_bot >= -1e-4:
                    p0 = self.nodes[n0]
                    p1 = self.nodes[n1]
                    res, self.next_node_c_key = create_foundation_edge_restraint(
                        restraint_key=self.next_restraint_key,
                        quad_key=q.key,
                        n0_key=n0,
                        n1_key=n1,
                        p0=p0,
                        p1=p1,
                        node_c_map=self.node_c_map,
                        next_node_c_key=self.next_node_c_key,
                        node_cs=self.node_cs,
                        thickness=strip_thick,
                        foundation_tag="abutment_right",
                    )
                    self.next_restraint_key += 1
                    self.restraints.append(res)

            # Right Abutment Fill above Impost [z_cap, deck_z]
            n_deck_ar = max(1, int(round((deck_z - z_cap) / mesh_sz)))
            for c in range(ar_m):
                for r in range(n_deck_ar):
                    z0 = z_cap + (r / n_deck_ar) * (deck_z - z_cap)
                    z1 = z_cap + ((r + 1) / n_deck_ar) * (deck_z - z_cap)
                    n0 = self._get_or_create_node(x_ar_cols[c], y, z0)
                    n1 = self._get_or_create_node(x_ar_cols[c + 1], y, z0)
                    n2 = self._get_or_create_node(x_ar_cols[c + 1], y, z1)
                    n3 = self._get_or_create_node(x_ar_cols[c], y, z1)
                    self._add_quad(n0, n1, n2, n3, fill_mat, strip_thick, f"Abutment_Right_{fill_grp_suffix}")

            # D. Arch Spans and Spandrels / Backfill
            for s_idx, span in enumerate(spec.spans):
                x_sp_start, x_sp_end = span_layouts[s_idx]
                m_span = max(4, 2 * int(round(span.length / (2.0 * mesh_sz))))

                # Semi-axes and center
                a = span.length / 2.0
                b = span.rise
                x_c = x_sp_start + a
                z_c = 0.0

                # Compute arch ring curves
                theta_vals = [s * (math.pi / m_span) for s in range(m_span + 1)]
                int_pts: List[Tuple[float, float]] = []
                ext_pts: List[Tuple[float, float]] = []

                for s, th in enumerate(theta_vals):
                    xi = x_c - a * math.cos(th)
                    zi = z_c + b * math.sin(th)
                    thick = span.thickness_springer + (span.thickness_crown - span.thickness_springer) * math.sin(th)
                    xe = xi
                    ze = zi + thick

                    # Enforce exact alignment at boundaries
                    if s == 0:
                        xi = x_sp_start
                        zi = 0.0
                        xe = x_sp_start
                        ze = span.thickness_springer
                    elif s == m_span:
                        xi = x_sp_end
                        zi = 0.0
                        xe = x_sp_end
                        ze = span.thickness_springer

                    int_pts.append((round(xi, 4), round(zi, 4)))
                    ext_pts.append((round(xe, 4), round(ze, 4)))

                # Mesh Arch Ring Quads (Material 18)
                for s in range(m_span):
                    xi0, zi0 = int_pts[s]
                    xi1, zi1 = int_pts[s + 1]
                    xe0, ze0 = ext_pts[s]
                    xe1, ze1 = ext_pts[s + 1]

                    n0 = self._get_or_create_node(xi0, y, zi0)
                    n1 = self._get_or_create_node(xi1, y, zi1)
                    n2 = self._get_or_create_node(xe1, y, ze1)
                    n3 = self._get_or_create_node(xe0, y, ze0)

                    self._add_quad(n0, n1, n2, n3, span.material_key, strip_thick, f"Span_{s_idx + 1}_Arch")

                # Mesh Backfill / Spandrel above Arch Extrados up to deck
                for s in range(m_span):
                    xe0, ze0 = ext_pts[s]
                    xe1, ze1 = ext_pts[s + 1]
                    z_bot_avg = (ze0 + ze1) / 2.0
                    n_sp_span = max(1, int(round((deck_z - z_bot_avg) / mesh_sz)))

                    for k in range(n_sp_span):
                        zk0 = ze0 + (k / n_sp_span) * (deck_z - ze0)
                        zk1 = ze1 + (k / n_sp_span) * (deck_z - ze1)
                        zk0_next = ze0 + ((k + 1) / n_sp_span) * (deck_z - ze0)
                        zk1_next = ze1 + ((k + 1) / n_sp_span) * (deck_z - ze1)

                        n0 = self._get_or_create_node(xe0, y, zk0)
                        n1 = self._get_or_create_node(xe1, y, zk1)
                        n2 = self._get_or_create_node(xe1, y, zk1_next)
                        n3 = self._get_or_create_node(xe0, y, zk0_next)

                        self._add_quad(
                            n0, n1, n2, n3, fill_mat, strip_thick, f"Span_{s_idx + 1}_{fill_grp_suffix}"
                        )

        # 5. Populate Pier Metadata (identifies pier origin and boundary restraints)
        for p_idx, pier in enumerate(spec.piers):
            x_p_start, x_p_end, x_p_center = pier_layouts[p_idx]
            origin_pt = Point3D(round(x_p_center, 4), 0.0, 0.0)
            meta = PierMetadata(
                id=f"pier_{p_idx + 1}",
                index=p_idx + 1,
                origin=origin_pt,
                x_start=x_p_start,
                x_end=x_p_end,
                restraint_keys=sorted(list(set(pier_restraints_map[p_idx]))),
            )
            self.piers.append(meta)

        # 6. Monitoring Points for structural displacement audits
        # Point 1: Mid-span crown top of Span 1
        s1_start, s1_end = span_layouts[0]
        s1_mid_x = (s1_start + s1_end) / 2.0
        # Find closest deck node
        deck_nodes = [
            (k, pt)
            for k, pt in self.nodes.items()
            if abs(pt.z - deck_z) < 1e-3 and abs(pt.y - y_strips[0]) < 1e-3
        ]
        deck_nodes.sort(key=lambda item: abs(item[1].x - s1_mid_x))
        if deck_nodes:
            mp_key = self.next_model_point_key
            self.next_model_point_key += 1
            self.monitoring_points.append(
                MonitoringPoint(
                    key=mp_key,
                    element_key=deck_nodes[0][0],
                    element_type="Node",
                    description=f"Deck Crown Span 1 (X={deck_nodes[0][1].x:.1f})",
                    point=deck_nodes[0][1],
                )
            )

        # Point 2: Pier 1 Top Centerline (if pier exists)
        if self.piers:
            p1_meta = self.piers[0]
            pier_nodes = [
                (k, pt)
                for k, pt in self.nodes.items()
                if abs(pt.z - 0.0) < 1e-3 and abs(pt.y - y_strips[0]) < 1e-3
            ]
            pier_nodes.sort(key=lambda item: abs(item[1].x - p1_meta.origin.x))
            if pier_nodes:
                mp_key = self.next_model_point_key
                self.next_model_point_key += 1
                self.monitoring_points.append(
                    MonitoringPoint(
                        key=mp_key,
                        element_key=pier_nodes[0][0],
                        element_type="Node",
                        description=f"Pier 1 Top Center (X={pier_nodes[0][1].x:.1f})",
                        point=pier_nodes[0][1],
                    )
                )

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

    p_m = max(2, int(round(pier.thickness / mesh_sz)))
    x_p_cols = [(c / p_m) * pier.thickness for c in range(p_m + 1)]

    h_fnd_p = pier.foundation_height
    h_shaft_p = pier.height
    z_fnd_bot_p = -h_shaft_p - h_fnd_p
    z_shaft_bot_p = -h_shaft_p
    z_cap = pier.cap_height if include_cap else 0.0

    n_fnd_p = max(1, int(round(h_fnd_p / mesh_sz)))
    z_fnd_rows = [z_fnd_bot_p + (r / n_fnd_p) * h_fnd_p for r in range(n_fnd_p + 1)]

    b_wing = max(0.0, (pier.foundation_length - pier.thickness) / 2.0)
    x_fnd_left = -b_wing
    x_fnd_right = pier.thickness + b_wing

    pier_restraint_keys: List[int] = []

    for y in y_strips:
        # 1. Foundation Footing (Spread Footing at Z in [-H - Hf, -H])
        # Left wing
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

        # Center footing (under shaft columns)
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

        # Right wing
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

        # 3. Pier Cap: Z in [0, z_cap]
        if include_cap and z_cap > 1e-4:
            for c in range(p_m):
                n0 = get_or_create_node(x_p_cols[c], y, 0.0)
                n1 = get_or_create_node(x_p_cols[c + 1], y, 0.0)
                n2 = get_or_create_node(x_p_cols[c + 1], y, z_cap)
                n3 = get_or_create_node(x_p_cols[c], y, z_cap)
                add_quad(n0, n1, n2, n3, pier.cap_material_key, strip_thick, "Pier_Cap")

    top_z = z_cap if include_cap else 0.0
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
