import pytest
from pydantic import ValidationError

from histra_builder.models import JobSpec


@pytest.mark.parametrize("path", ["../x.hrx", "/x.hrx", "x\\y.hrx", "x.xml", "folder/"])
def test_output_path_rejects_unsafe_values(base_job, path):
    base_job["model"]["output_path"] = path
    with pytest.raises(ValidationError):
        JobSpec.model_validate(base_job)


def test_patch_operands_are_validated(base_job):
    base_job["model"]["patches"] = [{"op": "set_attribute", "xpath": "/x"}]
    with pytest.raises(ValidationError):
        JobSpec.model_validate(base_job)


def test_extra_fields_are_rejected(base_job):
    base_job["surprise"] = True
    with pytest.raises(ValidationError):
        JobSpec.model_validate(base_job)
