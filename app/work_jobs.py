from __future__ import annotations

from typing import Any

from .hrx import HrxBuildResult
from .schemas import GenerationRequest


def generated_work_job(
    request: GenerationRequest,
    result: HrxBuildResult,
    *,
    template_name: str = "model.hrx",
    template_version: str | None = None,
) -> dict[str, Any]:
    """Create the runner-ready work-job JSON paired with a generated HRX.

    Geometry/material/configuration inputs are retained for reproducibility. The
    runner contract is kept at the top level, and model.path is changed from the
    template name to the generated HRX name. Nothing in this dictionary is
    serialized into the HRX document.
    """

    payload = request.model_dump(by_alias=True, exclude_none=True)
    payload["model"] = dict(payload.get("model") or {})
    payload["model"]["path"] = request.hrx_filename

    # Keep the runner JSON consistent with the HRX patcher.  Until separate
    # component mesh controls are exposed, BridgeDefinition.Nl is the global
    # target used by both HiStrA bridge meshers.
    nl = (payload.get("Geometry") or {}).get("BridgeDefinition", {}).get("Nl")
    if nl is not None:
        config = payload.setdefault("Config", {})
        config["ArcoMesherQuadLengthMax"] = nl
        config["WallMesherQuadLengthMax"] = nl

    model_points = [
        {
            "id": point.name,
            "name": point.name,
            "node_key": point.node_key,
            "component": point.component,
            "point": point.point,
        }
        for point in result.model_points
    ]
    all_model_point_ids = [point["id"] for point in model_points]

    # An empty model_point_ids list means "all generated model points" in the
    # input job. The generated runner job resolves it explicitly so execution
    # does not depend on an implicit convention.
    for analysis in payload.get("analyses", []):
        outputs = analysis.get("outputs") or {}
        displacements = outputs.get("displacements")
        if displacements and displacements.get("enabled", True):
            if not displacements.get("model_point_ids"):
                displacements["model_point_ids"] = list(all_model_point_ids)

    payload["generated"] = {
        "generator_schema_version": "1.0",
        "template": {
            "path": template_name,
            "version": template_version,
        },
        "artifacts": {
            "hrx": request.hrx_filename,
            "work_job": request.job_filename,
            "report": f"{request.job_id}.report.json",
        },
        "model_points": model_points,
        "analysis_names": [analysis.name for analysis in request.analyses],
        "hrx_validation": result.validation.model_dump(),
        "removed_counts": result.removed_counts,
    }
    return payload


def validate_requested_model_points(request: GenerationRequest, result: HrxBuildResult) -> list[str]:
    available = {point.name for point in result.model_points}
    errors: list[str] = []
    for analysis in request.analyses:
        displacement = analysis.outputs.displacements
        if displacement is None or not displacement.enabled:
            continue
        unknown = sorted(set(displacement.model_point_ids) - available)
        if unknown:
            errors.append(
                f"Analysis {analysis.name!r} requests unknown model_point_ids: {', '.join(unknown)}"
            )
    return errors


def generation_report(request: GenerationRequest, result: HrxBuildResult) -> dict[str, Any]:
    return {
        "schema_version": request.schema_version,
        "job_id": request.job_id,
        "artifacts": {
            "hrx": request.hrx_filename,
            "work_job": request.job_filename,
        },
        "validation": result.validation.model_dump(),
        "model_points": [point.as_dict() for point in result.model_points],
        "analyses": result.analyses,
        "removed_counts": result.removed_counts,
    }
