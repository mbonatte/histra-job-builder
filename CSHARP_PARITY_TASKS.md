# C# Mesh Parity Task Queue

Goal: reproduce the native C# `BridgeMesher` mesh, then add features on top.

Golden reference for the first slice:

- Source: `histra-python/histra/model-chain/model.hrx` (native HiStrA model)
- Structural snapshot: `tests/fixtures/csharp/model_chain_2span.json`
- Shape: 2 spans (450 cm), 1 pier (50 x 200 cm), 2 abutments (40 cm, H=0), width 300 cm, 3 x 100 cm strips, Nl=100, one elevation at 126.5 cm.
- Expected: 222 structural nodes, 156 quads, 12 GLRs, 12 restraints, 21 NodeCs.

## Completed

1. **Golden fixture + provenance test**
   - Commit: `e2bf4c7`
   - `tests/fixtures/csharp/model_chain_2span.json`, `tests/test_csharp_parity_fixture.py`

2. **Port C# elliptical arch math**
   - Commit: `fad8900`
   - `generator/csharp_arch.py`: `GetParamsArchEllipse`, `GetIntradossoArchEllipse`, `GetThickness`, `LArcoEllisse`, `GetPointsInEllipseEquiSpaced`.
   - Test: `tests/test_csharp_arch.py` against native extrados/intrados points.

3. **Reproduce native two-span structural mesh**
   - Commit: `d227237`
   - `generator/csharp_model.py`, `generator/csharp_mesher.py`
   - `AddBridgeRow1`, `AddSemiArcoSx1/Dx1`, `AddMesh4`, `AddMesh3`, `AddMeshArco1`, `AddSpallePile` (Hf=0 path).
   - Test: `tests/test_csharp_mesher.py` -> 222 nodes / 156 quads, exact geometry multiset.

4. **Preserve C# quad winding and insertion order**
   - Commit: `1569e27`
   - Exact ordered 156/156 quad match; 144 negative/12 positive normal winding as in C#.
   - `geometry.compute_quad_kinematics` accepts negative winding without flipping.

5. **Reproduce native GLR / Restraint / NodeC hierarchy**
   - Commit: `171d989`
   - 12 `GeometryLineRestraint`, 12 `Restraint`, 21 `NodeC`, exact key order and parent relationships.

6. **Native HRX writer integration**
   - Commit: `aca9fb2`
   - `generator/csharp_writer.py`: `<Bridge>`, GLRs, restraint parents.
   - Test: output loads and prepares through `histra-python` (222 nodes, 156 quads, 12 restraint interfaces).

7. **Correct multi-stage scour load semantics**
   - Commit: `053958c`
   - `Vert Mult=1`; `Scour_1/Scour_2 Mult=0`; scour load function 23 is flat zero.

8. **Public C# parity API**
   - Commit: `aa03253`
   - `histra_builder.CSharpBridgeSpec`, `CSharpMesher`, `build_csharp_bridge_mesh`, `generate_csharp_bridge_hrx`.

9. **Exact C# top/bottom/foundation discretization**
   - Commit: `d94ba67`
   - `generator/csharp_discretize.py`: `DiscretizeTopPileb2`, `DiscretizeBottomPileb2`, `DiscretizeBottomFondazionePileb2`.
   - Ported abutment/pier shafts for `H > 0`, foundation quads/GLRs for `Hf > 0`, and exact pier column generation.
   - Tests: `tests/test_csharp_discretize.py`, `tests/test_csharp_foundations.py`.

10. **Public HRX API dispatch**
    - Commit: `12b3feb`
    - `generate_bridge_hrx(CSharpBridgeSpec)` now uses the C#-parity writer.

11. **Native preparation defaults**
    - Commit: `9d51501`
    - Aligned `ToleranceNode`, `TolerancePlane`, `InterfaceImax`, `SolverParallel`, `VaultMesherQuadNumMin2` with `DefaultValues.cs`.

## Deferred

1. **Multi-layer elevations / BackFill**
   - Deferred by request. Keep as a future step.
   - Port the `Nstrati=4` and `Elevations.GetMaterialKey` branches.
   - Add a native golden model with `H2/H3 > 0`.

## Next tasks

2. **Native `WizardData` parity**
   - Emit full `BridgeDefinition` children (`Corsie`, `Trunks`, `Zlevels`, `Binaries`, `MasonryBridgeWalls`).
   - Emit full `Abutment`/`Span`/`Pier` attributes.
   - Emit `<Elevations>` children + `Layer1/2/3`.
   - Add `AfferenceMatrices`/`ReferenceSystem` on `NodeC`; full `Quad`/`ModelPoint`/`Analysis` attributes.

5. **Material template source**
   - Stop hardcoding a single project's templates.
   - Load templates from the C# DB assets or a registry.
   - Add attribute-level template tests.

6. **Model point parity**
   - Generate the same per-span/per-pier model points as C#.

7. **Default generator integration**
   - Make `generate_bridge_hrx` use the C#-parity path for all new portfolio generation.
   - Keep the old simplified `BridgeSpec` path as an explicit compatibility API if needed.

8. **Portfolio / scour integration**
   - Regenerate geometry for sampled parameters (not only WizardData patches).
   - Resolve `pier_1`/fraction to concrete interface keys and emit `workflow.interface_mutations`.

## Verification

```bash
PYTHONPATH=/tmp/opencode/pydeps:histra-job-builder/src:histra-python \
  python3 -m pytest -q histra-job-builder/tests
```

Current status: `122 passed, 1 skipped` (optional real-HRX gate).
