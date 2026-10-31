"""C#-parity random bridge portfolio generation.

Unlike the legacy reference-model patcher in ``scenarios.py``, this module
samples the actual bridge data model, regenerates the finite-element mesh, and
resolves the pier foundation interfaces to concrete solver keys.
"""
from __future__ import annotations

import json
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .canonical import sha256_hex
from .compiler import compile_job
from .errors import ScenarioError
from .importer import job_from_hrx
from .models import JobSpec
from .templates import TemplateRegistry

ANALYSIS_SEQUENCE = ("Vert", "Scour_1", "Scour_2")
SCOUR_MATERIAL_KEY = 147
DEFAULT_COUNT = 5
DEFAULT_BASE_SEED = 20261031

# C# standard springing angle used by the reference bridge models.
STANDARD_SPRINGING_ANGLE = 36.8699


@dataclass(frozen=True)
class PortfolioSpec:
    spec: Any
    values: Dict[str, Any]
    description: str


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def _span_spec(rng: random.Random) -> Any:
    from .generator.csharp_model import Span

    length = _round(rng.uniform(300.0, 500.0))
    rise = _round(rng.uniform(0.18 * length, 0.26 * length))
    springer = _round(rng.uniform(20.0, 35.0))
    crown = _round(rng.uniform(18.0, 30.0))
    return Span(
        L=length,
        W=0.0,  # filled after the bridge width is sampled
        f=rise,
        Tb=springer,
        Tt=crown,
        Asx=STANDARD_SPRINGING_ANGLE,
        Adx=STANDARD_SPRINGING_ANGLE,
        material_key=18,
        material_pulvino_key=22,
        material_reinforcement_key=24,
    )


def _strip_widths(rng: random.Random, width: float) -> List[float]:
    from .generator.csharp_model import Corsia

    strips = rng.randint(1, 3)
    slice_width = _round(width / strips, 2)
    widths = [slice_width] * strips
    widths[-1] = _round(width - sum(widths[:-1]), 2)
    return [Corsia(width=value) for value in widths]


def sample_spec(rng: random.Random) -> PortfolioSpec:
    """Sample a physically/numerically plausible C#-parity bridge."""
    from .generator.csharp_model import (
        Abutment,
        BridgeDefinition,
        CSharpBridgeSpec,
        Elevation,
        Elevations,
        Pier,
        Span,
    )

    num_spans = rng.randint(2, 3)
    spans = [_span_spec(rng) for _ in range(num_spans)]
    width = _round(rng.uniform(200.0, 350.0))
    for span in spans:
        span.W = width
    corsias = _strip_widths(rng, width)
    nl = _round(rng.uniform(50.0, 100.0))

    left = Abutment(
        b2=_round(max(50.0, max(span.Tb for span in spans) + rng.uniform(5.0, 25.0))),
        w2=width,
        H=_round(rng.uniform(0.0, 150.0)),
        Hf=_round(rng.uniform(0.0, 80.0)),
        material_key=18,
        material_foundation_key=141,
        kind="Sinistra",
    )
    right = Abutment(
        b2=_round(max(50.0, max(span.Tb for span in spans) + rng.uniform(5.0, 25.0))),
        w2=width,
        H=_round(rng.uniform(0.0, 150.0)),
        Hf=_round(rng.uniform(0.0, 80.0)),
        material_key=18,
        material_foundation_key=141,
        kind="Destra",
    )

    elements: List[object] = [left]
    for index, span in enumerate(spans):
        elements.append(span)
        if index < len(spans) - 1:
            adjacent = [span]
            if index + 1 < len(spans):
                adjacent.append(spans[index + 1])
            minimum = sum(item.Tb for item in adjacent) + rng.uniform(10.0, 40.0)
            elements.append(
                Pier(
                    b2=_round(max(70.0, minimum)),
                    w2=width,
                    H=_round(rng.uniform(100.0, 250.0)),
                    Hf=_round(rng.uniform(0.0, 100.0)),
                    material_key=18,
                    material_foundation_key=141,
                )
            )
    elements.append(right)

    elevation = _round(
        max(span.f + span.Tt for span in spans) + rng.uniform(25.0, 60.0)
    )
    definition = BridgeDefinition(
        width=width,
        width_top_pile=width,
        nl=nl,
        nt=20000.0,
        inclination_angle=0.0,
        slope=0.0,
        zlevel=500.0,
        thickness_ballast=0.0,
        thickness_riempimento=0.0,
        corsias=corsias,
    )
    spec = CSharpBridgeSpec(
        definition=definition,
        elements=elements,
        elevations=Elevations([Elevation(X=0.0, H1=elevation, H2=0.0, H3=0.0)]),
    )
    values = {
        "num_spans": num_spans,
        "width": width,
        "strip_widths": [corsia.width for corsia in corsias],
        "nl": nl,
        "spans": [
            {
                "L": span.L,
                "f": span.f,
                "Tb": span.Tb,
                "Tt": span.Tt,
            }
            for span in spans
        ],
        "abutments": [
            {"H": left.H, "Hf": left.Hf, "b2": left.b2},
            {"H": right.H, "Hf": right.Hf, "b2": right.b2},
        ],
        "piers": [
            {"H": element.H, "Hf": element.Hf, "b2": element.b2}
            for element in elements
            if isinstance(element, Pier)
        ],
        "elevation": elevation,
    }
    description = (
        f"{num_spans}-span bridge, width {width} cm, "
        f"{len(corsias)} strip(s), Nl={nl} cm"
    )
    return PortfolioSpec(spec=spec, values=values, description=description)


def _foundation_interface_keys(mesh: Any, foundation_tag: str) -> List[int]:
    """Prepare the generated HRX and return concrete foundation interface keys."""
    try:
        from histra.io.hr_loader import load_model
        from histra.preprocessing.prepare_model import prepare_model
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ScenarioError(
            "resolving scour interface keys requires the histra-python package"
        ) from exc

    from .generator.csharp_writer import serialize_csharp_mesh_to_hrx

    restraint_keys = {
        restraint.key
        for restraint in mesh.restraints
        if restraint.foundation_tag == foundation_tag
    }
    if not restraint_keys:
        raise ScenarioError(
            f"generated bridge has no foundation restraints for {foundation_tag!r}"
        )

    with tempfile.NamedTemporaryFile(suffix=".hrx") as handle:
        handle.write(serialize_csharp_mesh_to_hrx(mesh, include_scour_analyses=True))
        handle.flush()
        model = load_model(handle.name)
        prepare_model(model, force=True)
        keys = set()
        for interface in model.collections.interfaces.values():
            if (
                interface.parent_type_element1 == "Restraint"
                and interface.parent_element_key1 in restraint_keys
            ) or (
                interface.parent_type_element2 == "Restraint"
                and interface.parent_element_key2 in restraint_keys
            ):
                keys.add(interface.key)
    if not keys:
        raise ScenarioError(
            f"prepared model exposed no interfaces for {foundation_tag!r}"
        )
    return sorted(keys)


def build_native_job(
    *,
    job_id: str,
    template_id: str,
    registry: TemplateRegistry,
    rng_seed: str,
    base_seed: int,
    mesh: Any,
    hrx_bytes: bytes,
    spec: PortfolioSpec,
) -> Tuple[JobSpec, List[int]]:
    keys = _foundation_interface_keys(mesh, "pier_1")
    workflow = {
        "analyses": list(ANALYSIS_SEQUENCE),
        "interface_mutations": {
            "Scour_1": [
                {
                    "interface_keys": keys,
                    "material_key": SCOUR_MATERIAL_KEY,
                    "preserve_committed_state": True,
                }
            ],
            "Scour_2": [
                {
                    "interface_keys": keys,
                    "material_key": SCOUR_MATERIAL_KEY,
                    "preserve_committed_state": True,
                }
            ],
        },
        "scour": {
            "foundation": "pier_1",
            "material_key": SCOUR_MATERIAL_KEY,
            "interface_keys": keys,
            "cumulative": False,
        },
    }
    metadata = {
        "portfolio": "native-csharp-parity",
        "seed": {"base": base_seed, "job": rng_seed},
        "description": spec.description,
        "parameters": spec.values,
        "analysis_sequence": list(ANALYSIS_SEQUENCE),
        "template_sha256": sha256_hex(hrx_bytes),
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
    # Ensure the job graph is canonical and round-trips.
    job = JobSpec.model_validate(document)
    return job, keys


def generate_native_jobs(
    *,
    output_dir: str | Path,
    count: int = DEFAULT_COUNT,
    base_seed: int = DEFAULT_BASE_SEED,
) -> List[Path]:
    """Generate reproducible native C#-parity portfolio JOBs."""
    if count < 1:
        raise ScenarioError(f"count must be at least 1, got {count}")
    from .generator.csharp_mesher import build_csharp_bridge_mesh
    from .generator.csharp_writer import serialize_csharp_mesh_to_hrx

    output = Path(output_dir)
    registry = TemplateRegistry(output / "templates")
    written: List[Path] = []
    for index in range(1, count + 1):
        job_id = f"native_{index:03d}"
        rng_seed = f"{base_seed}:{index}"
        rng = random.Random(rng_seed)
        last_error: Exception | None = None
        for _attempt in range(10):
            sampled = sample_spec(rng)
            try:
                mesh = build_csharp_bridge_mesh(sampled.spec)
                hrx_bytes = serialize_csharp_mesh_to_hrx(
                    mesh, include_scour_analyses=True
                )
                compiled = compile_job(
                    job_from_hrx(
                        hrx_bytes,
                        job_id=job_id,
                        template_id=job_id,
                        registry=registry,
                        workflow={},
                        metadata={},
                    ),
                    registry,
                )
                if compiled.hrx_bytes != hrx_bytes:
                    raise ScenarioError("native model did not round-trip through the template registry")
                job, _keys = build_native_job(
                    job_id=job_id,
                    template_id=job_id,
                    registry=registry,
                    rng_seed=rng_seed,
                    base_seed=base_seed,
                    mesh=mesh,
                    hrx_bytes=hrx_bytes,
                    spec=sampled,
                )
            except Exception as exc:  # retry a different random draw
                last_error = exc
                continue
            break
        else:
            raise ScenarioError(
                f"could not generate a valid native bridge for {job_id}: {last_error}"
            )

        job_path = output / job_id / "job.json"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(
            json.dumps(job.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(job_path)
    return written
