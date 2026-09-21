# Changelog

## 1.2.0 - 2026-09-21

- Add parametric bridge generator ported from C# reference implementation (`BridgeSpec`, `SpanSpec`, `PierSpec`, `AbutmentSpec`, `generate_bridge_hrx`).
- Add procedural 2D quadrilateral finite-element mesher for masonry arches, spandrels, pier shafts, and foundation footings.
- Add HiStrA foundation boundary restraints and `NodeC` kinematics conforming to Quad solver invariants.
- Add displacement monitoring `<ModelPoint>` elements at key structural monitoring locations.
- Configure `AdapticConvergenceCriteria="ForceMoment"` for strict equilibrium audit compliance in `histra-python`.
- Add seeded random five-JOB scour workflow generation (`generate-random` CLI command and `histra_builder.scenarios`).
- Keep scour semantics (`pier_1`, absolute fractions 0.2/0.4) in canonical JOB workflows.
- Provide synthesized reference `model.hrx` fixture for regression suites.

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
