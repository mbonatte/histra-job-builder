# Changelog

## Unreleased

- Add seeded random five-JOB scour workflow generation (`generate-random` CLI command and `histra_builder.scenarios`).
- Keep scour semantics (`pier_1`, absolute fractions 0.2/0.4) in the canonical JOB workflow instead of concrete HRX interface IDs.
- Add `ScenarioError` and `python -m histra_builder` entry point.

## 1.1.0 - 2026-07-31

- Add secure HRX inventory and preview extraction from stored `Node` and `Quad` elements.
- Add geometry validation, bounding boxes, material/group counts and warnings.
- Add explicit JSON Pointer based scenario variants.
- Add `inspect`, `preview-job`, and `variants` CLI commands.
- Preserve the v1.0 canonical JOB contract and byte-for-byte no-patch HRX round trips.
- Improve immutable template registry listing and metadata support.
- Merge the v1.0 and v1.1 regression fixtures, keep immutable template IDs distinct, and reject non-finite JSON numbers used in provenance hashing.

## 1.0.0 - 2026-07-30

- Establish the canonical JOB compiler and lossless HRX importer.
