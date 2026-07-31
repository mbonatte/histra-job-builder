from .canonical import canonical_json_bytes, job_sha256, sha256_hex
from .compiler import BUILDER_VERSION, BuildArtifact, compile_job
from .errors import (
    BuilderError,
    InvalidHrxError,
    InvalidJobError,
    PatchError,
    TemplateIntegrityError,
    TemplateNotFoundError,
    VariantError,
)
from .importer import job_from_hrx
from .inspector import HrxInspection, inspect_hrx, preview_job
from .models import JobSpec, ModelSpec, PatchOperation, TemplateRef
from .templates import TemplateAsset, TemplateRegistry
from .variants import VariantDefinition, VariantSet, apply_variant, generate_variants

__all__ = [
    "BUILDER_VERSION", "BuildArtifact", "BuilderError", "HrxInspection",
    "InvalidHrxError", "InvalidJobError", "JobSpec", "ModelSpec", "PatchError",
    "PatchOperation", "TemplateAsset", "TemplateIntegrityError", "TemplateNotFoundError",
    "TemplateRef", "TemplateRegistry", "VariantDefinition", "VariantError", "VariantSet",
    "apply_variant", "canonical_json_bytes", "compile_job", "generate_variants",
    "inspect_hrx", "job_from_hrx", "job_sha256", "preview_job", "sha256_hex",
]

__version__ = "1.1.0"
