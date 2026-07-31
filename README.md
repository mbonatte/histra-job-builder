# HiStrA Job Builder 1.1.0

`histra-job-builder` is the engineering boundary between canonical JOB documents and the official HiStrA `.hrx` format.

## Capabilities

- Lossless import of an existing HRX into an immutable template plus canonical JOB.
- Deterministic compilation of canonical JOB patches back to HRX.
- Structural preview extraction from the actual `Node`/`Quad` geometry stored in HRX.
- HRX inventory and geometry validation for comparison with the official HiStrA software.
- Explicit scenario variants using JSON Pointer changes, without silently mutating the base JOB.
- CLI commands for import, compile, inspect, preview and variant generation.

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
```

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
