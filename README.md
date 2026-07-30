# histra-job-builder

A deterministic compiler for the HiStrA distributed job platform.

The Builder has one responsibility:

```text
canonical JOB + immutable source template -> generated HRX + provenance
```

It does **not** own queues, runners, leases, HTTP endpoints, or result storage. The
Server imports this package and invokes it in-process. Keeping it as a separate
Python package gives the compiler an explicit API and an independently testable
reproducibility boundary without adding another network service.

## Contract

A JOB is JSON with four top-level fields:

```json
{
  "schema_version": "1.0",
  "job_id": "campaign-a-0001",
  "model": {
    "output_path": "models/campaign-a-0001.hrx",
    "template": {
      "id": "bridge-base-v1",
      "sha256": "<64 lowercase hex characters>"
    },
    "patches": [
      {
        "op": "set_attribute",
        "xpath": "//Span[@id='main']",
        "attribute": "length",
        "value": 27.5
      }
    ]
  },
  "workflow": {
    "analyses": [{"id": "dead-load"}]
  },
  "metadata": {
    "campaign": "parameter-study-1",
    "seed": 182731
  }
}
```

`workflow` is delivered unchanged to the Runner. `metadata` is provenance and
campaign information. The Builder only interprets `model`.

## Template rule

Generated HRX files are disposable. A source template is not. Imported models
may contain information that cannot be represented safely as small JSON edits,
so the deployment keeps one immutable, content-addressed source HRX and stores
only its ID and SHA-256 in each JOB.

The registry layout is deliberately simple:

```text
templates/
  bridge-base-v1.hrx
  arch-base-v3.hrx
```

The Server should mount this directory read-only. A digest mismatch is a hard
build failure.

## Patch operations

Patches are ordered and deterministic:

- `set_attribute`: set an XML attribute on every selected element.
- `set_text`: replace text on every selected element.
- `delete`: remove every selected element.
- `replace_xml`: replace every selected element with the supplied fragment.
- `append_xml`: append the supplied fragment to every selected element.

An XPath that matches nothing is an error. XML external entities and network
access are disabled. A JOB with no patches returns the template bytes exactly,
which provides a lossless `HRX -> JOB -> HRX` import path.

Domain-specific generators—mesh generation, geometry synthesis, randomized
models—should be implemented as compiler plugins that produce these same
stable artifacts. Their random seed and generator version belong in the JOB.

## Python API

```python
from histra_builder import TemplateRegistry, compile_job

artifact = compile_job(job, TemplateRegistry("./templates"))
artifact.hrx_bytes
artifact.provenance
```

## CLI

```bash
histra-builder compile job.json --templates ./templates --output model.hrx
histra-builder import source.hrx \
  --templates ./templates \
  --template-id source-v1 \
  --job-id imported-001 \
  --job-output job.json
```

## Tests

```bash
python -m pip install -e '.[test]'
pytest
```

The coverage gate is 90% branch-aware coverage.
