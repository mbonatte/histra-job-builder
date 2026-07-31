from __future__ import annotations

from typing import Any

from .canonical import sha256_hex
from .inspector import inspect_hrx
from .models import JobSpec
from .templates import TemplateRegistry


def job_from_hrx(
    hrx_bytes: bytes,
    *,
    job_id: str,
    template_id: str,
    workflow: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    output_path: str = "model.hrx",
    registry: TemplateRegistry | None = None,
    validate_xml: bool = True,
) -> JobSpec:
    """Create a minimal, lossless canonical JOB for an existing HRX file."""
    inspection = inspect_hrx(hrx_bytes) if validate_xml else None
    digest = sha256_hex(hrx_bytes)
    if registry is not None:
        digest = registry.register(template_id, hrx_bytes).sha256
    combined_metadata = dict(metadata or {})
    combined_metadata.setdefault("import", {})
    if isinstance(combined_metadata["import"], dict):
        combined_metadata["import"].update({
            "source": "official-histra-hrx",
            "hrx_sha256": digest,
            "node_count": inspection.counts.get("nodes", 0) if inspection else None,
            "quad_count": inspection.counts.get("quads", 0) if inspection else None,
        })
    return JobSpec.model_validate({
        "schema_version": "1.0",
        "job_id": job_id,
        "model": {
            "output_path": output_path,
            "template": {"id": template_id, "sha256": digest},
            "patches": [],
        },
        "workflow": workflow or {},
        "metadata": combined_metadata,
    })
