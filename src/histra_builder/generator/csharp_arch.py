"""C#-equivalent elliptical arch geometry.

This module is a direct port of the C# routines used by ``BridgeMesher``:

* ``Operations.GetParamsArchEllipse``
* ``Operations.GetIntradossoArchEllipse``
* ``Operations.GetThickness``
* ``Operations.GetPointsInEllipseEquiSpaced``
* ``Operations.LArcoEllisse``

The C# implementation operates on ``Microsoft.Xna.Framework.Vector3`` (32-bit
floats).  We keep Python doubles here and compare against native float32
coordinates with a small tolerance; topology and formulas are identical.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Sequence, Tuple

Point = Tuple[float, float, float]

_MESHER_ANGULAR_TOLL = 1.0e-4
_ARC_BISECTION_TOL = 1.0e-5

# Six-point Gauss-Legendre abscissae/weights used by C#
# ``Operations.LArcoEllisse``.
_GAUSS_X = (0.9324695, 0.6612094, 0.2386192, -0.2386192, -0.6612094, -0.9324695)
_GAUSS_W = (0.17132449, 0.36076158, 0.46791393, 0.46791393, 0.36076158, 0.17132449)


@dataclass(frozen=True)
class EllipseParams:
    """Extrados ellipse returned by ``GetParamsArchEllipse``."""

    center: Point
    rx: float
    rz: float
    theta0: float
    intrados_rx: float
    intrados_rz: float
    springing_drop: float
    crown_point: Point


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v: Sequence[float]) -> float:
    return math.sqrt(_dot(v, v))


def _normalize(v: Sequence[float], default: Point = (1.0, 0.0, 0.0)) -> Point:
    n = _norm(v)
    if n < 1.0e-15:
        return default
    return (v[0] / n, v[1] / n, v[2] / n)


def _add(a: Sequence[float], b: Sequence[float]) -> Point:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Sequence[float], b: Sequence[float]) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Sequence[float], s: float) -> Point:
    return (a[0] * s, a[1] * s, a[2] * s)


def get_normal_ellipse(rx: float, rz: float, x: float, z: float) -> Point:
    """Port of ``Operations.GetNormalEllipse``."""
    return _normalize((x / (rx * rx), 0.0, z / (rz * rz)))


def l_arco_ellisse(theta1: float, theta2: float, rx: float, rz: float) -> float:
    """Port of ``Operations.LArcoEllisse`` (6-point Gauss-Legendre)."""
    total = 0.0
    for xi, wi in zip(_GAUSS_X, _GAUSS_W):
        theta = theta1 * (1.0 - xi) / 2.0 + theta2 * (1.0 + xi) / 2.0
        total += (theta2 - theta1) / 2.0 * wi * math.hypot(
            rx * math.sin(theta), rz * math.cos(theta)
        )
    return total


def _angle_with_horizontal(normal: Sequence[float]) -> float:
    """C# ``GetThickness`` measures the angle against the horizontal projection."""
    horizontal = (normal[0], 0.0, 0.0)
    n = _norm(horizontal)
    if n < 1.0e-15:
        # Degenerate normal; C# would divide by zero.  Treat as vertical.
        return math.pi / 2.0
    horizontal = _normalize(horizontal)
    cosine = max(-1.0, min(1.0, _dot(normal, horizontal)))
    return math.acos(cosine)


def get_thickness(
    thickness0: float,
    thickness1: float,
    normal0: Sequence[float],
    normal1: Sequence[float],
    normal: Sequence[float],
    law: str = "Linear",
) -> float:
    """Port of ``Operations.GetThickness`` for Constant/Linear laws."""
    if _norm(_sub(normal, normal1)) < 1.0e-5:
        return thickness1
    if _norm(_sub(normal, (0.0, 0.0, 1.0))) < 1.0e-15:
        return thickness0 if law == "Constant" else thickness1

    angle = _angle_with_horizontal(normal)
    angle0 = _angle_with_horizontal(normal0)
    angle1 = _angle_with_horizontal(normal1)
    if law == "Constant":
        return thickness0
    if abs(angle1 - angle0) < 1.0e-15:
        return thickness0
    return (thickness1 - thickness0) / (angle1 - angle0) * (angle - angle0) + thickness0


def get_intradosso_arch_ellipse(
    p: Sequence[float],
    center: Sequence[float],
    rx_ext: float,
    rz_ext: float,
    thick_base: float,
    thick_key: float,
    theta0: float,
) -> Point:
    """Port of ``Operations.GetIntradossoArchEllipse``."""
    relative = _sub(p, center)
    normal = get_normal_ellipse(rx_ext, rz_ext, relative[0], relative[2])
    key_point = (
        math.cos(theta0) * rx_ext,
        0.0,
        math.sin(theta0) * rz_ext,
    )
    key_normal = get_normal_ellipse(rx_ext, rz_ext, key_point[0], key_point[2])
    thickness = get_thickness(
        thick_base,
        thick_key,
        key_normal,
        (0.0, 0.0, 1.0),
        normal,
        "Linear",
    )
    return _sub(p, _mul(normal, thickness))


def get_params_arch_ellipse(
    x1: float,
    x2: float,
    f: float,
    length: float,
    s1: float,
    s2: float,
    tb: float,
    tt: float,
    alfa_degrees: float,
    dz: float,
) -> EllipseParams:
    """Port of ``Operations.GetParamsArchEllipse``.

    Note: the C# routine contains ``if (0 % 2 == 0)``, which is always true, so
    the ``X2`` branch is always used.  The port preserves that behaviour.
    """
    num = float(f)
    num2 = float(length) / 2.0
    num3 = float(f)
    alfa = math.radians(float(alfa_degrees))
    num4 = 0.0
    num5 = 2.0 * num2 + s1 + s2

    if alfa > _MESHER_ANGULAR_TOLL:
        num6 = math.atan(num5 / (2.0 * num3)) * 0.999
        if alfa > num6:
            alfa = num6
        num = (num5 - num3 * math.tan(alfa)) / (num5 - 2.0 * num3 * math.tan(alfa)) * num3
        num4 = num - num3
        num2 = math.sqrt(num5 * num * num * math.tan(alfa) / (2.0 * num4))
    else:
        alfa = 0.0

    if dz > 0.0:
        num4 += dz

    # C#: if (0 % 2 == 0) -> X2 branch.
    x2 = x2 + (s2 - s1) / 2.0
    vector = (x2, 0.0, -num4)

    ratio = num5 / 2.0 / num2
    if ratio > 1.0:
        ratio = 1.0
    theta0 = math.acos(ratio)

    vector2 = (num2 * math.cos(theta0), 0.0, num * math.sin(theta0))
    vector3 = _normalize(
        (vector2[0] / (num2 * num2), 0.0, vector2[2] / (num * num))
    )
    vector2 = _add(vector2, _mul(vector3, tb))

    vector4 = (0.0, 0.0, f + tt - vector[2])
    num8 = math.sqrt(
        max(0.0, (vector2[0] * vector4[2]) ** 2 - (vector4[0] * vector2[2]) ** 2)
    )
    rx_ext = num8 / math.sqrt(max(1.0e-30, vector4[2] ** 2 - vector2[2] ** 2))
    rz_ext = num8 / math.sqrt(max(1.0e-30, vector2[0] ** 2 - vector4[0] ** 2))

    vector4 = _add(vector4, vector)
    center = (vector4[0], vector4[1], vector4[2] - rz_ext)
    theta0 = math.acos(max(-1.0, min(1.0, vector2[0] / rx_ext)))
    return EllipseParams(
        center=center,
        rx=rx_ext,
        rz=rz_ext,
        theta0=theta0,
        intrados_rx=num2,
        intrados_rz=num,
        springing_drop=num4,
        crown_point=vector4,
    )


def get_points_in_ellipse_equi_spaced(
    p1: Sequence[float],
    p2: Sequence[float],
    rx: float,
    rz: float,
    origin: Sequence[float],
    lmax: float,
) -> List[Point]:
    """Port of ``Operations.GetPointsInEllipseEquiSpaced(p1, p2, ...)``."""
    if lmax <= 0.0:
        raise ValueError("lmax must be positive")

    t1 = math.acos(max(-1.0, min(1.0, (p1[0] - origin[0]) / rx)))
    t2 = math.acos(max(-1.0, min(1.0, (p2[0] - origin[0]) / rx)))
    reverse = t1 > t2
    t_min, t_max = (t2, t1) if reverse else (t1, t2)

    arc = l_arco_ellisse(t_min, t_max, rx, rz)
    count = max(1, int(round(abs(arc) / lmax)))
    step = arc / count

    points: List[Point] = []
    for index in range(count + 1):
        if index == 0:
            theta = t_min
        elif index == count:
            theta = t_max
        else:
            target = index * step
            lo, hi = t_min, t_max
            theta = (lo + hi) / 2.0
            for _ in range(100):
                value = target - l_arco_ellisse(t_min, theta, rx, rz)
                value_lo = target - l_arco_ellisse(t_min, lo, rx, rz)
                value_hi = target - l_arco_ellisse(t_min, hi, rx, rz)
                if hi - lo < _ARC_BISECTION_TOL:
                    break
                if value * value_hi <= 0.0:
                    lo = theta
                elif value * value_lo <= 0.0:
                    hi = theta
                else:
                    break
                theta = (lo + hi) / 2.0
        points.append(
            (
                origin[0] + rx * math.cos(theta),
                origin[1],
                origin[2] + rz * math.sin(theta),
            )
        )

    if reverse:
        points.reverse()
    points[0] = (float(p1[0]), float(p1[1]), float(p1[2]))
    points[-1] = (float(p2[0]), float(p2[1]), float(p2[2]))
    return points


def half_arch_params(
    x2: float,
    f: float,
    length: float,
    tb: float,
    tt: float,
    alfa_degrees: float,
    s1: float = 0.0,
    s2: float = 0.0,
    dz: float = 0.0,
) -> EllipseParams:
    """Port of the inline half-arch parameter block in ``AddBridgeRow1``.

    This is the block that actually feeds ``AddSemiArcoSx1``/``Dx1``.  It differs
    slightly from ``GetParamsArchEllipse`` and is the one required for native
    mesh parity.
    """
    num4 = float(length) + s1 + s2
    num5 = float(f)
    num6 = num4 / 2.0
    num7 = float(f)
    alfa = math.radians(float(alfa_degrees))
    num9 = 0.0

    if alfa > _MESHER_ANGULAR_TOLL:
        num10 = math.atan(num4 / (2.0 * num7)) * 0.999
        if alfa > num10:
            alfa = num10
        num5 = (num4 - 2.0 * num7 * math.tan(alfa)) / (
            num4 - 4.0 * num7 * math.tan(alfa)
        ) * num7
        num9 = num5 - num7
        num6 = math.sqrt(num4 * num5 * num5 * math.tan(alfa) / (2.0 * num9))
    else:
        alfa = 0.0

    if dz > 0.0:
        num9 += dz

    x2 = x2 + (s2 - s1) / 2.0
    vector = (x2, 0.0, -num9)

    ratio = num4 / 2.0 / num6
    ratio = min(1.0, ratio)
    theta = math.acos(ratio)
    vector2 = (num6 * math.cos(theta), 0.0, num5 * math.sin(theta))
    vector3 = _normalize(
        (vector2[0] / (num6 * num6), 0.0, vector2[2] / (num5 * num5))
    )
    vector2 = _add(vector2, _mul(vector3, tb))

    vector4 = (0.0, 0.0, f + tt - vector[2])
    num12 = math.sqrt(
        max(0.0, (vector2[0] * vector4[2]) ** 2 - (vector4[0] * vector2[2]) ** 2)
    )
    rx_ext = num12 / math.sqrt(max(1.0e-30, vector4[2] ** 2 - vector2[2] ** 2))
    rz_ext = num12 / math.sqrt(max(1.0e-30, vector2[0] ** 2 - vector4[0] ** 2))

    vector4 = _add(vector4, vector)
    center = (vector4[0], vector4[1], vector4[2] - rz_ext)
    theta = math.acos(max(-1.0, min(1.0, vector2[0] / rx_ext)))
    return EllipseParams(
        center=center,
        rx=rx_ext,
        rz=rz_ext,
        theta0=theta,
        intrados_rx=num6,
        intrados_rz=num5,
        springing_drop=num9,
        crown_point=vector4,
    )
