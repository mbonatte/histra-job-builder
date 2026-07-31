import pytest
from histra_builder import VariantError, generate_variants, job_from_hrx

def test_variants_change_explicit_fields(hrx_bytes, registry):
    base = job_from_hrx(hrx_bytes, job_id="base", template_id="railbridge-base", registry=registry)
    variants = generate_variants(base, {"variants": [{
        "job_id": "scour-050",
        "changes": [{"path": "/metadata/scour_normalized", "value": 0.5}],
        "metadata": {"campaign": "sensitivity"},
    }]})
    assert variants[0].job_id == "scour-050"
    assert variants[0].metadata["scour_normalized"] == 0.5
    assert variants[0].metadata["variant_of"] == "base"

def test_variants_reject_missing_paths(hrx_bytes, registry):
    base = job_from_hrx(hrx_bytes, job_id="base", template_id="railbridge-base", registry=registry)
    with pytest.raises(VariantError):
        generate_variants(base, {"variants": [{"job_id": "bad", "changes": [{"path": "/missing/value", "value": 1}]}]})
