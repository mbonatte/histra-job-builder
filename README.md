# HiStrA Job Builder 1.2.0

`histra-job-builder` is the engineering boundary between canonical JOB documents and the official HiStrA `.hrx` format.

## Capabilities

- Lossless import of an existing HRX into an immutable template plus canonical JOB.
- Deterministic compilation of canonical JOB patches back to HRX.
- Structural preview extraction from the actual `Node`/`Quad` geometry stored in HRX.
- HRX inventory and geometry validation for comparison with the official HiStrA software.
- Explicit scenario variants using JSON Pointer changes, without silently mutating the base JOB.
- CLI commands for import, compile, inspect, preview and variant generation.
- Interactive local web UI with live mesh preview, orbit/zoom, parameter editing and HRX export.

The importer deliberately creates a no-patch JOB. Compiling that JOB returns the original HRX bytes exactly. Changes are represented as ordered XML patch operations, preserving provenance.

## Install

```bash
python -m pip install -e .
```

## CLI

```bash
histra-builder import bridge.hrx --job-id bridge-base --template-id bridge-base --registry ./templates --output job.json
histra-builder inspect bridge.hrx
histra-builder preview-job job.json --registry ./templates --output preview.json
histra-builder compile job.json --registry ./templates --output model.hrx
histra-builder variants job.json variants.json --output-dir ./generated-jobs
histra-builder generate-random model.hrx --output-dir ./generated_jobs --count 5 --seed 20260817
histra-builder ui
```

The same generator is available as `python -m histra_builder generate-random ...`.

## Interactive bridge UI

Launch the local editor:

```bash
histra-builder ui
# or:
python -m histra_builder ui --port 8765 --no-open
```

It serves a dependency-free browser UI at `http://127.0.0.1:8765/` and opens it
automatically. The editor uses the same C#-parity mesher as the CLI, so the
preview and exported HRX come from the same geometry path.

The UI supports:

- live editing of mesh size, elevations, transverse strips, spans, piers, footing
  wings and abutments;
- adding/removing spans and strips with automatic pier-count synchronisation;
- orbit (drag), zoom (wheel) and fit-to-view controls;
- fill/wireframe/node overlays, support (GLR/restraint) markers and material,
  group or depth colouring;
- one-click HRX export of the current model.

HTTP endpoints used by the page:

```text
GET  /                 editor page
GET  /api/default      starter payload
GET  /api/health       health check
POST /api/preview      build a JSON mesh preview
POST /api/export       build and download the HRX
```

The browser payload is a compact JSON description of strips, spans, piers and
abutments; `histra_builder.ui.build_preview()` and `export_hrx()` expose the same
functions for scripted use.

## Random scour workflow jobs

`generate-random` imports a reference HRX (e.g. `model.hrx`), verifies the scour
foundation exists and writes five reproducible scenario JOBs:

```text
generated_jobs/
    random_001/job.json
    ...
    random_005/job.json
    templates/model.hrx
```

Every JOB keeps the fixed analysis sequence `Vert` -> `Scour_1` -> `Scour_2` with
semantic interface changes (`pier_1` scoured to absolute fractions 0.2 and 0.4,
never resolved into concrete HRX interface IDs), plus a seeded randomisation of
pier/foundation WizardData parameters (pier height, foundation height, plan
sizes, subgrade modulus) applied as deterministic XML patches. Generation fails
clearly when the model cannot be loaded, `pier_1` is missing, sampled parameters
are invalid, or a JOB cannot compile or round-trip through JSON.

## Variant definition

```json
{
  "variants": [
    {
      "job_id": "bridge-scour-050",
      "changes": [
        {"path": "/metadata/scour_normalized", "value": 0.5},
        {"path": "/model/patches/0/value", "value": -0.05}
      ]
    }
  ]
}
```

Each generated document is validated as a canonical JOB before it is returned.

## Tests

Install the solver integration dependency and run the suite:

```bash
python -m pip install -e ".[test]"
python -m pip install "histra-python @ git+https://github.com/mbonatte/histra-python.git@v1.2.2"
pytest
```

The six parity/integration modules that need `histra-python` are skipped when
that package is not installed; installing it is required for the full native
solver round-trip coverage used by CI. `histra-python` requires Python 3.12+,
so the Python 3.11 CI leg runs the core suite only.
