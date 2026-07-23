# HiStrA HRX Work-Job Generator

Python/FastAPI service for creating HiStrA RailBridge models from a structured
work-job JSON document.

The browser is a thin client. Python performs template patching, mesh creation,
model-point creation, HRX serialization, validation, and work-job generation.

## Canonical template

The service stores the canonical source model at:

```text
app/templates/model.hrx
```

The input work job normally references it as:

```json
"model": {"path": "model.hrx"}
```

The server currently uses the configured canonical template rather than reading
an arbitrary client-side path. In the generated work-job JSON, `model.path` is
changed to the generated artifact name:

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

## Not implemented yet

- applying `analyses[].interfaces` during the analysis run;
- component-specific mesh policies for arches, backfill, piers, and foundations;
- additional model-point families;
- geometry-attached load-position generation;
- persistence/database integration with the VPS work-job queue.
