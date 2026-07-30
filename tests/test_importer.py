from histra_builder.compiler import compile_job
from histra_builder.importer import job_from_hrx
from histra_builder.templates import TemplateRegistry


def test_import_then_compile_is_byte_exact(tmp_path, template_bytes):
    registry = TemplateRegistry(tmp_path)
    job = job_from_hrx(
        template_bytes,
        job_id="imported-001",
        template_id="source-001",
        workflow={"analyses": ["static"]},
        registry=registry,
    )
    artifact = compile_job(job, registry)
    assert artifact.hrx_bytes == template_bytes
    assert job.workflow == {"analyses": ["static"]}
