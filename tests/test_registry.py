import pytest
from histra_builder import TemplateIntegrityError, TemplateRegistry

def test_registry_is_immutable(tmp_path):
    registry = TemplateRegistry(tmp_path)
    registry.register("model", b"one")
    registry.register("model", b"one")
    with pytest.raises(TemplateIntegrityError):
        registry.register("model", b"two")
    assert [asset.template_id for asset in registry.list()] == ["model"]
