"""C#-parity native portfolio and concrete scour interface tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lxml import etree

from histra_builder.native_portfolio import (
    ANALYSIS_SEQUENCE,
    SCOUR_MATERIAL_KEY,
    generate_native_jobs,
)

pytest.importorskip("histra", reason="install histra-python to run the solver integration tests")

from histra.io.hr_loader import load_model
from histra.preprocessing.prepare_model import prepare_model


def _documents(paths: list[Path]) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def test_native_portfolio_generates_runnable_jobs(tmp_path: Path) -> None:
    paths = generate_native_jobs(output_dir=tmp_path, count=2, base_seed=4242)
    assert len(paths) == 2
    documents = _documents(paths)
    for document in documents:
        assert [item for item in document["workflow"]["analyses"]] == list(ANALYSIS_SEQUENCE)
        mutations = document["workflow"]["interface_mutations"]
        assert set(mutations) == {"Scour_1", "Scour_2"}
        for stage in ("Scour_1", "Scour_2"):
            assert len(mutations[stage]) == 1
            spec = mutations[stage][0]
            assert spec["material_key"] == SCOUR_MATERIAL_KEY
            assert spec["preserve_committed_state"] is True
            assert spec["interface_keys"]
            assert len(spec["interface_keys"]) == len(set(spec["interface_keys"]))
        assert document["metadata"]["portfolio"] == "native-csharp-parity"
        assert document["metadata"]["parameters"]["num_spans"] in (2, 3)


def test_native_portfolio_templates_are_native_and_prepare(tmp_path: Path) -> None:
    paths = generate_native_jobs(output_dir=tmp_path, count=1, base_seed=99)
    document = json.loads(paths[0].read_text(encoding="utf-8"))
    template = tmp_path / "templates" / f"{document['model']['template']['id']}.hrx"
    assert template.is_file()
    root = etree.fromstring(template.read_bytes())
    assert root.find("Bridge") is not None
    assert len(root.findall("GeometryLineRestraint")) > 0
    assert len(root.findall("Quad")) > 0

    model = load_model(template)
    prepare_model(model, force=True)
    expected = set(
        document["workflow"]["interface_mutations"]["Scour_1"][0]["interface_keys"]
    )
    assert expected <= set(model.collections.interfaces)


def test_native_portfolio_is_reproducible(tmp_path: Path) -> None:
    first = generate_native_jobs(output_dir=tmp_path / "a", count=2, base_seed=777)
    second = generate_native_jobs(output_dir=tmp_path / "b", count=2, base_seed=777)
    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
    other = generate_native_jobs(output_dir=tmp_path / "c", count=2, base_seed=778)
    assert [path.read_bytes() for path in other] != [path.read_bytes() for path in first]
