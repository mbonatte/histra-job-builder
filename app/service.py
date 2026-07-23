from __future__ import annotations

from pathlib import Path

from .hrx import HrxBuildResult, HrxBuilder
from .mesh import generate_mesh
from .model_points import select_model_points
from .schemas import GenerationRequest, PreviewResponse
from .template import TemplatePatcher, TemplateRepository


class GeneratorService:
    def __init__(self, template_path: Path):
        self.repository = TemplateRepository(template_path)
        self.template_path = template_path

    def prepare(self, request: GenerationRequest):
        tree = self.repository.load()
        patcher = TemplatePatcher(request)
        patcher.patch(tree)
        mesh = generate_mesh(tree, request.Mesh)
        return tree, mesh, patcher.warnings

    def preview(self, request: GenerationRequest) -> PreviewResponse:
        tree, mesh, patch_warnings = self.prepare(request)
        points = select_model_points(tree, mesh)
        analyses = [
            {
                "name": analysis.name,
                "timeout_seconds": analysis.timeout_seconds,
                "interfaces": analysis.interfaces,
                "outputs": analysis.outputs.model_dump(exclude_none=True),
                "hrx_parameters": analysis.hrx_attributes(),
                "interfaces_encoded_in_hrx": False,
            }
            for analysis in request.analyses
        ]
        return PreviewResponse(
            job_id=request.job_id,
            hrx_filename=request.hrx_filename,
            mesh=mesh.as_dict(),
            model_points=[point.as_dict() for point in points],
            analyses=analyses,
            warnings=[*patch_warnings, *mesh.metadata.get("warnings", [])],
        )

    def generate(self, request: GenerationRequest) -> HrxBuildResult:
        tree, mesh, patch_warnings = self.prepare(request)
        result = HrxBuilder().build(tree, mesh, request)
        result.validation.warnings.extend(patch_warnings)
        return result
