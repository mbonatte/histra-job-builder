from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model used by the public API.

    Unknown fields are intentionally retained so newer work-job properties can be
    accepted before a dedicated UI/editor is added for them.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Lane(StrictModel):
    Name: str
    Width: float = Field(gt=0)
    MaterialKey: str
    Description: Optional[str] = None
    Height: float = Field(default=0.0, ge=0)


class BridgeDefinitionPatch(StrictModel):
    Width: Optional[float] = Field(default=None, gt=0)
    Slope: Optional[float] = None
    InclinationAngle: Optional[float] = None
    Zlevel: Optional[float] = None
    ThicknessBallast: Optional[float] = None
    ThicknessRiempimento: Optional[float] = None
    Nl: Optional[float] = Field(default=None, gt=0)


class SupportPatch(StrictModel):
    AbutmentKind: Optional[str] = None
    H: Optional[float] = None
    b1: Optional[float] = Field(default=None, ge=0)
    b2: Optional[float] = Field(default=None, gt=0)
    b3: Optional[float] = Field(default=None, ge=0)
    w1: Optional[float] = Field(default=None, ge=0)
    w2: Optional[float] = Field(default=None, gt=0)
    w3: Optional[float] = Field(default=None, ge=0)
    VerticalAllignment: Optional[str] = None
    Hsp1: Optional[float] = None
    Hsp2: Optional[float] = None
    Hf: Optional[float] = Field(default=None, ge=0)
    B1f: Optional[float] = Field(default=None, ge=0)
    B3f: Optional[float] = Field(default=None, ge=0)
    W1f: Optional[float] = Field(default=None, ge=0)
    W3f: Optional[float] = Field(default=None, ge=0)
    Kz: Optional[float] = None
    Origin: Optional[List[float]] = None
    MaterialKey: Optional[str] = None
    MaterialFoundationKey: Optional[str] = None

    @model_validator(mode="after")
    def origin_has_three_values(self) -> "SupportPatch":
        if self.Origin is not None and len(self.Origin) != 3:
            raise ValueError("Origin must contain exactly three coordinates")
        return self


class SpanPatch(StrictModel):
    L: Optional[float] = Field(default=None, gt=0)
    W: Optional[float] = Field(default=None, gt=0)
    f: Optional[float] = Field(default=None, gt=0)
    Tb: Optional[float] = Field(default=None, gt=0)
    Tt: Optional[float] = Field(default=None, gt=0)
    Dz: Optional[float] = None
    MaterialKey: Optional[str] = None
    MaterialPulvinoKey: Optional[str] = None
    Circolare: Optional[bool | str] = None


class ElevationPatch(StrictModel):
    X: float
    H1: float
    H2: float = 0.0
    H3: float = 0.0


class BackfillLayerPatch(StrictModel):
    Tag: str
    MaterialKey: Optional[str] = None
    MaterialKey2: Optional[str] = None
    UniformMaterial: Optional[bool | str] = None
    RowIndexMaterial: Optional[int | str] = None
    GenerateComputationalElements: Optional[bool | str] = None


class ElevationsPatch(StrictModel):
    Elevations: List[ElevationPatch]
    Layers: List[BackfillLayerPatch] = Field(default_factory=list)


class GeometryPatch(StrictModel):
    BridgeDefinition: BridgeDefinitionPatch = Field(default_factory=BridgeDefinitionPatch)
    Lanes: Optional[List[Lane]] = None
    Abutments: List[SupportPatch]
    Piers: List[SupportPatch]
    Spans: List[SpanPatch]
    Elevations: ElevationsPatch

    @model_validator(mode="after")
    def sequence_is_valid(self) -> "GeometryPatch":
        if len(self.Abutments) != 2:
            raise ValueError("Exactly two abutments are required")
        if len(self.Spans) != len(self.Piers) + 1:
            raise ValueError("The number of spans must equal the number of piers plus one")
        if self.Lanes and self.BridgeDefinition.Width is not None:
            lane_width = sum(lane.Width for lane in self.Lanes)
            if abs(lane_width - self.BridgeDefinition.Width) > 1e-6:
                raise ValueError(
                    f"Lane widths sum to {lane_width}, but BridgeDefinition.Width is "
                    f"{self.BridgeDefinition.Width}"
                )
        return self


class MaterialPatch(StrictModel):
    Key: str
    Name: str


class AnalysisAttributePatch(StrictModel):
    ConvergenceTolerance: Optional[float] = Field(default=None, gt=0)
    NumberOfEigenModes: Optional[int] = Field(default=None, gt=0)
    NumberOfLanczosEigenVectors: Optional[int] = Field(default=None, ge=0)
    MaxIterations: Optional[int] = Field(default=None, gt=0)


class AnalysisParameterSet(StrictModel):
    Defaults: AnalysisAttributePatch = Field(default_factory=AnalysisAttributePatch)
    ByName: Dict[str, AnalysisAttributePatch] = Field(default_factory=dict)


class AdvancedOptionsPatch(StrictModel):
    InterfaceNrow: Optional[int] = Field(default=None, gt=0)
    ArcoMesherQuadLengthMax: Optional[float] = Field(default=None, gt=0)
    WallMesherQuadLengthMax: Optional[float] = Field(default=None, gt=0)


class MeshPatch(StrictModel):
    """Mesh-generation controls. This is the uppercase ``Mesh`` object."""

    MaxLength: Optional[float] = Field(default=None, gt=0)
    NodeTolerance: float = Field(default=1e-5, gt=0)
    ArcDivisionMode: str = "observed-even"
    ArcDivisions: Optional[int] = Field(default=None, gt=0)
    PreserveImportedGeometry: bool = True


# ---------------------------------------------------------------------------
# Work-job contract (not serialized into the HRX)
# ---------------------------------------------------------------------------


class ImportedModelState(StrictModel):
    template_path: str
    source_filename: str
    source_sha256: str
    fingerprints: Dict[str, str]
    preserve_exact_if_unchanged: bool = True
    preserve_geometry_if_unchanged: bool = True
    preserve_analyses_if_unchanged: bool = True
    preserve_model_points_if_unchanged: bool = True


class JobModelReference(StrictModel):
    path: str = "model.hrx"
    template_path: Optional[str] = None
    source_sha256: Optional[str] = None
    imported: Optional[ImportedModelState] = None

    @model_validator(mode="after")
    def path_is_a_file(self) -> "JobModelReference":
        if not self.path or PurePath(self.path).name in {"", ".", ".."}:
            raise ValueError("model.path must identify an HRX file")
        return self


class JobMeshRun(StrictModel):
    """Optional runner-side meshing/initial analysis stage.

    This lowercase ``mesh`` object is work-runner configuration and is distinct
    from the uppercase ``Mesh`` object used by the geometry generator.
    """

    enabled: bool = False
    analysis_name: str = "StartMesh"
    timeout_seconds: int = Field(default=900, gt=0)


class ScourJobConfig(StrictModel):
    foundation_interface_materials: List[str] = Field(default_factory=list)
    scoured_foundation_interface_material: Optional[str] = None


class DisplacementOutput(StrictModel):
    enabled: bool = True
    all_steps: bool = True
    model_point_ids: List[str] = Field(default_factory=list)


class ReactionOutput(StrictModel):
    enabled: bool = True
    all_steps: bool = True


class ModalContributionOutput(StrictModel):
    enabled: bool = False
    top_n: int = Field(default=3, gt=0)


class AnalysisOutputs(StrictModel):
    displacements: Optional[DisplacementOutput] = None
    reactions: Optional[ReactionOutput] = None
    modal_contributions: Optional[ModalContributionOutput] = None


class WorkAnalysis(StrictModel):
    name: str = Field(min_length=1)
    timeout_seconds: int = Field(default=50, gt=0)
    interfaces: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    outputs: AnalysisOutputs = Field(default_factory=AnalysisOutputs)
    ConvergenceTolerance: Optional[float] = Field(default=None, gt=0)
    NumberOfEigenModes: Optional[int] = Field(default=None, gt=0)
    NumberOfLanczosEigenVectors: Optional[int] = Field(default=None, ge=0)
    MaxIterations: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def interface_ratios_are_valid(self) -> "WorkAnalysis":
        for component, sides in self.interfaces.items():
            if not component:
                raise ValueError("Analysis interface component names cannot be empty")
            for side, ratio in sides.items():
                if not side:
                    raise ValueError("Analysis interface side names cannot be empty")
                if ratio < 0 or ratio > 1:
                    raise ValueError(
                        f"Interface deletion ratio for {component}.{side} must be between 0 and 1"
                    )
        return self

    def hrx_attributes(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for name in (
            "ConvergenceTolerance",
            "NumberOfEigenModes",
            "NumberOfLanczosEigenVectors",
            "MaxIterations",
        ):
            value = getattr(self, name)
            if value is not None:
                values[name] = value
        return values


class JobValidation(StrictModel):
    require_completed_state: bool = True
    require_results_database: bool = True
    minimum_results_bytes: int = Field(default=1, ge=0)


class GenerationRequest(StrictModel):
    """Complete model-generation + execution work job.

    Lowercase fields form the work-runner contract. Uppercase fields control HRX
    generation. Work-runner data is never written into the HRX.
    """

    schema_version: str = "1.0"
    job_id: str
    model: JobModelReference = Field(default_factory=JobModelReference)
    mesh: JobMeshRun = Field(default_factory=JobMeshRun)
    scour: ScourJobConfig = Field(default_factory=ScourJobConfig)
    analyses: List[WorkAnalysis]
    validation: JobValidation = Field(default_factory=JobValidation)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    Geometry: GeometryPatch
    Materials: List[MaterialPatch]
    AnalysisParameters: AnalysisParameterSet = Field(default_factory=AnalysisParameterSet)
    advanced_options: AdvancedOptionsPatch = Field(
        default_factory=AdvancedOptionsPatch,
        alias="Config",
        serialization_alias="Config",
    )
    Mesh: MeshPatch = Field(default_factory=MeshPatch)

    # Legacy compatibility fields. They are accepted on input, but omitted from
    # generated work-job JSON. Existing Python modules can still use Analysis.
    Analysis: Dict[str, Dict[str, Any]] = Field(default_factory=dict, exclude=True)
    OutputName: Optional[str] = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_request(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)

        legacy_analysis = data.get("Analysis") or {}
        analyses = data.get("analyses")
        if analyses is None and legacy_analysis:
            analyses = [
                {
                    "name": name,
                    "timeout_seconds": 50,
                    "interfaces": scenario if isinstance(scenario, dict) else {},
                    "outputs": {},
                }
                for name, scenario in legacy_analysis.items()
            ]
            data["analyses"] = analyses

        if "job_id" not in data:
            output_name = str(data.get("OutputName") or "generated_model")
            job_id = PurePath(output_name).stem or "generated_model"
            data["job_id"] = re.sub(r"[^A-Za-z0-9._-]+", "-", job_id).strip("-._") or "generated_model"

        data.setdefault("schema_version", "1.0")
        data.setdefault("model", {"path": "model.hrx"})
        data.setdefault("mesh", {"enabled": False, "analysis_name": "StartMesh", "timeout_seconds": 900})
        data.setdefault("scour", {})
        data.setdefault("validation", {})
        data.setdefault("metadata", {})
        return data

    @model_validator(mode="after")
    def validate_and_derive(self) -> "GenerationRequest":
        if self.schema_version != "1.0":
            raise ValueError(f"Unsupported schema_version {self.schema_version!r}; expected '1.0'")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.job_id):
            raise ValueError(
                "job_id must be 1-128 characters and contain only letters, numbers, '.', '_' or '-'"
            )
        if self.job_id.lower().endswith(".hrx"):
            raise ValueError("job_id must not include the .hrx extension")
        if not self.analyses:
            raise ValueError("At least one analysis must be requested")
        names = [analysis.name for analysis in self.analyses]
        if len(set(names)) != len(names):
            raise ValueError("Analysis names must be unique")

        # Compatibility map consumed by the existing HRX builder. Only interface
        # scenarios are stored here; timeout/output/scour work-job data stays out
        # of the HRX document.
        self.Analysis = {analysis.name: analysis.interfaces for analysis in self.analyses}

        # Per-analysis attributes in the work-job list override the optional
        # AnalysisParameters.ByName map while preserving defaults.
        for analysis in self.analyses:
            attributes = analysis.hrx_attributes()
            if attributes:
                base = self.AnalysisParameters.ByName.get(analysis.name)
                merged = base.model_dump(exclude_none=True) if base is not None else {}
                merged.update(attributes)
                self.AnalysisParameters.ByName[analysis.name] = AnalysisAttributePatch(**merged)
        return self

    @property
    def hrx_filename(self) -> str:
        return f"{self.job_id}.hrx"

    @property
    def job_filename(self) -> str:
        return f"{self.job_id}.json"


class ValidationReport(StrictModel):
    valid: bool
    errors: List[str]
    warnings: List[str]
    counts: Dict[str, int]


class PreviewResponse(StrictModel):
    job_id: str
    hrx_filename: str
    mesh: Dict[str, Any]
    model_points: List[Dict[str, Any]]
    analyses: List[Dict[str, Any]]
    warnings: List[str]
