"""Random five-JOB scour workflow generation against the real ``model.hrx``."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from lxml import etree

from histra_builder import (
    InvalidHrxError,
    JobSpec,
    ScenarioError,
    TemplateRegistry,
    compile_job,
    inspect_hrx,
    job_from_hrx,
)
from histra_builder.scenarios import (
    ANALYSIS_SEQUENCE,
    SCOUR_FOUNDATION,
    find_piers,
    generate_random_jobs,
    resolve_foundation,
    validate_parameters,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = REPO_ROOT / "model.hrx"


@pytest.fixture(scope="module")
def model_bytes() -> bytes:
    return MODEL.read_bytes()


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> list[Path]:
    """One full default run (five jobs), shared by the broad assertions."""
    output = tmp_path_factory.mktemp("generated_jobs")
    return generate_random_jobs(MODEL, output_dir=output)


def test_reference_model_imports(model_bytes: bytes, tmp_path: Path) -> None:
    inspection = inspect_hrx(model_bytes)
    assert inspection.counts["nodes"] > 0
    assert inspection.counts["quads"] > 0
    assert inspection.validation["valid"] is True
    registry = TemplateRegistry(tmp_path / "templates")
    job = job_from_hrx(model_bytes, job_id="model", template_id="model", registry=registry)
    assert compile_job(job, registry).hrx_bytes == model_bytes


def test_model_has_two_piers(model_bytes: bytes) -> None:
    piers = find_piers(model_bytes)
    assert [pier["id"] for pier in piers] == ["pier_1", "pier_2"]
    assert piers[0]["origin"] == "502;0;0"
    resolve_foundation(piers, "pier_1")
    with pytest.raises(ScenarioError, match="pier_99"):
        resolve_foundation(piers, "pier_99")


def test_generates_exactly_five_jobs(generated: list[Path]) -> None:
    assert len(generated) == 5
    for index, path in enumerate(generated, start=1):
        assert path == path.parent.parent / f"random_{index:03d}" / "job.json"
        assert path.is_file()


def test_analysis_sequence_in_every_job(generated: list[Path]) -> None:
    for path in generated:
        document = json.loads(path.read_text(encoding="utf-8"))
        names = [analysis["name"] for analysis in document["workflow"]["analyses"]]
        assert names == list(ANALYSIS_SEQUENCE)


def test_scour_1_targets_pier_1_at_0_2(generated: list[Path]) -> None:
    for path in generated:
        analyses = json.loads(path.read_text(encoding="utf-8"))["workflow"]["analyses"]
        scour_1 = next(item for item in analyses if item["name"] == "Scour_1")
        assert scour_1["interface_changes"] == [{"foundation": SCOUR_FOUNDATION, "fraction": 0.2}]


def test_scour_2_targets_pier_1_at_0_4(generated: list[Path]) -> None:
    for path in generated:
        analyses = json.loads(path.read_text(encoding="utf-8"))["workflow"]["analyses"]
        scour_2 = next(item for item in analyses if item["name"] == "Scour_2")
        assert scour_2["interface_changes"] == [{"foundation": SCOUR_FOUNDATION, "fraction": 0.4}]


def test_scour_levels_are_absolute_states(generated: list[Path]) -> None:
    for path in generated:
        workflow = json.loads(path.read_text(encoding="utf-8"))["workflow"]
        assert workflow["scour"] == {
            "foundation": "pier_1",
            "fractions": {"Scour_1": 0.2, "Scour_2": 0.4},
            "cumulative": False,
        }


def test_jobs_differ_in_random_parameters(generated: list[Path]) -> None:
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in generated]
    signatures = {
        tuple(sorted(document["metadata"]["random_parameters"].items())) for document in documents
    }
    assert len(signatures) > 1
    assert len({json.dumps(document["model"]["patches"], sort_keys=True) for document in documents}) > 1


def test_reproducible_with_fixed_seed(model_bytes: bytes, tmp_path: Path) -> None:
    first = generate_random_jobs(MODEL, output_dir=tmp_path / "a", base_seed=1234)
    second = generate_random_jobs(MODEL, output_dir=tmp_path / "b", base_seed=1234)
    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
    other = generate_random_jobs(MODEL, output_dir=tmp_path / "c", base_seed=5678)
    assert [path.read_bytes() for path in other] != [path.read_bytes() for path in first]


def test_job_metadata_identifies_workflow_test(generated: list[Path]) -> None:
    for path in generated:
        metadata = json.loads(path.read_text(encoding="utf-8"))["metadata"]
        assert metadata["workflow_test"] == "random-five-scour-workflow"
        assert metadata["seed"]["base"] == 20260817
        assert metadata["seed"]["job"].startswith("20260817:")
        assert metadata["template_source"] == "model.hrx"
        assert metadata["analysis_sequence"] == list(ANALYSIS_SEQUENCE)
        assert metadata["scour"]["foundation"] == "pier_1"
        assert metadata["scour"]["levels"] == {"Scour_1": 0.2, "Scour_2": 0.4}


def test_serialization_round_trip(generated: list[Path]) -> None:
    for path in generated:
        raw = json.loads(path.read_text(encoding="utf-8"))
        restored = JobSpec.model_validate(raw)
        assert restored.model_dump(mode="json") == raw


def test_compiled_hrx_round_trip(generated: list[Path], model_bytes: bytes) -> None:
    registry = TemplateRegistry(generated[0].parents[1] / "templates")
    for path in generated:
        job = JobSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
        artifact = compile_job(job, registry)
        compiled = inspect_hrx(artifact.hrx_bytes)
        assert compiled.counts == {"nodes": 3216, "quads": 2520}
        assert compiled.validation["valid"] is True
        root = etree.fromstring(artifact.hrx_bytes)
        selected = job.metadata["random_parameters"]
        pier_h = {element.get("H") for element in root.xpath("/HiStrA/WizardData/Pier")}
        assert pier_h == {str(selected["pier_height"])}


def test_missing_model_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="reference model not found"):
        generate_random_jobs(tmp_path / "nope.hrx", output_dir=tmp_path / "out")


def test_malformed_model_fails_clearly(tmp_path: Path) -> None:
    broken = tmp_path / "broken.hrx"
    broken.write_bytes(b"<HiStrA><WizardData>")
    with pytest.raises(InvalidHrxError):
        generate_random_jobs(broken, output_dir=tmp_path / "out")
    empty = tmp_path / "empty.hrx"
    empty.write_bytes(b"")
    with pytest.raises(InvalidHrxError, match="empty"):
        generate_random_jobs(empty, output_dir=tmp_path / "out")


def test_model_without_requested_pier_fails(model_bytes: bytes, tmp_path: Path) -> None:
    pierless = tmp_path / "pierless.hrx"
    pierless.write_bytes(b'<HiStrA version="2025.1.6"><WizardData /></HiStrA>')
    with pytest.raises(ScenarioError, match="pier_1.*does not exist"):
        generate_random_jobs(pierless, output_dir=tmp_path / "out")
    with pytest.raises(ScenarioError, match="pier_99.*does not exist"):
        generate_random_jobs(MODEL, output_dir=tmp_path / "out", foundation="pier_99")


def test_invalid_parameter_combinations_rejected() -> None:
    with pytest.raises(ScenarioError, match="outside valid range"):
        validate_parameters({
            "pier_height": 500.0,
            "foundation_height": 60.0,
            "foundation_width": 50.0,
            "foundation_length": 25.0,
            "subgrade_modulus": 0.1,
        })
    with pytest.raises(ScenarioError, match="below pier height"):
        validate_parameters({
            "pier_height": 85.0,
            "foundation_height": 90.0,
            "foundation_width": 50.0,
            "foundation_length": 25.0,
            "subgrade_modulus": 0.1,
        })
    with pytest.raises(ScenarioError, match="not a finite number"):
        validate_parameters({
            "pier_height": None,
            "foundation_height": 60.0,
            "foundation_width": 50.0,
            "foundation_length": 25.0,
            "subgrade_modulus": 0.1,
        })
