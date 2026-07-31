from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON using a stable, standards-compliant representation.

    RFC 8259 does not permit NaN or infinite numeric values. Rejecting them is
    essential because the canonical bytes are used for provenance hashes and
    must be portable across JSON implementations.
    """
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonical JSON: {exc}") from exc
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def job_sha256(job: Any) -> str:
    return sha256_hex(canonical_json_bytes(job))
