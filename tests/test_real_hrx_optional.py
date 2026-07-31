"""Optional release gate for a real HRX produced by the official HiStrA software."""
from pathlib import Path
import os
import pytest
from histra_builder import TemplateRegistry, compile_job, inspect_hrx, job_from_hrx

PATH = os.getenv("HISTRA_REAL_HRX")

@pytest.mark.skipif(not PATH, reason="set HISTRA_REAL_HRX to run the official-file round-trip gate")
def test_official_hrx_roundtrip(tmp_path):
    source = Path(PATH).read_bytes()
    inspection = inspect_hrx(source)
    assert inspection.counts["nodes"] > 0
    assert inspection.counts["quads"] > 0
    registry = TemplateRegistry(tmp_path / "templates")
    job = job_from_hrx(source, job_id="official-real-file", template_id="official-real-file", registry=registry)
    assert compile_job(job, registry).hrx_bytes == source
