"""C#-exact pier/abutment transverse discretization.

Ports:

* ``WizardBridge.DiscretizeTopPileb2``
* ``WizardBridge.DiscretizeBottomPileb2``
* ``WizardBridge.DiscretizeBottomFondazionePileb2``

The input list uses the same order as the C# ``WizardBridge.DataList`` after
removing the leading ``BridgeDefinition`` and trailing ``Elevations`` objects:
left abutment, span, pier, span, right abutment, ...
"""
from __future__ import annotations

from typing import List, Sequence

from .csharp_model import Abutment, BridgeElement, Pier, Span


def _span_before(elements: Sequence[object], index: int) -> Span | None:
    if index <= 0:
        return None
    candidate = elements[index - 1]
    return candidate if isinstance(candidate, Span) else None


def _span_after(elements: Sequence[object], index: int) -> Span | None:
    if index + 1 >= len(elements):
        return None
    candidate = elements[index + 1]
    return candidate if isinstance(candidate, Span) else None


def _adjacent_widths(
    elements: Sequence[object], index: int
) -> tuple[float, float, float, float, int, int]:
    """Return ``(s_left, s_right, tb_left, tb_right, discr_right, discr_left)``.

    C# checks ``Adx == 0`` on each adjacent span when deciding whether to
    include its springer thickness, including the span to the right.
    """
    span_left = _span_before(elements, index)
    span_right = _span_after(elements, index)

    s_left = span_left.S2 if span_left is not None else 0.0
    s_right = span_right.S1 if span_right is not None else 0.0
    tb_left = span_left.Tb if span_left is not None and span_left.Adx == 0.0 else 0.0
    tb_right = span_right.Tb if span_right is not None and span_right.Adx == 0.0 else 0.0
    discr_right = max(1, span_left.discr_right) if span_left is not None else 1
    discr_left = max(1, span_right.discr_left) if span_right is not None else 1
    return s_left, s_right, tb_left, tb_right, discr_right, discr_left


def discretize_top_pileb2(elements: Sequence[object], index: int) -> List[float]:
    """Port of ``WizardBridge.DiscretizeTopPileb2``."""
    element = elements[index]
    if not isinstance(element, BridgeElement):
        return []
    s_left, s_right, tb_left, tb_right, discr_right, discr_left = _adjacent_widths(
        elements, index
    )
    widths: List[float] = []
    if s_left > 0.0:
        widths.append(s_left)
    if tb_left > 0.0:
        widths.append(tb_left)

    remainder = element.b2 - (tb_left + tb_right + s_left + s_right)
    if remainder > 0.0:
        if 0 < index < len(elements) - 1:
            widths.extend([remainder / 2.0 / discr_right] * discr_right)
            widths.extend([remainder / 2.0 / discr_left] * discr_left)
        elif index == 0:
            widths.extend([remainder / discr_left] * discr_left)
        else:
            widths.extend([remainder / discr_right] * discr_right)

    if tb_right > 0.0:
        widths.append(tb_right)
    if s_right > 0.0:
        widths.append(s_right)

    start = -element.b2 / 2.0
    coordinates = [start]
    cursor = start
    for width in widths:
        cursor += width
        coordinates.append(cursor)
    return coordinates


def discretize_bottom_pileb2(elements: Sequence[object], index: int) -> List[float]:
    """Port of ``WizardBridge.DiscretizeBottomPileb2``."""
    element = elements[index]
    if not isinstance(element, BridgeElement):
        return []
    s_left, s_right, tb_left, tb_right, discr_right, discr_left = _adjacent_widths(
        elements, index
    )
    widths: List[float] = []
    if s_left > 0.0:
        widths.append(s_left)
    if tb_left > 0.0:
        widths.append(tb_left)

    remainder = element.b2 - (tb_left + tb_right + s_left + s_right)
    if remainder > 0.0:
        if 0 < index < len(elements) - 1:
            widths.extend([remainder / 2.0 / discr_right] * discr_right)
            widths.extend([remainder / 2.0 / discr_left] * discr_left)
        elif index == 0:
            widths.extend([remainder / discr_left] * discr_left)
        else:
            widths.extend([remainder / discr_right] * discr_right)

    if tb_right > 0.0:
        widths.append(tb_right)
    if s_right > 0.0:
        widths.append(s_right)

    start = -element.b1 - element.b2 / 2.0
    b_total = element.b1 + element.b2 + element.b3
    coordinates = [start]
    cursor = start
    for width in widths:
        cursor += width / element.b2 * b_total
        coordinates.append(cursor)
    return coordinates


def discretize_bottom_foundation_pileb2(
    elements: Sequence[object], index: int
) -> List[float]:
    """Port of ``WizardBridge.DiscretizeBottomFondazionePileb2``."""
    element = elements[index]
    if not isinstance(element, BridgeElement):
        return []
    s_left, s_right, tb_left, tb_right, discr_right, discr_left = _adjacent_widths(
        elements, index
    )
    widths: List[float] = []
    if s_left > 0.0:
        widths.append(s_left)
    if tb_left > 0.0:
        widths.append(tb_left)

    remainder = element.b2 - (tb_left + tb_right + s_left + s_right)
    if remainder > 0.0:
        if 0 < index < len(elements) - 1:
            widths.extend([remainder / 2.0 / discr_right] * discr_right)
            widths.extend([remainder / 2.0 / discr_left] * discr_left)
        elif index == 0:
            widths.extend([remainder / discr_left] * discr_left)
        else:
            widths.extend([remainder / discr_right] * discr_right)

    if tb_right > 0.0:
        widths.append(tb_right)
    if s_right > 0.0:
        widths.append(s_right)

    start = -element.B1f - element.b1 - element.b2 / 2.0
    b_total = element.b1 + element.b2 + element.b3
    coordinates: List[float] = []
    cursor = start

    if element.is_reinf_left and element.Hf == 0.0 and element.TreinfBotLeft > 0.0:
        cursor -= element.TreinfBotLeft
        coordinates.append(cursor)
        cursor += element.TreinfBotLeft

    coordinates.append(cursor)
    if element.B1f > 0.0:
        cursor += element.B1f
        coordinates.append(cursor)

    for width in widths:
        cursor += width / element.b2 * b_total
        coordinates.append(cursor)

    if element.B3f > 0.0:
        cursor += element.B3f
        coordinates.append(cursor)

    if element.is_reinf_right and element.Hf == 0.0 and element.TreinfBotRight > 0.0:
        cursor += element.TreinfBotRight
        coordinates.append(cursor)

    return coordinates
