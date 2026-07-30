from __future__ import annotations

from typing import Any

from .canonical import sha256_hex
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
) -> JobSpec:
    """Create the minimal lossless JOB for an existing HRX template."""
    digest = sha256_hex(hrx_bytes)
    if registry is not None:
        asset = registry.register(template_id, hrx_bytes)
        digest = asset.sha256
    return JobSpec.model_validate(
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "model": {
                "output_path": output_path,
                "template": {"id": template_id, "sha256": digest},
                "patches": [],
            },
            "workflow": workflow or {},
            "metadata": metadata or {},
        }
    )
