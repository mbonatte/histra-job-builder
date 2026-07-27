"""Stable identities shared by the builder, server and runner."""

from __future__ import annotations

import hashlib
import json
from typing import Any


BUILDER_VERSION = "0.6.0"
JOB_SCHEMA_VERSION = "1.0"
PACKAGE_PROTOCOL_VERSION = "1.1"


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    """Serialize only the authoritative JOB content deterministically."""

    cloned = json.loads(json.dumps(value))
    cloned.pop("attempt_id", None)
    metadata = cloned.setdefault("metadata", {})
    for key in (
        "job_sha256",
        "provenance",
        "submission_protocol",
        "idempotency_key",
        "import_validation",
    ):
        metadata.pop(key, None)
    return json.dumps(
        cloned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def job_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
