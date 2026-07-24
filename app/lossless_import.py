"""Source-independent HRX import acceptance gate."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import BUILDER_VERSION, bytes_sha256, job_sha256
from .import_hrx import imported_job_payload
from .roundtrip import compare_hrx
from .schemas import GenerationRequest
from .service import GeneratorService
from .template import TemplateRegistry


@dataclass(frozen=True)
class LosslessImportResult:
    job: dict[str, Any]
    comparison: dict[str, Any]
    validation: dict[str, Any]


def _comparison_error(comparison: dict[str, Any]) -> str:
    differences = comparison.get("differences")
    if isinstance(differences, dict) and differences:
        return json.dumps(differences, ensure_ascii=False, sort_keys=True)
    if isinstance(differences, list) and differences:
        return "; ".join(str(item) for item in differences)
    return "the generated HRX is not semantically equivalent to the uploaded HRX"


def import_losslessly(
    source: bytes,
    source_filename: str,
    *,
    compiler: GeneratorService,
    job_id: str | None = None,
) -> LosslessImportResult:
    """Extract a JOB and prove that it alone can regenerate the source model.

    The source HRX is used only inside a temporary directory while the existing
    extractor reads it. The returned JOB contains no template path, imported
    state or source-HRX dependency. Newly authored JOBs use the same compiler
    path and therefore require no reference HRX.
    """

    with tempfile.TemporaryDirectory(prefix="histra-import-") as temporary:
        registry = TemplateRegistry(
            compiler.registry.default_path,
            imported_dir=Path(temporary),
        )
        extracted = imported_job_payload(
            source,
            source_filename,
            registry=registry,
            job_id=job_id,
        )

    payload = json.loads(json.dumps(extracted))
    model = payload.setdefault("model", {})
    model.pop("template_path", None)
    model.pop("source_sha256", None)
    model.pop("imported", None)
    payload.setdefault("Mesh", {})["PreserveImportedGeometry"] = False

    metadata = payload.setdefault("metadata", {})
    for key in (
        "imported_from",
        "imported_hrx_version",
        "imported_wizard_type",
    ):
        metadata.pop(key, None)

    request = GenerationRequest.model_validate(payload)
    generated = compiler.generate(request)
    comparison = compare_hrx(source, generated.xml)
    validation = generated.validation.model_dump()

    if not generated.validation.valid:
        raise ValueError(
            "Imported HRX cannot be regenerated from JOB: "
            + "; ".join(generated.validation.errors)
        )
    if not comparison.get("match", False):
        raise ValueError(
            "Imported HRX is not losslessly representable by the JOB schema: "
            + _comparison_error(comparison)
        )

    normalized = request.model_dump(by_alias=True, exclude_none=True)
    normalized.setdefault("metadata", {})["import_validation"] = {
        "status": "lossless",
        "source_filename": Path(source_filename).name,
        "source_hrx_sha256": bytes_sha256(source),
        "generated_hrx_sha256": bytes_sha256(generated.xml),
        "builder_version": BUILDER_VERSION,
        "checks": comparison.get("checks", {}),
        "validation": validation,
    }
    normalized["metadata"]["job_sha256"] = job_sha256(normalized)
    return LosslessImportResult(normalized, comparison, validation)
