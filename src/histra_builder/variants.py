from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .errors import VariantError
from .models import JobSpec


class VariantChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    value: Any


class VariantDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    changes: list[VariantChange] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VariantSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variants: list[VariantDefinition] = Field(min_length=1, max_length=10000)


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise VariantError(f"JSON Pointer must start with '/': {pointer!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _assign(document: Any, pointer: str, value: Any) -> None:
    tokens = _tokens(pointer)
    if not tokens:
        raise VariantError("the JOB document root cannot be replaced")
    current = document
    for token in tokens[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise VariantError(f"invalid list index in {pointer!r}: {token!r}") from exc
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise VariantError(f"path does not exist: {pointer!r}")
    final = tokens[-1]
    if isinstance(current, list):
        try:
            current[int(final)] = deepcopy(value)
        except (ValueError, IndexError) as exc:
            raise VariantError(f"invalid list index in {pointer!r}: {final!r}") from exc
    elif isinstance(current, dict):
        current[final] = deepcopy(value)
    else:
        raise VariantError(f"path parent is not a container: {pointer!r}")


def apply_variant(base_job: JobSpec | dict[str, Any], definition: VariantDefinition | dict[str, Any]) -> JobSpec:
    base = base_job if isinstance(base_job, JobSpec) else JobSpec.model_validate(base_job)
    variant = definition if isinstance(definition, VariantDefinition) else VariantDefinition.model_validate(definition)
    document = deepcopy(base.model_dump(mode="json"))
    document["job_id"] = variant.job_id
    for change in variant.changes:
        if change.path in {"/schema_version", "/job_id"}:
            raise VariantError(f"reserved field cannot be changed through changes: {change.path}")
        _assign(document, change.path, change.value)
    document.setdefault("metadata", {}).update(variant.metadata)
    document["metadata"].setdefault("variant_of", base.job_id)
    try:
        return JobSpec.model_validate(document)
    except Exception as exc:
        raise VariantError(f"generated variant {variant.job_id!r} is not a valid JOB: {exc}") from exc


def generate_variants(base_job: JobSpec | dict[str, Any], variants: VariantSet | dict[str, Any]) -> list[JobSpec]:
    definitions = variants if isinstance(variants, VariantSet) else VariantSet.model_validate(variants)
    seen: set[str] = set()
    output: list[JobSpec] = []
    for definition in definitions.variants:
        if definition.job_id in seen:
            raise VariantError(f"duplicate variant job_id: {definition.job_id}")
        seen.add(definition.job_id)
        output.append(apply_variant(base_job, definition))
    return output
