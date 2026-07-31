from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from histra_builder import TemplateRegistry

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def hrx_bytes() -> bytes:
    """Representative RailBridge HRX used by v1.1 inspection/UI tests."""
    return (_FIXTURES / "simple.hrx").read_bytes()


@pytest.fixture
def template_bytes() -> bytes:
    """Legacy generic HRX retained for compiler-contract regressions."""
    return (_FIXTURES / "base.hrx").read_bytes()


@pytest.fixture
def registry(tmp_path: Path, template_bytes: bytes) -> TemplateRegistry:
    """Fresh immutable registry containing the shared ``base`` template."""
    value = TemplateRegistry(tmp_path / "templates")
    value.register("base", template_bytes)
    return value


@pytest.fixture
def base_job(registry: TemplateRegistry) -> dict[str, object]:
    """Canonical mutable JOB document for compiler and model tests.

    A new dictionary is returned for every test so in-place mutations cannot
    leak across parametrized or independently collected test cases.
    """
    asset = registry.list()[0]
    document: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "base-job",
        "model": {
            "output_path": "model.hrx",
            "template": {"id": asset.template_id, "sha256": asset.sha256},
            "patches": [],
        },
        "workflow": {},
        "metadata": {},
    }
    return deepcopy(document)
