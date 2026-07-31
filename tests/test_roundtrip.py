from histra_builder import compile_job, job_from_hrx

def test_import_compile_is_byte_exact(hrx_bytes, registry):
    job = job_from_hrx(hrx_bytes, job_id="bridge-1", template_id="bridge-1", registry=registry)
    artifact = compile_job(job, registry)
    assert artifact.hrx_bytes == hrx_bytes
    assert artifact.provenance["template_sha256"] == job.model.template.sha256
