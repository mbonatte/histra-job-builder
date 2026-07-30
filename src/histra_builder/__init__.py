"""Deterministic JOB to HRX compilation."""

from .canonical import canonical_json_bytes, job_sha256, sha256_hex
from .compiler import BuildArtifact, compile_job
from .importer import job_from_hrx
from .models import JobSpec
from .templates import TemplateRegistry

__all__ = [
    "BuildArtifact",
    "JobSpec",
    "TemplateRegistry",
    "canonical_json_bytes",
    "compile_job",
    "job_from_hrx",
    "job_sha256",
    "sha256_hex",
]

__version__ = "1.0.0"
