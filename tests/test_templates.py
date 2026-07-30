from pathlib import Path

import pytest

from histra_builder.errors import TemplateIntegrityError, TemplateNotFoundError
from histra_builder.templates import TemplateRegistry


def test_registry_rejects_missing_template(tmp_path: Path):
    with pytest.raises(TemplateNotFoundError):
        TemplateRegistry(tmp_path).load("missing", "0" * 64)


def test_registry_rejects_digest_mismatch(registry):
    with pytest.raises(TemplateIntegrityError):
        registry.load("base", "0" * 64)


def test_register_is_idempotent_for_same_bytes(tmp_path: Path):
    registry = TemplateRegistry(tmp_path)
    first = registry.register("base", b"<x/>")
    second = registry.register("base", b"<x/>")
    assert first.sha256 == second.sha256


def test_register_rejects_changed_content(tmp_path: Path):
    registry = TemplateRegistry(tmp_path)
    registry.register("base", b"<x/>")
    with pytest.raises(TemplateIntegrityError):
        registry.register("base", b"<y/>")
