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
        z_crown_max = max(s.rise + s.thickness_crown for s in spec.spans)
        deck_z = z_crown_max + spec.deck_clearance

        # Superstructure shared vertical levels
        n_r = 1  # radial layer for arch ring
        t_springer_ref = max(s.thickness_springer for s in spec.spans)
        n_sp = max(2, int(round((deck_z - t_springer_ref) / mesh_sz)))
        # Z levels above 0
        z_sup: List[float] = [0.0]
        z_sup.append(t_springer_ref)
        for k in range(1, n_sp + 1):
            z_sup.append(t_springer_ref + (k / n_sp) * (deck_z - t_springer_ref))
        z_sup = sorted(list(set(z_sup)))

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
            # A. Left Abutment
            al_m = max(2, int(round(spec.left_abutment.thickness / mesh_sz)))
            x_al_cols = [x_al_start + (c / al_m) * spec.left_abutment.thickness for c in range(al_m + 1)]

            h_fnd_al = spec.left_abutment.foundation_height
            h_shaft_al = spec.left_abutment.height
            z_fnd_bot_al = -h_shaft_al - h_fnd_al
            z_shaft_bot_al = -h_shaft_al

            n_fnd_al = max(1, int(round(h_fnd_al / mesh_sz)))
            n_shaft_al = max(2, int(round(h_shaft_al / mesh_sz)))

            # Substructure Z levels (below 0)
            z_al_sub: List[float] = []
            for r in range(n_fnd_al):
                z_al_sub.append(z_fnd_bot_al + (r / n_fnd_al) * h_fnd_al)
            for r in range(n_shaft_al):
                z_al_sub.append(z_shaft_bot_al + (r / n_shaft_al) * h_shaft_al)
            # Full Z levels for left abutment
            z_al_full = z_al_sub + z_sup

            # Mesh Left Abutment grid
            for c in range(al_m):
                for r in range(len(z_al_full) - 1):
                    n0 = self._get_or_create_node(x_al_cols[c], y, z_al_full[r])
                    n1 = self._get_or_create_node(x_al_cols[c + 1], y, z_al_full[r])
                    n2 = self._get_or_create_node(x_al_cols[c + 1], y, z_al_full[r + 1])
                    n3 = self._get_or_create_node(x_al_cols[c], y, z_al_full[r + 1])

                    if r < n_fnd_al:
                        mat = spec.left_abutment.foundation_material_key
                        grp = "Abutment_Left_Foundation"
                    elif r < n_fnd_al + n_shaft_al:
                        mat = spec.left_abutment.material_key
                        grp = "Abutment_Left_Shaft"
                    else:
                        mat = spec.left_abutment.material_key
                        grp = "Abutment_Left_Wall"

                    q = self._add_quad(n0, n1, n2, n3, mat, strip_thick, grp)

                    # Boundary restraint on foundation bottom
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

            # B. Intermediate Piers
            for p_idx, pier in enumerate(spec.piers):
                x_p_start, x_p_end, x_p_center = pier_layouts[p_idx]
                p_m = max(2, int(round(pier.thickness / mesh_sz)))
                x_p_cols = [x_p_start + (c / p_m) * pier.thickness for c in range(p_m + 1)]

                h_fnd_p = pier.foundation_height
                h_shaft_p = pier.height
                z_fnd_bot_p = -h_shaft_p - h_fnd_p
                z_shaft_bot_p = -h_shaft_p

                n_fnd_p = max(1, int(round(h_fnd_p / mesh_sz)))
                n_shaft_p = max(2, int(round(h_shaft_p / mesh_sz)))

                z_p_sub: List[float] = []
                for r in range(n_fnd_p):
                    z_p_sub.append(z_fnd_bot_p + (r / n_fnd_p) * h_fnd_p)
                for r in range(n_shaft_p):
                    z_p_sub.append(z_shaft_bot_p + (r / n_shaft_p) * h_shaft_p)
                z_p_full = z_p_sub + z_sup

                for c in range(p_m):
                    for r in range(len(z_p_full) - 1):
                        n0 = self._get_or_create_node(x_p_cols[c], y, z_p_full[r])
                        n1 = self._get_or_create_node(x_p_cols[c + 1], y, z_p_full[r])
                        n2 = self._get_or_create_node(x_p_cols[c + 1], y, z_p_full[r + 1])
                        n3 = self._get_or_create_node(x_p_cols[c], y, z_p_full[r + 1])

                        if r < n_fnd_p:
                            mat = pier.foundation_material_key
                            grp = f"Pier_{p_idx + 1}_Foundation"
                        elif r < n_fnd_p + n_shaft_p:
                            mat = pier.material_key
                            grp = f"Pier_{p_idx + 1}_Shaft"
                        else:
                            mat = pier.material_key
                            grp = f"Pier_{p_idx + 1}_Wall"

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
                                foundation_tag=f"pier_{p_idx + 1}",
                            )
                            self.next_restraint_key += 1
                            self.restraints.append(res)
                            pier_restraints_map[p_idx].append(res.key)

            # C. Right Abutment
            ar_m = max(2, int(round(spec.right_abutment.thickness / mesh_sz)))
            x_ar_cols = [x_ar_start + (c / ar_m) * spec.right_abutment.thickness for c in range(ar_m + 1)]

            h_fnd_ar = spec.right_abutment.foundation_height
            h_shaft_ar = spec.right_abutment.height
            z_fnd_bot_ar = -h_shaft_ar - h_fnd_ar
            z_shaft_bot_ar = -h_shaft_ar

            n_fnd_ar = max(1, int(round(h_fnd_ar / mesh_sz)))
            n_shaft_ar = max(2, int(round(h_shaft_ar / mesh_sz)))

            z_ar_sub: List[float] = []
            for r in range(n_fnd_ar):
                z_ar_sub.append(z_fnd_bot_ar + (r / n_fnd_ar) * h_fnd_ar)
            for r in range(n_shaft_ar):
                z_ar_sub.append(z_shaft_bot_ar + (r / n_shaft_ar) * h_shaft_ar)
            z_ar_full = z_ar_sub + z_sup

            for c in range(ar_m):
                for r in range(len(z_ar_full) - 1):
                    n0 = self._get_or_create_node(x_ar_cols[c], y, z_ar_full[r])
                    n1 = self._get_or_create_node(x_ar_cols[c + 1], y, z_ar_full[r])
                    n2 = self._get_or_create_node(x_ar_cols[c + 1], y, z_ar_full[r + 1])
                    n3 = self._get_or_create_node(x_ar_cols[c], y, z_ar_full[r + 1])

                    if r < n_fnd_ar:
                        mat = spec.right_abutment.foundation_material_key
                        grp = "Abutment_Right_Foundation"
                    elif r < n_fnd_ar + n_shaft_ar:
                        mat = spec.right_abutment.material_key
                        grp = "Abutment_Right_Shaft"
                    else:
                        mat = spec.right_abutment.material_key
                        grp = "Abutment_Right_Wall"

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

            # D. Arch Spans and Spandrels
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

                # Mesh Arch Ring Quads
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

                # Mesh Spandrel Wall Quads above Arch Extrados up to deck
                n_sp_span = max(2, int(round((deck_z - (b + span.thickness_crown)) / mesh_sz)) + 1)
                for s in range(m_span):
                    xe0, ze0 = ext_pts[s]
                    xe1, ze1 = ext_pts[s + 1]

                    # Subdivide vertical column between extrados and deck
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
                            n0, n1, n2, n3, span.material_key, strip_thick, f"Span_{s_idx + 1}_Spandrel"
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
