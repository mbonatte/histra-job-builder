from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
_SHA256 = r"^[0-9a-f]{64}$"


class TemplateRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=_SAFE_ID)
    sha256: str = Field(pattern=_SHA256)


class PatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_attribute", "set_text", "delete", "replace_xml", "append_xml"]
    xpath: str = Field(min_length=1)
    attribute: str | None = None
    value: str | int | float | bool | None = None
    xml: str | None = None

    @model_validator(mode="after")
    def validate_operands(self) -> "PatchOperation":
        if self.op == "set_attribute":
            if not self.attribute:
                raise ValueError("set_attribute requires attribute")
            if self.value is None:
                raise ValueError("set_attribute requires value")
        elif self.op == "set_text" and self.value is None:
            raise ValueError("set_text requires value")
        elif self.op in {"replace_xml", "append_xml"} and not self.xml:
            raise ValueError(f"{self.op} requires xml")
        return self


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_path: str = "model.hrx"
    template: TemplateRef
    patches: list[PatchOperation] = Field(default_factory=list)

    @field_validator("output_path")
    @classmethod
    def output_path_is_safe(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or value.endswith("/") or "\\" in value:
            raise ValueError("output_path must be a safe relative POSIX path")
        if path.suffix.lower() != ".hrx":
            raise ValueError("output_path must end with .hrx")
        return value


class JobSpec(BaseModel):
    """Stable contract shared by authors, Server, Builder and Runner."""
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    job_id: str = Field(pattern=_SAFE_ID)
    model: ModelSpec
    workflow: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
