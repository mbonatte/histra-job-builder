# HiStrA Job Builder Agent Operating Manual

Quick-start guide, architectural contracts, and operating rules for AI agents working in `histra-job-builder`.

---

## 1. Project Overview & Role

`histra-job-builder` is the engineering boundary between canonical JOB specifications, parametric finite-element bridge generation (ported from C#), and official HiStrA `.hrx` models.

It owns:
1. **Parametric Bridge Generation**: Procedurally meshing masonry arch bridges into valid HiStrA finite-element models (`.hrx`).
2. **Lossless Import**: Converting official `.hrx` files into immutable templates and no-patch canonical `JobSpec` documents.
3. **Deterministic Compilation**: Applying ordered XML patch operations to compile canonical jobs back to exact `.hrx` bytes.
4. **Scour Scenario Generation**: Reproducible multi-stage scour portfolio generation (`Vert` -> `Scour_1` -> `Scour_2`).
5. **Structural Inspection**: Geometry preview extraction, bounding boxes, element counts, and schema validation.

---

## 2. Architecture & Key Modules

```text
src/histra_builder/
├── generator/            # Ported C# bridge generation & FE meshing
│   ├── parameters.py     # BridgeSpec, SpanSpec, PierSpec, AbutmentSpec
│   ├── geometry.py       # Elliptical arch math, quad kinematics, triads
│   ├── materials.py      # HiStrA constitutive templates (18, 22, 141, 146, 147)
│   ├── restraints.py     # Fully-fixed boundary restraints & NodeC anchors
│   ├── mesher.py         # 2D FE quad mesher (arch, spandrel, pier, footing)
│   ├── hrx_writer.py     # HiStrA XML schema serializer with gravity loads
│   └── bridge_builder.py # High-level API: generate_bridge_hrx(spec)
├── compiler.py           # Deterministic XML patch compiler
├── importer.py           # Lossless HRX -> template + JobSpec importer
├── inspector.py          # Node/Quad inspection & preview extraction
├── models.py             # Pydantic schema for canonical JobSpec
├── scenarios.py          # Random 5-JOB scour scenario generation
├── templates.py          # TemplateRegistry for immutable HRX assets
└── variants.py           # JSON Pointer variant generator
```

---

## 3. Non-Negotiable Invariants

### 1. Lossless Round-Trip Guarantee
- An imported official `.hrx` produces a no-patch `JobSpec`.
- Compiling that `JobSpec` against the stored template MUST reproduce the original HRX bytes exactly (`assert artifact.hrx_bytes == template_bytes`).

### 2. Quad Mesh Geometry & Orientation
- All generated `<Quad>` finite elements must have **positive area** in the X-Z plane.
- Quad vertices must follow consistent ordering with computed corner angles, diagonals, and local orthonormal reference frames ($E_1, E_2, E_3$).
- Elements must not overlap or contain degenerate edge lengths.

### 3. Solver Boundary Restraint Invariants
- `histra-python`s `contact_geometry.py` strictly requires:
  - `computational_element_type == "Quad"`.
  - Restraint stiffness $K = [-1, -1, -1, -1, -1, -1]$ (fully fixed; elastic/free DOFs are rejected).
  - 4 contact points matching the quad lateral contact face.
- Restraints must only be placed on foundation footing bottom quads.

### 4. Equilibrium Convergence Criteria
- Generated bridge analyses (`Vert`, `Scour_1`, `Scour_2`) MUST be configured with `AdapticConvergenceCriteria="ForceMoment"`.
- Do NOT use `"Work"` criterion for generated bridges; under `histra-python`s default `equilibrium_policy="error"`, `"Work"` fails independent residual force equilibrium audits.

### 5. Displacement Monitoring Points
- `<ModelPoint>` elements must be generated at critical monitoring locations (mid-span bottom arch, pier cap tops) so `histra-python`s `project_displacements` produces output rows.

---

## 4. Environment & Verification

### Python Environment
- Uses Python 3.11–3.14.
- Dependencies: `lxml>=5.2`, `pydantic>=2.7`.

### Running Tests
```bash
# Run full builder test suite (86+ tests)
pytest -ra

# Run parametric generator tests
pytest tests/test_parametric_generator.py

# Run random scour scenario tests
pytest tests/test_random_scenarios.py

# Check test coverage (threshold: 90%)
pytest --cov=histra_builder --cov-report=term-missing
```

---

## 5. Primary Python API

```python
from histra_builder import (
    BridgeSpec,
    SpanSpec,
    PierSpec,
    generate_bridge_hrx,
    compile_job,
    job_from_hrx,
    inspect_hrx,
)

# 1. Generate parametric bridge model
spec = BridgeSpec(
    num_spans=2,
    spans=[SpanSpec(span_id=1, length=400.0, arch_rise=100.0), SpanSpec(span_id=2, length=400.0, arch_rise=100.0)],
    piers=[PierSpec(pier_id=1, height=150.0, width_top=60.0)],
)
hrx_bytes = generate_bridge_hrx(spec)

# 2. Inspect generated HRX
inspection = inspect_hrx(hrx_bytes)
assert inspection.validation["valid"] is True
```
