"""Parametric bridge specifications and data models."""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, model_validator


class SpanSpec(BaseModel):
    """Geometric and material definition for an individual arch span."""

    length: float = Field(default=400.0, gt=50.0, description="Clear span length in cm")
    rise: float = Field(default=100.0, gt=10.0, description="Arch rise at crown in cm")
    thickness_springer: float = Field(default=35.0, gt=5.0, description="Arch thickness at springers in cm")
    thickness_crown: float = Field(default=25.0, gt=5.0, description="Arch thickness at crown in cm")
    material_key: int = Field(default=18, description="Material template key for arch masonry")
    cap_material_key: int = Field(default=22, description="Material template key for pier cap / springings")
    backfill_material_key: int = Field(default=19, description="Material template key for backfill")
    spandrel_material_key: int = Field(default=141, description="Material template key for spandrel walls")


class PierSpec(BaseModel):
    """Geometric and foundation specification for an intermediate bridge pier."""

    height: float = Field(default=150.0, gt=20.0, description="Pier shaft height in cm")
    thickness: float = Field(default=60.0, gt=15.0, description="Pier shaft longitudinal thickness in cm")
    foundation_height: float = Field(default=60.0, gt=15.0, description="Foundation depth (Hf) in cm")
    foundation_length: float = Field(default=100.0, gt=15.0, description="Foundation longitudinal size (Bf) in cm")
    foundation_width: float = Field(default=200.0, gt=15.0, description="Foundation transverse size (Wf) in cm")
    subgrade_modulus_kz: float = Field(default=0.1, gt=0.0, description="Subgrade reaction modulus Kz")
    material_key: int = Field(default=18, description="Material template key for pier shaft")
    cap_height: float = Field(default=35.0, ge=0.0, description="Pier cap height in cm")
    foundation_material_key: int = Field(default=141, description="Material template key for foundation footing")
    cap_material_key: int = Field(default=22, description="Material template key for pier cap")


class AbutmentSpec(BaseModel):
    """Geometric and foundation specification for an end bridge abutment."""

    height: float = Field(default=0.0, ge=0.0, description="Abutment wall height below springing in cm")
    thickness: float = Field(default=70.0, gt=20.0, description="Abutment longitudinal thickness in cm")
    foundation_height: float = Field(default=0.0, ge=0.0, description="Abutment foundation depth in cm")
    foundation_length: float = Field(default=90.0, gt=20.0, description="Abutment foundation longitudinal size in cm")
    material_key: int = Field(default=18, description="Material template key for abutment masonry")
    cap_material_key: int = Field(default=22, description="Material template key for impost cap")
    backfill_material_key: int = Field(default=19, description="Material template key for backfill")
    spandrel_material_key: int = Field(default=141, description="Material template key for spandrel walls")
    foundation_material_key: int = Field(default=141, description="Material template key for foundation footing")


class BridgeSpec(BaseModel):
    """Top-level parametric bridge definition."""

    name: str = Field(default="ParametricBridge", description="Bridge identification name")
    width: float = Field(default=200.0, gt=20.0, description="Bridge deck transverse width in cm")
    target_mesh_size: float = Field(default=35.0, gt=5.0, description="Target quadrilateral element size in cm")
    num_transverse_strips: int = Field(default=1, ge=1, le=10, description="Number of transverse Quad slices")
    deck_clearance: float = Field(default=30.0, ge=10.0, description="Clearance from highest crown extrados to deck in cm")
    spans: List[SpanSpec] = Field(default_factory=lambda: [SpanSpec()])
    piers: List[PierSpec] = Field(default_factory=list)
    left_abutment: AbutmentSpec = Field(default_factory=AbutmentSpec)
    right_abutment: AbutmentSpec = Field(default_factory=AbutmentSpec)

    @model_validator(mode="after")
    def populate_and_validate_piers(self) -> BridgeSpec:
        num_spans = len(self.spans)
        if num_spans == 0:
            return self
        needed_piers = max(0, num_spans - 1)
        if len(self.piers) < needed_piers:
            diff = needed_piers - len(self.piers)
            for _ in range(diff):
                self.piers.append(PierSpec())
        elif len(self.piers) > needed_piers:
            self.piers = self.piers[:needed_piers]
        return self
