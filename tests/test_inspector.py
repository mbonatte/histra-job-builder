import pytest
from histra_builder import InvalidHrxError, inspect_hrx, job_from_hrx, preview_job

def test_extracts_actual_hrx_geometry(hrx_bytes):
    value = inspect_hrx(hrx_bytes)
    assert value.counts == {"nodes": 4, "quads": 1}
    assert value.bounds == {"min": [0.0, 0.0, 0.0], "max": [1.0, 0.0, 1.0]}
    assert value.materials == {"7": 1}
    assert value.validation["valid"] is True

def test_preview_compiles_job_first(hrx_bytes, registry):
    job = job_from_hrx(hrx_bytes, job_id="bridge-1", template_id="bridge-1", registry=registry)
    value = preview_job(job, registry)
    assert value["counts"]["quads"] == 1
    assert value["provenance"]["job_sha256"]

def test_rejects_malformed_hrx():
    with pytest.raises(InvalidHrxError):
        inspect_hrx(b"<RailBridge>")
