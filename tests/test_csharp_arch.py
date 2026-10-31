"""C# arch-math parity tests against the native two-span fixture."""
from __future__ import annotations

import math

import pytest

from histra_builder.generator.csharp_arch import (
    get_intradosso_arch_ellipse,
    get_normal_ellipse,
    get_params_arch_ellipse,
    get_points_in_ellipse_equi_spaced,
    get_thickness,
    half_arch_params,
    l_arco_ellisse,
)

# Native C# points from tests/fixtures/csharp/model_chain_2span.json,
# span 1 left half (Abutment A -> midspan).
EXPECTED_EXTRADOS = (
    (22.8000335693359, 0.0, 12.9000434875488),
    (93.5549240112305, 0.0, 63.6509704589844),
    (177.564819335938, 0.0, 88.7811889648438),
    (265.0, 0.0, 96.4999923706055),
)
EXPECTED_INTRADOS = (
    (40.0, 0.0, 0.0),
    (102.302963256836, 0.0, 44.0111618041992),
    (181.413681030273, 0.0, 67.6285018920898),
    (265.0, 0.0, 74.9999923706055),
)


def test_half_arch_parameters_match_csharp_span1() -> None:
    params = half_arch_params(
        x2=265.0,
        f=75.0,
        length=450.0,
        tb=21.5,
        tt=21.5,
        alfa_degrees=36.8699,
    )
    assert params.center[0] == pytest.approx(265.0, abs=1e-6)
    assert params.center[2] == pytest.approx(-37.5, abs=1e-4)
    assert params.rx == pytest.approx(261.3938, abs=1e-3)
    assert params.rz == pytest.approx(134.0, abs=1e-3)
    assert params.theta0 == pytest.approx(0.3856, abs=1e-4)


def test_extrados_equi_spaced_points_match_csharp() -> None:
    params = half_arch_params(265.0, 75.0, 450.0, 21.5, 21.5, 36.8699)
    points = get_points_in_ellipse_equi_spaced(
        EXPECTED_EXTRADOS[0],
        EXPECTED_EXTRADOS[-1],
        params.rx,
        params.rz,
        params.center,
        100.0,
    )
    assert len(points) == len(EXPECTED_EXTRADOS)
    for actual, expected in zip(points, EXPECTED_EXTRADOS):
        assert actual[0] == pytest.approx(expected[0], abs=5e-4)
        assert actual[2] == pytest.approx(expected[2], abs=5e-4)


def test_intrados_offsets_match_csharp_after_springing_override() -> None:
    params = half_arch_params(265.0, 75.0, 450.0, 21.5, 21.5, 36.8699)
    for index, extrados in enumerate(EXPECTED_EXTRADOS):
        intrados = get_intradosso_arch_ellipse(
            extrados,
            params.center,
            params.rx,
            params.rz,
            21.5,
            21.5,
            params.theta0,
        )
        expected = EXPECTED_INTRADOS[index]
        if index == 0:
            # AddMeshArco1 forces the first intrados node to the exact
            # springing coordinate; that override belongs to the mesher.
            continue
        assert intrados[0] == pytest.approx(expected[0], abs=2e-3)
        assert intrados[2] == pytest.approx(expected[2], abs=2e-3)


def test_ellipse_arc_length_is_positive_and_monotonic() -> None:
    a = l_arco_ellisse(math.pi / 2.0, math.pi, 261.3938, 134.0)
    b = l_arco_ellisse(math.pi / 2.0, math.pi * 0.75, 261.3938, 134.0)
    assert a > b > 0.0


def test_constant_thickness_returns_springing_value() -> None:
    normal = get_normal_ellipse(261.3938, 134.0, 0.0, 134.0)
    key_normal = get_normal_ellipse(261.3938, 134.0, 242.2, 50.4)
    assert get_thickness(21.5, 21.5, key_normal, (0.0, 0.0, 1.0), normal) == pytest.approx(
        21.5
    )


def test_get_params_arch_ellipse_returns_consistent_crown() -> None:
    params = get_params_arch_ellipse(
        x1=0.0,
        x2=265.0,
        f=75.0,
        length=450.0,
        s1=0.0,
        s2=0.0,
        tb=21.5,
        tt=21.5,
        alfa_degrees=36.8699,
        dz=0.0,
    )
    assert params.rx > 0.0
    assert params.rz > 0.0
    assert params.crown_point[2] == pytest.approx(96.5, abs=1e-9)
