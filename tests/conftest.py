from pathlib import Path
import pytest
from histra_builder import TemplateRegistry

@pytest.fixture
def hrx_bytes() -> bytes:
    return (Path(__file__).parent / "fixtures" / "simple.hrx").read_bytes()

@pytest.fixture
def registry(tmp_path: Path) -> TemplateRegistry:
    return TemplateRegistry(tmp_path / "templates")
