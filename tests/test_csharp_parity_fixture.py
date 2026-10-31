"""Structural fixture for C#-generated mesh parity.

The fixture is a trimmed snapshot of a native HiStrA model produced by the C#
bridge generator.  It deliberately keeps only the structural objects needed
for mesh comparison (nodes used by quads, quads, geometry line restraints and
restraints) so tests do not depend on solver state or generated interfaces.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "model_chain_2span.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_csharp_fixture_has_expected_structural_counts() -> None:
    fixture = load_fixture()
    assert len(fixture["nodes"]) == 222
    assert len(fixture["quads"]) == 156
    assert len(fixture["geometry_line_restraints"]) == 12
    assert len(fixture["restraints"]) == 12


def test_csharp_fixture_is_topologically_consistent() -> None:
    fixture = load_fixture()
    nodes = {int(key) for key in fixture["nodes"]}
    assert len(nodes) == 222

    quad_keys = set()
    for quad in fixture["quads"]:
        key = quad["key"]
        assert key not in quad_keys, f"duplicate quad key {key}"
        quad_keys.add(key)
        assert len(set(quad["nodes"])) == 4, f"quad {key} repeats a node"
        assert set(quad["nodes"]) <= nodes, f"quad {key} references a missing node"

    for glr in fixture["geometry_line_restraints"]:
        assert int(glr["NodeKey1"]) in nodes
        assert int(glr["NodeKey2"]) in nodes

    for restraint in fixture["restraints"]:
        assert int(restraint["NodeKey1"]) in nodes
        assert int(restraint["NodeKey2"]) in nodes


def test_csharp_fixture_has_three_transverse_strips() -> None:
    fixture = load_fixture()
    y_values = {round(fixture["nodes"][str(key)][1], 6) for key in fixture["nodes"]}
    assert y_values == {-100.0, 0.0, 100.0}


def test_csharp_fixture_has_two_spans_and_one_pier() -> None:
    fixture = load_fixture()
    wizard = fixture["wizard"]
    assert [s["L"] for s in wizard["spans"]] == ["450", "450"]
    assert len(wizard["abutments"]) == 2
    assert len(wizard["piers"]) == 1
    assert wizard["piers"][0]["H"] == "200"
