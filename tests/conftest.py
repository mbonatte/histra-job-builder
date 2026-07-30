from pathlib import Path

import pytest

from histra_builder.canonical import sha256_hex
from histra_builder.templates import TemplateRegistry


@pytest.fixture
def template_bytes() -> bytes:
    return (Path(__file__).parent / "fixtures" / "base.hrx").read_bytes()


@pytest.fixture
def registry(tmp_path: Path, template_bytes: bytes) -> TemplateRegistry:
    registry = TemplateRegistry(tmp_path)
    registry.register("base", template_bytes)
    return registry


@pytest.fixture
def base_job(template_bytes: bytes) -> dict:
    return {
        "schema_version": "1.0",
        "job_id": "job-001",
        "model": {
            "output_path": "models/job-001.hrx",
            "template": {"id": "base", "sha256": sha256_hex(template_bytes)},
            "patches": [],
        },
        "workflow": {"analyses": [{"id": "dead-load"}]},
        "metadata": {"campaign": "smoke"},
    }
