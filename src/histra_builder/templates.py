from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .canonical import sha256_hex
from .errors import TemplateIntegrityError, TemplateNotFoundError

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class TemplateAsset:
    template_id: str
    path: Path
    data: bytes
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {"id": self.template_id, "sha256": self.sha256, "size_bytes": len(self.data)}


class TemplateRegistry:
    """Filesystem-backed registry of immutable source HRX assets."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).resolve()

    def path_for(self, template_id: str) -> Path:
        if not _SAFE_ID.fullmatch(template_id):
            raise TemplateNotFoundError("invalid template id")
        return self.root / f"{template_id}.hrx"

    def load(self, template_id: str, expected_sha256: str) -> TemplateAsset:
        path = self.path_for(template_id)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise TemplateNotFoundError(f"template {template_id!r} does not exist") from exc
        digest = sha256_hex(data)
        if digest != expected_sha256:
            raise TemplateIntegrityError(
                f"template {template_id!r} digest mismatch: expected {expected_sha256}, got {digest}"
            )
        return TemplateAsset(template_id, path, data, digest)

    def register(self, template_id: str, data: bytes, *, overwrite: bool = False) -> TemplateAsset:
        if not data:
            raise TemplateIntegrityError("cannot register an empty HRX template")
        path = self.path_for(template_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = "wb" if overwrite else "xb"
        try:
            with path.open(flags) as handle:
                handle.write(data)
        except FileExistsError:
            existing = path.read_bytes()
            if existing != data:
                raise TemplateIntegrityError(
                    f"template {template_id!r} already exists with different content"
                )
        final = path.read_bytes()
        return TemplateAsset(template_id, path, final, sha256_hex(final))

    def list(self) -> list[TemplateAsset]:
        if not self.root.exists():
            return []
        assets: list[TemplateAsset] = []
        for path in sorted(self.root.glob("*.hrx"), key=lambda item: item.name.lower()):
            data = path.read_bytes()
            assets.append(TemplateAsset(path.stem, path, data, sha256_hex(data)))
        return assets
