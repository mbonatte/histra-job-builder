from .canonical import canonical_json_bytes, job_sha256, sha256_hex
from .compiler import BUILDER_VERSION, BuildArtifact, compile_job
from .errors import (
    BuilderError,
    InvalidHrxError,
    InvalidJobError,
    PatchError,
    ScenarioError,
    TemplateIntegrityError,
    TemplateNotFoundError,
    VariantError,
)
from .generator import (
    AbutmentSpec,
    BridgeMesher,
    BridgeSpec,
    GeneratedBridgeMesh,
    PierSpec,
    SpanSpec,
    build_bridge_mesh,
    generate_bridge_hrx,
    generate_bridge_hrx_file,
)
from .importer import job_from_hrx
from .inspector import HrxInspection, inspect_hrx, preview_job
from .models import JobSpec, ModelSpec, PatchOperation, TemplateRef
from .scenarios import generate_random_jobs
from .templates import TemplateAsset, TemplateRegistry
from .variants import VariantDefinition, VariantSet, apply_variant, generate_variants

__all__ = [
    "AbutmentSpec",
    "BUILDER_VERSION",
    "BridgeMesher",
    "BridgeSpec",
    "BuildArtifact",
    "BuilderError",
    "GeneratedBridgeMesh",
    "HrxInspection",
    "InvalidHrxError",
    "InvalidJobError",
    "JobSpec",
    "ModelSpec",
    "PatchError",
    "PatchOperation",
    "PierSpec",
    "ScenarioError",
    "SpanSpec",
    "TemplateAsset",
    "TemplateIntegrityError",
    "TemplateNotFoundError",
    "TemplateRef",
    "TemplateRegistry",
    "VariantDefinition",
    "VariantError",
    "VariantSet",
    "apply_variant",
    "build_bridge_mesh",
    "canonical_json_bytes",
    "compile_job",
    "generate_bridge_hrx",
    "generate_bridge_hrx_file",
    "generate_random_jobs",
    "generate_variants",
    "inspect_hrx",
    "job_from_hrx",
    "job_sha256",
    "preview_job",
    "sha256_hex",
]

__version__ = "1.2.0"
