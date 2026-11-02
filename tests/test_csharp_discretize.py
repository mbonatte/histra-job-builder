"""C#-parity tests for pier/abutment transverse discretization."""
from __future__ import annotations

from histra_builder.generator.csharp_discretize import (
    discretize_bottom_foundation_pileb2,
    discretize_bottom_pileb2,
    discretize_top_pileb2,
)
from histra_builder.generator.csharp_model import Abutment, Pier, Span


def _model_chain_elements():
    left = Abutment(b2=40.0, H=0.0, kind="Sinistra")
    right = Abutment(b2=40.0, H=0.0, kind="Destra")
    pier = Pier(b2=50.0, H=200.0)
    span1 = Span(L=450.0, W=300.0, f=75.0, Asx=36.8699, Adx=36.8699, Tb=21.5)
    span2 = Span(L=450.0, W=300.0, f=75.0, Asx=36.8699, Adx=36.8699, Tb=21.5)
    return [left, span1, pier, span2, right]


def test_model_chain_pier_discretization_matches_native_columns() -> None:
    elements = _model_chain_elements()
    assert discretize_top_pileb2(elements, 2) == [-25.0, 0.0, 25.0]
    assert discretize_bottom_pileb2(elements, 2) == [-25.0, 0.0, 25.0]
    assert discretize_bottom_foundation_pileb2(elements, 2) == [-25.0, 0.0, 25.0]


def test_model_chain_abutment_discretization_matches_native_columns() -> None:
    elements = _model_chain_elements()
    assert discretize_top_pileb2(elements, 0) == [-20.0, 20.0]
    assert discretize_bottom_pileb2(elements, 0) == [-20.0, 20.0]
    assert discretize_bottom_foundation_pileb2(elements, 0) == [-20.0, 20.0]
    assert discretize_top_pileb2(elements, 4) == [-20.0, 20.0]


def test_zero_springing_angle_adds_springer_and_springing_offsets() -> None:
    elements = [
        Abutment(b2=100.0, H=0.0, kind="Sinistra"),
        Span(L=400.0, W=200.0, f=100.0, Asx=0.0, Adx=0.0, Tb=21.0, S1=4.0, S2=6.0),
        Pier(b2=80.0, H=100.0),
        Span(L=400.0, W=200.0, f=100.0, Asx=0.0, Adx=0.0, Tb=21.0, S1=3.0, S2=5.0),
        Abutment(b2=100.0, H=0.0, kind="Destra"),
    ]
    # Pier index 2: left span S2/Tb then split remainder, then right span Tb/S1.
    assert discretize_top_pileb2(elements, 2) == [-40.0, -34.0, -13.0, 1.5, 16.0, 37.0, 40.0]
    # The same segment lengths are scaled by B/b2 for the bottom.
    assert discretize_bottom_pileb2(elements, 2) == [-40.0, -34.0, -13.0, 1.5, 16.0, 37.0, 40.0]


def test_foundation_wings_and_reinforcement_extend_the_bottom_outline() -> None:
    element = Pier(
        b1=5.0,
        b2=50.0,
        b3=7.0,
        B1f=10.0,
        B3f=12.0,
        Hf=60.0,
        is_reinf_left=True,
        is_reinf_right=True,
        TreinfBotLeft=4.0,
        TreinfBotRight=6.0,
    )
    elements = [
        Abutment(b2=40.0),
        Span(L=450.0, W=300.0, f=75.0, Tb=0.0, Asx=0.0, Adx=0.0),
        element,
        Abutment(b2=40.0, kind="Destra"),
    ]
    # Reinforcement extensions are only included when Hf == 0; with a
    # foundation they are omitted and the B1f/B3f wings are added.
    assert discretize_bottom_foundation_pileb2(elements, 2) == [-40.0, -30.0, 1.0, 32.0, 44.0]


def test_right_adjacent_span_uses_adx_for_springer_in_all_three_paths() -> None:
    abutment = Abutment(b2=100.0)
    span = Span(L=400.0, W=200.0, f=100.0, Asx=25.0, Adx=0.0, Tb=20.0)
    elements = [abutment, span, Abutment(b2=100.0, kind="Destra")]
    for discretize in (discretize_top_pileb2, discretize_bottom_pileb2,
                       discretize_bottom_foundation_pileb2):
        assert discretize(elements, 0) == [-50.0, 30.0, 50.0]
        span.Asx, span.Adx = 0.0, 25.0
        assert discretize(elements, 0) == [-50.0, 50.0]
        span.Asx, span.Adx = 25.0, 0.0
