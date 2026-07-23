from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from lxml import etree

EPS = 1e-9


def parse_xml(path_or_bytes: str | Path | bytes) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=False, huge_tree=True, recover=False)
    if isinstance(path_or_bytes, (str, Path)):
        return etree.parse(str(path_or_bytes), parser)
    return etree.ElementTree(etree.fromstring(path_or_bytes, parser))


def direct_children(parent: etree._Element, tag: str | None = None) -> list[etree._Element]:
    children = [child for child in parent if isinstance(child.tag, str)]
    return [child for child in children if child.tag == tag] if tag else children


def first_direct(parent: etree._Element | None, tag: str) -> etree._Element | None:
    if parent is None:
        return None
    for child in parent:
        if child.tag == tag:
            return child
    return None


def clone(element: etree._Element | None, tag: str) -> etree._Element:
    return copy.deepcopy(element) if element is not None else etree.Element(tag)


def clear_children(element: etree._Element) -> None:
    for child in list(element):
        element.remove(child)


def ensure_child(parent: etree._Element, tag: str) -> etree._Element:
    child = first_direct(parent, tag)
    if child is None:
        child = etree.SubElement(parent, tag)
    return child


def set_attributes(element: etree._Element, values: dict[str, object | None]) -> None:
    for key, value in values.items():
        if value is not None:
            element.set(key, str(value))


def parse_vector(raw: str | None, fallback: Sequence[float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not raw:
        return list(fallback)
    values = raw.split(";")
    if len(values) != 3:
        return list(fallback)
    try:
        return [float(value) for value in values]
    except ValueError:
        return list(fallback)


def attr_float(element: etree._Element | None, name: str, fallback: float = 0.0) -> float:
    if element is None:
        return fallback
    raw = element.get(name)
    if raw in (None, ""):
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    return value if math.isfinite(value) else fallback


def attr_text(element: etree._Element | None, name: str, fallback: str = "") -> str:
    if element is None:
        return fallback
    return element.get(name, fallback)


def attr_bool(element: etree._Element | None, name: str, fallback: bool = False) -> bool:
    raw = attr_text(element, name, "").strip().lower()
    return fallback if not raw else raw in {"true", "1", "yes"}


def fmt(value: float | int) -> str:
    number = float(value)
    if not math.isfinite(number) or abs(number) < 1e-12:
        return "0"
    return f"{number:.15g}"


def vec_text(vector: Sequence[float]) -> str:
    return ";".join(fmt(value) for value in vector)


def sorted_unique(values: Iterable[float], tolerance: float = EPS) -> list[float]:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    result: list[float] = []
    for value in ordered:
        if not result or abs(value - result[-1]) > tolerance:
            result.append(value)
    return result


def reference_system(axes: Sequence[Sequence[float]], origin: Sequence[float]) -> etree._Element:
    element = etree.Element("ReferenceSystem")
    set_attributes(
        element,
        {"E1": vec_text(axes[0]), "E2": vec_text(axes[1]), "E3": vec_text(axes[2]), "Origin": vec_text(origin)},
    )
    return element


def serialize(tree_or_root: etree._ElementTree | etree._Element) -> bytes:
    root = tree_or_root.getroot() if isinstance(tree_or_root, etree._ElementTree) else tree_or_root
    return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=False)
