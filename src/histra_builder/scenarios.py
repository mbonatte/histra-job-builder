"""Random scour-scenario JOB generation on top of a reference HRX model.

The generated JOBs describe engineering intent only: the analysis sequence
(``Vert`` -> ``Scour_1`` -> ``Scour_2``) and the semantic interface changes
(foundation ``pier_1`` scoured to an absolute fraction of 0.2 and 0.4).
Pier 1 is never resolved into concrete HRX interface IDs here; the Runner
and solver adapters interpret the semantic definition later, using the
imported template preserved by the Builder.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree

from .compiler import compile_job
from .errors import InvalidHrxError, ScenarioError
from .importer import job_from_hrx
from .inspector import inspect_hrx
from .models import JobSpec
from .templates import TemplateRegistry

WORKFLOW_TEST_ID = "random-five-scour-workflow"
ANALYSIS_SEQUENCE: tuple[str, ...] = ("Vert", "Scour_1", "Scour_2")
SCOUR_FOUNDATION = "pier_1"
SCOUR_FRACTIONS: dict[str, float] = {"Scour_1": 0.2, "Scour_2": 0.4}
DEFAULT_JOB_COUNT = 5
DEFAULT_BASE_SEED = 20260817

_PIER_XPATH = "/HiStrA/WizardData/Pier"


@dataclass(frozen=True)
class RandomParameter:
    """A WizardData attribute that may be randomised within safe bounds."""

    name: str
    description: str
    xpath: str
    attributes: tuple[str, ...]
    minimum: float
    maximum: float
    decimals: int = 1


RANDOM_PARAMETERS: tuple[RandomParameter, ...] = (
    RandomParameter(
        "pier_height",
        "Pier shaft height H (cm)",
        _PIER_XPATH,
        ("H",),
        80.0,
        200.0,
    ),
    RandomParameter(
        "foundation_height",
        "Pier foundation height Hf (cm)",
        _PIER_XPATH,
        ("Hf",),
        50.0,
        100.0,
    ),
    RandomParameter(
        "foundation_width",
        "Pier foundation transverse size B1f=B3f (cm)",
        _PIER_XPATH,
        ("B1f", "B3f"),
        45.0,
        60.0,
    ),
    RandomParameter(
        "foundation_length",
        "Pier foundation longitudinal size W1f=W3f (cm)",
        _PIER_XPATH,
        ("W1f", "W3f"),
        20.0,
        35.0,
    ),
    RandomParameter(
        "subgrade_modulus",
        "Foundation subgrade reaction modulus Kz",
        _PIER_XPATH,
        ("Kz",),
        0.05,
        0.30,
        decimals=3,
    ),
)


def find_piers(hrx_bytes: bytes) -> list[dict[str, Any]]:
    """Return the pier inventory of an HRX model, numbered by document order.

    Pier ``pier_1`` is the first ``WizardData/Pier`` element; the recorded
    origin keeps the semantic identity stable for the Runner without leaking
    concrete interface IDs into the canonical JOB.
    """
    if not hrx_bytes:
        raise InvalidHrxError("HRX input is empty")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    try:
        root = etree.fromstring(hrx_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise InvalidHrxError(f"HRX is not valid XML: {exc}") from exc
    piers: list[dict[str, Any]] = []
    for index, element in enumerate(root.xpath("WizardData/Pier"), start=1):
        reference = element.find("ReferenceSystem")
        piers.append({
            "id": f"pier_{index}",
            "origin": reference.get("Origin") if reference is not None else None,
        })
    return piers


def resolve_foundation(piers: list[dict[str, Any]], foundation: str) -> dict[str, Any]:
    for pier in piers:
        if pier["id"] == foundation:
            return pier
    available = [pier["id"] for pier in piers] or "none"
    raise ScenarioError(
        f"foundation {foundation!r} does not exist in the imported model (available piers: {available})"
    )


def sample_parameters(rng: random.Random) -> dict[str, float]:
    values: dict[str, float] = {}
    for parameter in RANDOM_PARAMETERS:
        maximum = parameter.maximum
        if parameter.name == "foundation_height":
            # Keep the foundation strictly shorter than the pier shaft.
            maximum = min(maximum, values["pier_height"] - 10.0)
        values[parameter.name] = round(rng.uniform(parameter.minimum, maximum), parameter.decimals)
    return values


def validate_parameters(values: dict[str, float]) -> None:
    for parameter in RANDOM_PARAMETERS:
        value = values.get(parameter.name)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ScenarioError(f"random parameter {parameter.name!r} is not a finite number: {value!r}")
        if not parameter.minimum <= value <= parameter.maximum:
            raise ScenarioError(
                f"random parameter {parameter.name!r} outside valid range "
                f"[{parameter.minimum}, {parameter.maximum}]: {value}"
            )
    if values["foundation_height"] >= values["pier_height"]:
        raise ScenarioError(
            f"foundation height {values['foundation_height']} must stay below pier height {values['pier_height']}"
        )


def parameter_patches(values: dict[str, float]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for parameter in RANDOM_PARAMETERS:
        for attribute in parameter.attributes:
            patches.append({
                "op": "set_attribute",
                "xpath": parameter.xpath,
                "attribute": attribute,
                "value": values[parameter.name],
            })
    return patches


def build_workflow(foundation: str = SCOUR_FOUNDATION) -> dict[str, Any]:
    """Semantic workflow: analysis sequence plus interface changes by foundation id."""
    analyses: list[dict[str, Any]] = [{"name": ANALYSIS_SEQUENCE[0]}]
    for name in ANALYSIS_SEQUENCE[1:]:
        analyses.append({
            "name": name,
            "interface_changes": [{"foundation": foundation, "fraction": SCOUR_FRACTIONS[name]}],
        })
    return {
        "analyses": analyses,
        "scour": {
            "foundation": foundation,
            "fractions": dict(SCOUR_FRACTIONS),
            "cumulative": False,
        },
    }


def build_job(
    hrx_bytes: bytes,
    *,
    job_id: str,
    template_id: str,
    registry: TemplateRegistry,
    rng_seed: str,
    base_seed: int,
    model_filename: str,
    foundation: str,
) -> tuple[JobSpec, dict[str, float]]:
    """Create one random scenario JOB from the reference HRX bytes."""
    rng = random.Random(rng_seed)
    values = sample_parameters(rng)
    validate_parameters(values)
    workflow = build_workflow(foundation)
    metadata = {
        "workflow_test": WORKFLOW_TEST_ID,
        "seed": {"base": base_seed, "job": rng_seed},
        "template_source": model_filename,
        "random_parameters": dict(values),
        "random_parameter_ranges": {
            parameter.name: {"min": parameter.minimum, "max": parameter.maximum, "unit": parameter.description}
            for parameter in RANDOM_PARAMETERS
        },
        "analysis_sequence": list(ANALYSIS_SEQUENCE),
        "scour": {
            "foundation": foundation,
            "levels": dict(SCOUR_FRACTIONS),
            "cumulative": False,
        },
    }
    job = job_from_hrx(
        hrx_bytes,
        job_id=job_id,
        template_id=template_id,
        registry=registry,
        workflow=workflow,
        metadata=metadata,
    )
    document = job.model_dump(mode="json")
    document["model"]["patches"] = parameter_patches(values)
    spec = JobSpec.model_validate(document)
    return spec, values


def generate_random_jobs(
    model_path: str | Path,
    *,
    output_dir: str | Path = "generated_jobs",
    count: int = DEFAULT_JOB_COUNT,
    base_seed: int = DEFAULT_BASE_SEED,
    foundation: str = SCOUR_FOUNDATION,
) -> list[Path]:
    """Generate ``count`` reproducible random scenario JOBs from a reference HRX.

    Fails clearly (never silently continues with an unscoured model) when the
    reference model cannot be loaded, the scour foundation is missing, the
    sampled parameters are invalid, or a JOB cannot compile or serialize.
    """
    if count < 1:
        raise ScenarioError(f"count must be at least 1, got {count}")
    path = Path(model_path)
    try:
        hrx_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise ScenarioError(f"reference model not found: {path}") from exc
    inspection = inspect_hrx(hrx_bytes)
    if not inspection.validation["valid"]:
        raise ScenarioError(f"reference model has invalid geometry: {inspection.validation['errors']}")
    piers = find_piers(hrx_bytes)
    resolve_foundation(piers, foundation)

    output = Path(output_dir)
    registry = TemplateRegistry(output / "templates")
    template_id = path.stem or "model"
    written: list[Path] = []
    for index in range(1, count + 1):
        rng_seed = f"{base_seed}:{index}"
        job_id = f"random_{index:03d}"
        job, _ = build_job(
            hrx_bytes,
            job_id=job_id,
            template_id=template_id,
            registry=registry,
            rng_seed=rng_seed,
            base_seed=base_seed,
            model_filename=path.name,
            foundation=foundation,
        )
        artifact = compile_job(job, registry)
        compiled = inspect_hrx(artifact.hrx_bytes)
        if not compiled.validation["valid"]:
            raise ScenarioError(f"job {job_id!r} compiled to an invalid model: {compiled.validation['errors']}")
        job_path = output / job_id / "job.json"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(job.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        job_path.write_text(text, encoding="utf-8")
        try:
            restored = JobSpec.model_validate(json.loads(job_path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise ScenarioError(f"job {job_id!r} failed serialization/deserialization: {exc}") from exc
        if restored.model_dump(mode="json") != job.model_dump(mode="json"):
            raise ScenarioError(f"job {job_id!r} does not survive a JSON round trip unchanged")
        written.append(job_path)
    return written
