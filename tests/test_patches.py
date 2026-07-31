from lxml import etree
from histra_builder import compile_job, job_from_hrx

def test_ordered_patch_changes_attribute(hrx_bytes, registry):
    job = job_from_hrx(hrx_bytes, job_id="bridge-1", template_id="bridge-1", registry=registry)
    document = job.model_dump(mode="json")
    document["model"]["patches"] = [{
        "op": "set_attribute", "xpath": "/RailBridge/WizardData/BridgeDefinition",
        "attribute": "Width", "value": 5.5,
    }]
    artifact = compile_job(document, registry)
    root = etree.fromstring(artifact.hrx_bytes)
    assert root.xpath("/RailBridge/WizardData/BridgeDefinition")[0].get("Width") == "5.5"
