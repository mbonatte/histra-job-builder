# HiStrA HRX Work-Job Generator — Reference Mesh v6

## Model1 target-size reference behavior

This revision uses the software-generated `Model1_101.hrx` as a regression
oracle. Imported models no longer switch blindly to the Python remesher whenever
`BridgeDefinition.Nl` changes. The service now:

1. patches the requested WizardData and advanced options;
2. confirms that no geometric property other than the target mesh size changed;
3. computes a numbering-independent discretisation signature for the imported
   and requested target sizes;
4. preserves the original HiStrA nodes, quads, restraints, `NodeC` objects,
   model points, and load topology when those signatures are identical;
5. activates the Python remesher only when the signature genuinely changes.

For the supplied model, `Nl=100` and `Nl=101` are reference-equivalent. Both
therefore retain exactly 3,286 nodes and 2,644 quads. The generated `Nl=101`
geometry matches the software output independently of node/quad numbering.

The global target value is synchronized across:

```text
WizardData/BridgeDefinition/@Nl
AdvancedOptionsDefault/@ArcoMesherQuadLengthMax
AdvancedOptionsDefault/@WallMesherQuadLengthMax
```

The generated work-job JSON is synchronized in the same way. Separate
component-specific target lengths remain a future extension.

`ModelLibrary.dll` and `Triangle.dll` were used only as reference inputs. They
are not loaded at runtime and are not redistributed with this project.


Python/FastAPI service for creating HiStrA RailBridge models from a structured
work-job JSON document.

The browser is a thin client. Python performs template patching, mesh creation,
model-point creation, HRX serialization, validation, and work-job generation.

## Regression validation

The test suite includes both software-generated fixtures:

```text
tests/fixtures/Model1.hrx       # Nl = 100
tests/fixtures/Model1_101.hrx   # Nl = 101
```

The `Nl=101` regression requires:

- 3,286 nodes and 2,644 quads;
- identical node-coordinate multiset;
- identical semantic quad geometry, thickness, layer, and material;
- identical materials and analyses;
- synchronized HRX target-mesh attributes;
- valid internal references.

Run with:

```bash
python -m pytest -q
```

## Canonical template

The service stores the canonical source model at:

```text
app/templates/model.hrx
```

The input work job normally references it as:

```json
"model": {"path": "model.hrx"}
```

The server also maintains an imported-template registry under
`app/templates/imported/`. Importing an HRX stores it by SHA-256 and records the
relative `model.template_path` in the work job. This lets an imported job retain
all version-specific data that is not represented by the editable JSON fields.
In the generated work-job JSON, `model.path` is changed to the generated artifact
name while `model.template_path` remains available for regeneration:

```json
"model": {"path": "first-bridge.hrx"}
```

## One document, two responsibilities

The request JSON contains two groups of information.

### Work-runner fields

These lowercase fields are preserved in the generated work-job JSON and are
**not written into the HRX**:

- `schema_version`
- `job_id`
- `model`
- `mesh`
- `scour`
- `analyses[].timeout_seconds`
- `analyses[].interfaces`
- `analyses[].outputs`
- `validation`
- `metadata`

### Model-generation fields

These fields control the generated HRX:

- `Geometry`
- `Materials`
- `AnalysisParameters`
- `Config`
- `Mesh`
- analysis names and supported HRX analysis attributes such as
  `ConvergenceTolerance` and `NumberOfEigenModes`

The lowercase `mesh` object is runner configuration. The uppercase `Mesh`
object controls mesh generation. They intentionally coexist in the same JSON.

## Artifact naming

`job_id` is the artifact basename. For:

```json
"job_id": "first-bridge"
```

the API produces:

```text
first-bridge.hrx
first-bridge.json
first-bridge.report.json
first-bridge.zip
```

`job_id` must contain only letters, numbers, `.`, `_`, or `-`, and must not
include the `.hrx` extension.

## Analyses

The ordered lowercase `analyses` list controls both the work runner and the
analysis records created in the HRX.

```json
{
  "name": "Modal_1",
  "timeout_seconds": 50,
  "NumberOfEigenModes": 3,
  "interfaces": {
    "pier_1": {"downstream": 0.4}
  },
  "outputs": {
    "modal_contributions": {
      "enabled": false,
      "top_n": 3
    }
  }
}
```

The generator selects analysis archetypes from `model.hrx` as follows:

1. exact template analysis name, when available;
2. an `AnalysisType=5` archetype for new names beginning with `Modal`;
3. an `AnalysisType=2` archetype for other new analysis names.

Runner-only properties such as timeout, requested outputs, and interface
removal ratios stay in the JSON. Supported HRX properties are applied to the
analysis element.

Interface deletion ratios are intentionally not encoded as static HRX changes.
They are retained for the analysis-time scour mutation workflow.

## Generated model points

The generator currently creates:

- pier centre/upstream/downstream at top and bottom;
- foundation centre/upstream/downstream at top and bottom;
- one crown point for every span.

Stable IDs are used, for example:

```text
Pier_1_center_top
Foundation_2_downstream_bottom
Span_3_crown
```

When displacement output is enabled and `model_point_ids` is empty, the
generated work-job JSON explicitly expands the list to all generated IDs. If a
non-empty list contains an unknown ID, generation fails with HTTP 422.

## API

### Inspect template

```http
GET /api/template
```

### Get the work-job JSON Schema

```http
GET /api/jobs/schema
```

### Get the example request

```http
GET /api/jobs/example
```

### Import an HRX as a work job

```http
POST /api/jobs/import
Content-Type: multipart/form-data
file=@Model1.hrx
```

The response is an editable work-job JSON containing the complete observed
WizardData attributes, lane definitions, backfill layer definitions, materials,
analyses, and advanced options. The uploaded HRX is registered as the source
template by SHA-256.

### Validate the full round trip

```http
POST /api/jobs/roundtrip/validate
Content-Type: multipart/form-data
file=@Model1.hrx
```

This endpoint performs `HRX → job JSON → HRX` and reports byte equality,
canonical XML equality, WizardData equality, node-coordinate equality, semantic
quad equality, material equality, and analysis equality.

### Preview model

```http
POST /api/jobs/preview
Content-Type: application/json
```

Returns the server-generated mesh, model points, analyses, warnings,
`job_id`, and the expected HRX filename.

### Generate HRX

```http
POST /api/jobs/generate/hrx
```

Returns `<job_id>.hrx` after referential validation.

### Generate runner-ready JSON

```http
POST /api/jobs/generate/json
```

Returns `<job_id>.json`. It preserves the execution contract and all
model-generation inputs for provenance, rewrites `model.path`, expands empty
model-point lists, and adds a `generated` section containing:

- template/version information;
- artifact names;
- generated model-point IDs and node keys;
- HRX validation counts and warnings;
- removed stale-object counts.

The generated JSON is accepted again by the preview/generation API. The
additional `generated` section is forward-compatible metadata.

### Generate validation report

```http
POST /api/jobs/generate/report
```

Returns `<job_id>.report.json`.

### Generate complete bundle

```http
POST /api/jobs/generate
```

or:

```http
POST /api/jobs/generate/bundle
```

Returns `<job_id>.zip` containing the HRX, generated work-job JSON, and report.

### Backward-compatible aliases

The following endpoints still work with the new work-job schema:

```text
POST /api/models/preview
POST /api/models/generate
POST /api/models/generate-report
```

## Browser workspaces

### Model Builder — `/generator`

The builder includes:

- geometry, lanes, spans, piers, abutments, and foundations;
- material patches;
- work-job identity, runner mesh stage, scour material mapping, validation,
  and metadata;
- ordered analyses with timeout, interface payload, outputs, convergence
  tolerance, and eigen-mode count;
- mesh and advanced HRX options;
- advanced JSON editing/import;
- direct HRX import into an editable work job;
- exact source-geometry preview for unchanged imported jobs;
- live server-generated Three.js preview;
- separate downloads for HRX, work-job JSON, and complete ZIP bundle.

### Model Viewer — `/viewer`

The viewer keeps the smoother standalone Three.js interaction model:

- Z-up orbiting with damping;
- screen-space panning;
- front/top/side/isometric views;
- quad selection and highlighted outlines;
- material/component/lane coloring;
- edges, nodes, model points, opacity, and thickness extrusion;
- local `.hrx`, `.xml`, or `.txt` file loading.

Both pages use `app/static/viewer-core.js`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000/generator
http://localhost:8000/viewer
http://localhost:8000/docs
```

## Docker

```bash
docker compose up --build -d
```

The service is exposed on port 8000.

## Tests

```bash
PYTHONPATH=. pytest -q
```

The tests verify:

- canonical template mesh counts;
- `Model1.hrx → job JSON → HRX` byte-exact round-trip;
- extraction and remeshing of variable arch thickness, raised spandrel lanes,
  shaped piers, foundations, and three cumulative backfill layers;
- observed Model1 arch divisions (`8, 12, 12, 12, 12`);
- geometrically valid Model1 remeshing at `Nl=99`, `100`, and `101`;
- material-only edits while preserving imported node/quad geometry;
- switching to the Python mesher after a geometry edit;
- referentially valid HRX generation;
- nonlinear/modal archetype selection;
- semantic model-point creation;
- job-ID-based filenames;
- generated work-job JSON and model-path rewriting;
- empty model-point-list expansion;
- generated JSON replay through the API;
- invalid model-point rejection;
- ZIP bundle generation;
- builder and viewer routes.

## Imported-model preservation and remeshing

For an imported job, the server compares stable section fingerprints:

- if all HRX-affecting fields are unchanged, the original source bytes are
  returned exactly;
- if materials, configuration, or analyses change while geometry does not, the
  original nodes, quads, restraints, loads, and model points are preserved;
- if `Geometry` or uppercase `Mesh` changes, the Python mesher rebuilds the
  geometry and validates it before preview or export.

`Model1.hrx` is included as a regression fixture for the outlier bridge features
that previously caused the preview to collapse after changing `Nl`. The Python
mesher now supports:

- cumulative `H1`, `H2`, and `H3` backfill layers with independent materials;
- lane `Height`, including raised outer spandrel-wall bands;
- circular span geometry with variable `Tb`/`Tt` ring thickness;
- forced arch divisions at the crown and backfill-layer intersections;
- `b1`/`b2`/`b3` longitudinal pier variation;
- `w1`/`w2`/`w3` transverse pier variation and vertical alignment;
- foundations following the shaped pier base;
- clean support/cap stitching without the source model's near-duplicate top-pier
  nodes.

The geometry validator rejects a remesh containing non-finite coordinates,
missing node references, repeated quad nodes, zero edges, zero projected area,
or self-intersecting quads. Invalid meshes therefore cannot be sent to the
viewer or serialized into an HRX.

For the supplied `Model1.hrx`, the observed arch subdivisions are reconstructed
as `8, 12, 12, 12, 12`. The exact imported mesh remains available at its
original `Nl=100`; changing `Nl` to 99 or 101 activates the clean Python remesh.
The remeshed topology is intentionally not byte-identical because it removes
HiStrA's mismatched/near-duplicate support nodes.

## Mesh-size behavior

`Nl` is a target size, not a requested element count. Crossing a component
thickness can therefore change the number of rows discontinuously. In Model1,
a 100-unit arch ring produces two radial rows at `Nl=99`, but one row at
`Nl=100` or `Nl=101`. This is expected; all three cases are covered by the
regression suite and must pass geometric and HRX referential validation.

## Not implemented yet

- applying `analyses[].interfaces` during the analysis run;
- full advanced non-circular span laws when their advanced-mode flags are active;
- component-specific mesh policies for arches, backfill, piers, and foundations;
- additional model-point families;
- geometry-attached load-position generation;
- persistence/database integration with the VPS work-job queue.
