from __future__ import annotations

from pathlib import Path
from typing import Any

from .fingerprints import (
    mesh_geometry_fingerprint,
    request_section_fingerprints,
    wizard_geometry_fingerprint,
    xml_sha256,
)
from .hrx import HrxBuildResult, HrxBuilder
from .mesh import generate_mesh, mesh_from_hrx
from .model_points import existing_model_points, select_model_points
from .schemas import GenerationRequest, PreviewResponse
from .template import TemplatePatcher, TemplateRegistry, TemplateRepository


class GeneratorService:
    def __init__(self, template_path: Path, imported_dir: Path | None = None):
        self.registry = TemplateRegistry(template_path, imported_dir)
        self.template_path = template_path
        # Compatibility for older callers/tests that access service.repository.
        self.repository = TemplateRepository(template_path)

    def resolve_template(self, request: GenerationRequest) -> Path:
        return self.registry.resolve(request.model)

    def _import_state(self, request: GenerationRequest, template_path: Path) -> dict[str, Any]:
        imported = request.model.imported
        current = request_section_fingerprints(request)
        if imported is None:
            return {
                "imported": False,
                "current": current,
                "exact": False,
                "geometry_unchanged": False,
                "geometry_equivalent": False,
                "analyses_unchanged": False,
                "materials_unchanged": False,
                "config_unchanged": False,
            }
        expected = imported.fingerprints
        source_bytes = template_path.read_bytes()
        source_hash_matches = xml_sha256(source_bytes) == imported.source_sha256
        return {
            "imported": True,
            "current": current,
            "source_hash_matches": source_hash_matches,
            "exact": bool(
                imported.preserve_exact_if_unchanged
                and source_hash_matches
                and current.get("hrx") == expected.get("hrx")
            ),
            "geometry_unchanged": bool(
                request.Mesh.PreserveImportedGeometry
                and imported.preserve_geometry_if_unchanged
                and current.get("geometry") == expected.get("geometry")
            ),
            "geometry_equivalent": False,
            "analyses_unchanged": bool(
                imported.preserve_analyses_if_unchanged
                and current.get("analyses") == expected.get("analyses")
            ),
            "materials_unchanged": current.get("materials") == expected.get("materials"),
            "config_unchanged": current.get("config") == expected.get("config"),
        }

    @staticmethod
    def _uses_default_imported_mesh_controls(request: GenerationRequest) -> bool:
        """Only infer target-size equivalence for the importer defaults.

        Explicit ArcDivisions/MaxLength overrides are user instructions and must
        always activate the Python mesher, even if the resulting count happens to
        match the imported topology.
        """

        mesh = request.Mesh
        return bool(
            mesh.PreserveImportedGeometry
            and mesh.MaxLength is None
            and mesh.ArcDivisions is None
            and mesh.ArcDivisionMode == "observed-even"
            and abs(mesh.NodeTolerance - 1e-5) <= 1e-12
        )

    def _target_mesh_is_discretely_equivalent(
        self,
        source_tree,
        patched_tree,
        request: GenerationRequest,
    ) -> bool:
        """Detect a target-size edit that leaves the reference discretisation unchanged.

        The imported software mesh is retained only when the editable WizardData
        is identical apart from the global target length *and* the Python
        reconstruction produces an identical numbering-independent mesh under
        the observed nearest-integer subdivision rule.
        """

        if not self._uses_default_imported_mesh_controls(request):
            return False
        if wizard_geometry_fingerprint(
            source_tree, ignore_target_mesh=True
        ) != wizard_geometry_fingerprint(patched_tree, ignore_target_mesh=True):
            return False

        source_mesh = generate_mesh(source_tree, request.Mesh)
        target_mesh = generate_mesh(patched_tree, request.Mesh)
        return mesh_geometry_fingerprint(source_mesh) == mesh_geometry_fingerprint(target_mesh)

    def prepare(self, request: GenerationRequest):
        template_path = self.resolve_template(request)
        source_tree = TemplateRepository(template_path).load()
        tree = TemplateRepository(template_path).load()
        state = self._import_state(request, template_path)
        warnings: list[str] = []

        if state["exact"]:
            mesh = mesh_from_hrx(tree)
            warnings.append("Imported job is unchanged; preview uses the source HRX geometry")
            return tree, mesh, warnings, state, template_path

        patcher = TemplatePatcher(request)
        patcher.patch(tree)
        warnings.extend(patcher.warnings)

        if state["imported"] and not state["geometry_unchanged"]:
            try:
                state["geometry_equivalent"] = self._target_mesh_is_discretely_equivalent(
                    source_tree, tree, request
                )
            except ValueError as error:
                # Unsupported source geometry should fall through to the normal
                # mesher, which will return its own detailed validation error.
                warnings.append(f"Imported mesh-equivalence check was skipped: {error}")

        if state["geometry_unchanged"] or state["geometry_equivalent"]:
            mesh = mesh_from_hrx(tree)
            if state["geometry_equivalent"]:
                mesh.metadata["geometryMode"] = "preserved-reference-equivalent"
                mesh.metadata["targetSizeEquivalent"] = True
                warnings.append(
                    "Target mesh length changed, but the target-size discretisation signature is unchanged; "
                    "the original software-generated nodes, quads and restraints were preserved"
                )
            else:
                mesh.metadata["geometryMode"] = "preserved-imported"
                mesh.metadata["targetSizeEquivalent"] = False
                warnings.append("WizardData is unchanged; source nodes, quads and restraints are preserved")
        else:
            mesh = generate_mesh(tree, request.Mesh)
            warnings.extend(mesh.metadata.get("warnings", []))
        return tree, mesh, warnings, state, template_path

    def preview(self, request: GenerationRequest) -> PreviewResponse:
        tree, mesh, warnings, state, _template_path = self.prepare(request)
        if state["imported"] and (state["geometry_unchanged"] or state["geometry_equivalent"]):
            points = existing_model_points(tree)
        else:
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
            warnings=warnings,
        )

    def generate(self, request: GenerationRequest) -> HrxBuildResult:
        tree, mesh, patch_warnings, state, template_path = self.prepare(request)
        builder = HrxBuilder()
        if state["exact"]:
            result = builder.source_exact(tree, template_path.read_bytes())
        elif state["geometry_unchanged"] or state["geometry_equivalent"]:
            result = builder.preserve_existing(
                tree,
                mesh,
                request,
                preserve_analyses=state["analyses_unchanged"],
                preserve_model_points=True,
                preservation_reason=(
                    "the target-size discretisation signature is unchanged"
                    if state["geometry_equivalent"]
                    else "WizardData and mesh controls are unchanged"
                ),
            )
        else:
            result = builder.build(tree, mesh, request)
        result.validation.warnings.extend(patch_warnings)
        return result
