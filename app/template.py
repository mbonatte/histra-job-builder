from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
from typing import Iterable

from lxml import etree

from .schemas import GenerationRequest, MaterialPatch, SupportPatch, SpanPatch
from .xml_utils import (
    attr_text,
    clone,
    direct_children,
    ensure_child,
    first_direct,
    parse_xml,
    set_attributes,
    vec_text,
)


class TemplateRepository:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> etree._ElementTree:
        return parse_xml(self.path)


class TemplateRegistry:
    """Resolve canonical and imported HRX templates without allowing path traversal."""

    def __init__(self, default_path: Path, imported_dir: Path | None = None):
        self.default_path = default_path.resolve()
        configured = os.getenv("HISTRA_TEMPLATE_DIR")
        self.imported_dir = Path(configured).resolve() if configured else (imported_dir or default_path.parent / "imported").resolve()
        self.imported_dir.mkdir(parents=True, exist_ok=True)

    def import_bytes(self, data: bytes, source_filename: str) -> tuple[Path, str]:
        digest = hashlib.sha256(data).hexdigest()
        suffix = Path(source_filename).suffix.lower() or ".hrx"
        if suffix != ".hrx":
            suffix = ".hrx"
        path = self.imported_dir / f"{digest}{suffix}"
        if not path.exists():
            path.write_bytes(data)
        return path, digest

    def relative_name(self, path: Path) -> str:
        path = path.resolve()
        try:
            return path.relative_to(self.default_path.parent.resolve()).as_posix()
        except ValueError:
            return path.name

    def resolve(self, model_reference) -> Path:
        candidate = getattr(model_reference, "template_path", None) or getattr(model_reference, "path", None)
        if not candidate or candidate == self.default_path.name:
            return self.default_path
        raw = Path(str(candidate))
        if raw.is_absolute():
            resolved = raw.resolve()
            allowed_roots = [self.default_path.parent.resolve(), self.imported_dir]
            if not any(resolved == root or root in resolved.parents for root in allowed_roots):
                raise ValueError("model.template_path is outside the configured template directory")
            if not resolved.exists():
                raise FileNotFoundError(f"HRX template was not found: {candidate}")
            return resolved
        if any(part == ".." for part in raw.parts):
            raise ValueError("model.template_path must not contain '..'")
        for root in (self.default_path.parent.resolve(), self.imported_dir):
            resolved = (root / raw).resolve()
            if (resolved == root or root in resolved.parents) and resolved.exists():
                return resolved
        # Imported JSON may contain only the digest filename.
        resolved = (self.imported_dir / raw.name).resolve()
        if resolved.exists():
            return resolved
        # Generated runner jobs point model.path to the output artifact.  When
        # no explicit template_path/import metadata is present, regeneration
        # remains backward-compatible and uses the canonical model.hrx.
        if getattr(model_reference, "template_path", None) is None and getattr(model_reference, "imported", None) is None:
            return self.default_path
        raise FileNotFoundError(f"HRX template was not found: {candidate}")


class TemplatePatcher:
    def __init__(self, request: GenerationRequest):
        self.request = request
        self.warnings: list[str] = []

    @staticmethod
    def _patch_model(element: etree._Element, patch) -> None:
        values = patch.model_dump(exclude_none=True)
        values.pop("Origin", None)
        values.pop("AbutmentKind", None)
        set_attributes(element, values)
        if getattr(patch, "AbutmentKind", None) is not None:
            element.set("AbutmentKind", str(patch.AbutmentKind))
        if getattr(patch, "Origin", None) is not None:
            reference = ensure_child(element, "ReferenceSystem")
            reference.set("Origin", vec_text(patch.Origin))

    def patch(self, tree: etree._ElementTree) -> etree._ElementTree:
        root = tree.getroot()
        if root.get("WizardType") != "RailBridge":
            raise ValueError("model.hrx is not a RailBridge template")
        wizard = first_direct(root, "WizardData")
        if wizard is None:
            raise ValueError("model.hrx does not contain WizardData")

        self._patch_bridge_definition(wizard)
        self._patch_sequence(wizard)
        self._patch_elevations(wizard)
        self._patch_materials(root)
        self._patch_advanced_options(root)
        root.set("GDL", "0")
        return tree

    def _patch_bridge_definition(self, wizard: etree._Element) -> None:
        bridge = first_direct(wizard, "BridgeDefinition")
        if bridge is None:
            raise ValueError("WizardData/BridgeDefinition is missing")
        patch_values = self.request.Geometry.BridgeDefinition.model_dump(exclude_none=True)
        set_attributes(bridge, patch_values)

        lanes = self.request.Geometry.Lanes
        if lanes is None:
            return
        lane_root = ensure_child(bridge, "Corsie")
        archetypes = direct_children(lane_root, "Corsia")
        for child in list(lane_root):
            lane_root.remove(child)
        for index, lane_patch in enumerate(lanes):
            source = archetypes[index] if index < len(archetypes) else (archetypes[-1] if archetypes else None)
            lane = clone(source, "Corsia")
            values = lane_patch.model_dump(exclude_none=True)
            values.setdefault("Key", str(index))
            values.setdefault("Description", lane_patch.Description or lane_patch.Name)
            set_attributes(lane, values)
            lane.set("Key", str(values.get("Key", index)))
            lane_root.append(lane)

        declared_width = float(bridge.get("Width", "0"))
        lane_width = sum(lane.Width for lane in lanes)
        if abs(declared_width - lane_width) > 1e-6:
            raise ValueError(
                f"Lane widths sum to {lane_width}, but BridgeDefinition.Width is {declared_width}"
            )

    def _select_abutment_archetype(self, wizard: etree._Element, patch: SupportPatch, index: int) -> etree._Element | None:
        candidates = direct_children(wizard, "Abutment")
        desired = (patch.AbutmentKind or ("Sinistra" if index == 0 else "Destra")).lower()
        for candidate in candidates:
            kind = candidate.get("AbutmentKind", "").lower()
            if ("sinistra" in desired or "left" in desired) and ("sinistra" in kind or "left" in kind):
                return candidate
            if ("destra" in desired or "right" in desired) and ("destra" in kind or "right" in kind):
                return candidate
        return candidates[index] if index < len(candidates) else (candidates[0] if candidates else None)

    def _patch_sequence(self, wizard: etree._Element) -> None:
        geometry = self.request.Geometry
        span_archetype = first_direct(wizard, "Span")
        pier_archetype = first_direct(wizard, "Pier")
        abutment_archetypes = direct_children(wizard, "Abutment")
        elevation_ref = first_direct(wizard, "Elevations")

        existing = [child for child in direct_children(wizard) if child.tag in {"Abutment", "Span", "Pier"}]
        for child in existing:
            wizard.remove(child)

        sequence: list[etree._Element] = []
        left_source = next((a for a in abutment_archetypes if "sinistra" in a.get("AbutmentKind", "").lower() or "left" in a.get("AbutmentKind", "").lower()), abutment_archetypes[0] if abutment_archetypes else None)
        left = clone(left_source, "Abutment")
        self._patch_model(left, geometry.Abutments[0])
        left.set("AbutmentKind", geometry.Abutments[0].AbutmentKind or "Sinistra")
        sequence.append(left)

        for index, span_patch in enumerate(geometry.Spans):
            span = clone(span_archetype, "Span")
            self._patch_model(span, span_patch)
            sequence.append(span)
            if index < len(geometry.Piers):
                pier = clone(pier_archetype, "Pier")
                self._patch_model(pier, geometry.Piers[index])
                sequence.append(pier)

        right_source = next((a for a in abutment_archetypes if "destra" in a.get("AbutmentKind", "").lower() or "right" in a.get("AbutmentKind", "").lower()), abutment_archetypes[-1] if abutment_archetypes else None)
        right = clone(right_source, "Abutment")
        self._patch_model(right, geometry.Abutments[1])
        right.set("AbutmentKind", geometry.Abutments[1].AbutmentKind or "Destra")
        sequence.append(right)

        insertion_index = wizard.index(elevation_ref) if elevation_ref is not None else len(wizard)
        for offset, element in enumerate(sequence):
            wizard.insert(insertion_index + offset, element)

    def _patch_elevations(self, wizard: etree._Element) -> None:
        root = ensure_child(wizard, "Elevations")
        items = ensure_child(root, "Elevations")
        archetype = first_direct(items, "Elevation")
        for child in list(items):
            items.remove(child)
        for item_patch in self.request.Geometry.Elevations.Elevations:
            item = clone(archetype, "Elevation")
            set_attributes(item, item_patch.model_dump(exclude_none=True))
            items.append(item)

        layers = self.request.Geometry.Elevations.Layers
        if layers:
            existing = {child.tag: copy.deepcopy(child) for child in direct_children(root) if child.tag.startswith("Layer")}
            for child in list(root):
                if isinstance(child.tag, str) and child.tag.startswith("Layer"):
                    root.remove(child)
            for layer_patch in layers:
                tag = layer_patch.Tag
                layer = clone(existing.get(tag), tag)
                values = layer_patch.model_dump(exclude_none=True)
                values.pop("Tag", None)
                set_attributes(layer, values)
                root.append(layer)

    def _patch_materials(self, root: etree._Element) -> None:
        templates = direct_children(root, "Template")
        by_key = {item.get("Key"): item for item in templates if item.get("Key")}
        by_name = {item.get("Name"): item for item in templates if item.get("Name")}
        for patch in self.request.Materials:
            target = by_key.get(str(patch.Key))
            if target is None:
                target = by_name.get(patch.Name)
            if target is None:
                raise KeyError(f"Material Key={patch.Key!r}, Name={patch.Name!r} was not found in model.hrx")
            if target.get("Name") != patch.Name:
                raise ValueError(
                    f"Material key {patch.Key} is named {target.get('Name')!r} in model.hrx, "
                    f"not {patch.Name!r}"
                )
            for key, value in patch.model_dump(exclude_none=True).items():
                if key not in {"Key", "Name"}:
                    target.set(key, str(value))

    def _patch_advanced_options(self, root: etree._Element) -> None:
        options = first_direct(root, "AdvancedOptionsDefault")
        if options is None:
            options = etree.Element("AdvancedOptionsDefault")
            root.insert(3, options)
        values = self.request.advanced_options.model_dump(exclude_none=True)

        # HiStrA's global target-mesh control updates the bridge definition and
        # both bridge-specific mesher limits together.  Component-specific
        # controls can be exposed later; for now the public Nl field is the
        # authoritative value so imported jobs behave like the software UI.
        nl = self.request.Geometry.BridgeDefinition.Nl
        if nl is not None:
            for key in ("ArcoMesherQuadLengthMax", "WallMesherQuadLengthMax"):
                supplied = values.get(key)
                if supplied is not None and abs(float(supplied) - float(nl)) > 1e-9:
                    self.warnings.append(
                        f"Config.{key}={supplied} was synchronized to BridgeDefinition.Nl={nl}"
                    )
                values[key] = nl
        set_attributes(options, values)
