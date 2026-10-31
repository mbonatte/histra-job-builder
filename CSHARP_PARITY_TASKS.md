# C# Mesh Parity Task Queue

Goal: reproduce the native C# `BridgeMesher` mesh, then add features on top.

Golden reference for the first slice:

- Source: `histra-python/histra/model-chain/model.hrx` (native HiStrA model)
- Structural snapshot: `tests/fixtures/csharp/model_chain_2span.json`
- Shape: 2 spans (450 cm), 1 pier (50 x 200 cm), 2 abutments (40 cm, H=0), width 300 cm, 3 x 100 cm strips, Nl=100, one elevation at 126.5 cm.
- Expected: 222 structural nodes, 156 quads, 12 GLRs, 12 restraints, 21 NodeCs.

## Provided native models (`histral_models/`)

The `histral_models/` folder is now the second golden source. It is ignored by git
because of its size; compact WizardData fixtures are stored under
`tests/fixtures/csharp/`.

Useful models:

- `Bridge_3/Bridge_3_abutment.hrx`
  - 3 spans, 2 piers, 3 unequal strips (`33/288/33`).
  - Exterior strips have `Height=17` -> `Nstrati=4`.
  - Abutments have `Hf=92` footings.
  - Native: 1088 quads, 18 GLRs, 48 restraints.
  - Our current exterior strips match exactly: `141:320, 18:56, 22:4`.
  - Known deltas: interior foundation quads (`60` native vs `48` generated),
    and restraint expansion (`48` native vs `18` direct-GLR restraints).
  - Fixture: `tests/fixtures/csharp/bridge3_abutment_wizard.hrx`.
  - Test: `tests/test_csharp_bridge3_golden.py`.

- `Bridge_1/*`, `Bridge_2/*`, `Bridge_3.1/*`, `Bridge_3.2/*`, `Bridge_3.3/*`,
  `Bridge_3.4/*`, `Bridge_5.1/*`, `Bridge_5.2/*`
  - Further 1–3 span variants, mesh densities, material/load calibrations, and
    solved result CSVs.
  - Most have `H2=H3=0`; several use exterior `Corsia.Height` to exercise the
    fourth layer, but they do not provide true multi-stratigraphy elevations.

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

## Completed (continued)

12. **Native `WizardData` parity**
    - Commit: `3f6f22e`, `7fc4e47`
    - Full `BridgeDefinition` children (`Corsie`, `Trunks`, `Zlevels`, `Binaries`, `MasonryBridgeWalls`).
    - Full native `Abutment`/`Span`/`Pier` attribute sets.
    - `<Elevations>` sections and `Layer1/2/3`.
    - Tests: `tests/test_csharp_writer.py`.

13. **Native material templates**
    - Commit: `8d6c30b`
    - `materials.py` now matches native templates 18/19/22/141/146/147 exactly.
    - Legacy `BridgeSpec` keeps a compatibility material set; C#-parity path uses native values.
    - Test: `tests/test_csharp_materials.py`.

14. **Native default model point**
    - Commit: `1383414`, `32f1a6d`
    - Ported `ModelPointOperations.TryAddDefaultModelPoints`: highest-Z node nearest the plan centre.
    - Emits native `ModelPoint` attributes and links analyses through `MasterPoint`.
    - Test: `tests/test_csharp_mesher.py` and `tests/test_csharp_writer.py`.

15. **Native attribute completeness**
    - Commit: `28b5a77`, `8484e11`
    - `NodeC` afference matrices + reference system.
    - Full `Quad` native attributes (`U1..U7`, load templates, modified flag).
    - Native `ModelPoint`, `NodeC`, `Node` names/flags; load-condition gamma fields.

16. **Default generator integration**
    - Commit: `12b3feb`
    - `generate_bridge_hrx(CSharpBridgeSpec)` dispatches to the C#-parity writer.

17. **Native portfolio / scour integration**
    - Commit: `aaafd2c`
    - `native_portfolio.py` samples real `CSharpBridgeSpec` values, regenerates the mesh, resolves pier foundation interface keys through `histra-python`, and emits `workflow.interface_mutations` with material 147.
    - CLI: `histra-builder generate-native`.
    - Test: `tests/test_native_portfolio.py`.

## Completed (multi-layer)

18. **Multi-layer elevation fill**
    - Commit: `63b2ea9`, `428b5c0`
    - Layers 2..N are stacked as structured quad bands over the extrados columns.
    - Added native layer materials `20` (Fill) and `21` (Concrete).
    - Test: `tests/test_csharp_multilayer.py`.
    - Remaining limitation: the C# `AddMesh2` curved-transition/`Vertex` branch
      is not yet emitted; it needs a native multi-layer golden to validate the
      triangle topology.

19. **Asymmetric arch + 4-span chain coverage**
    - Commit: `6ca2295`
    - Test: `tests/test_csharp_asymmetric.py` (`S1/S2`, `Asx/Adx`, unequal spans, 3 piers, 32 GLRs/restraints).

## Remaining golden-dependent branches

These are implemented only at the formula/structural level, or not at all,
because no native golden model exists in the repository:

1. Multi-layer curved transition / `AddMesh2` triangle topology.
2. Footing edge cases beyond `Bridge_3_abutment`: foundation wings
   (`B1f/B3f/W1f/W3f`), reinforcement extensions, and footing restraint
   expansion/segmentation.
3. Passive earth-pressure `SurfaceRestraint` path.
4. Inclined/slope/curved bridge transforms.
5. RailBridge2 / masonry walls / `BackFill` path.
6. Full-section alignment/reinforcement/cutwater paths.
7. Custom user-authored model points.
8. Asymmetric arch `Tb1/Tb2`-specific behavior (basic S1/S2/Asx/Adx is covered).
9. DB-derived template export with serialized enum names.

## Needed C# golden models

Please provide the following native `.hrx` files (or the C# WizardData plus a saved model) when available. They are needed to verify slices that currently have formula-level/structural tests but no native golden.

1. **Multi-layer elevation model**
   - `Elevations` with `H1/H2/H3 > 0` and preferably `IsStratigraphyVariable=true`.
   - Needed for `Nstrati=4`, layer material transitions, and `AddSemiArco` multi-layer branches.

2. **Footing model**
   - Abutment and/or pier with `Hf > 0`.
   - Prefer non-zero `B1f`, `B3f`, `W1f`, `W3f` and `b1/b3/w1/w3`.
   - Needed to verify foundation quads, foundation GLRs, and footing GLR segmentation.

3. **Passive earth-pressure model**
   - `SpintaPassivaSX` and/or `SpintaPassivaDX = true`.
   - Needed to verify `SurfaceRestraint` geometry and material/load assignment.

4. **Inclined / curved model**
   - `InclinationAngle != 0`, `Slope != 0`, and/or a curved `BridgeTrunk`.
   - Needed to verify normal rotation, node projection, and quad thickness interpolation.

5. **RailBridge2 / masonry-wall model**
   - `WizardType=RailBridge2`, `MasonryBridgeWalls`, `BackFill`.
   - Needed to verify `AddBridge2` and the wall/backfill path.

6. **Full-section model**
   - Non-zero `b1/b3`, `w1/w3`, `VerticalAllignment != Center`, reinforcement plates, or cutwater geometry.
   - Needed to verify `generatePilaSpalla` taper, reinforcement, and alignment branches.

7. **Custom model-point model**
   - Multiple `ModelPoint` elements, including non-default Node/Quad/Vertex selections.
   - Needed to verify user-authored model-point parity beyond the default highest-node rule.

8. **Asymmetric arch model**
   - Non-zero `S1/S2`, different `Asx/Adx`, and/or `Tb1/Tb2` differences.
   - Needed to verify the full retained-arch parameter path.

9. **Four-plus span / unequal-span model**
   - At least 4 spans and unequal span lengths.
   - Needed to verify `DiscrLeft/DiscrRight` across multiple piers and long chains.

10. **Database/template reference export**
    - The native `Template` elements generated from `DBRoadBridge/dbo.MaterialsMasonry.csv` with serialized enum names, or a saved model using those DB defaults.
    - Needed to distinguish the native model reference set from database-seed defaults.

## Known deltas exposed by `histral_models`

1. **Restraint expansion**: native `Bridge_3_abutment` has 48 restraints from
   18 GLRs, because `RestraintMesher` emits one restraint per foundation
   quad/column. The current builder emits one restraint per GLR.
2. **Abutment foundation discretization**: native interior-strip foundation
   produces 60 quads vs 48 in the current builder (`DiscrLeft/DiscrRight` and
   `WidthBottom`/GLR `B` handling for abutment footings need refinement).
3. **Project-specific material keys**: native uses custom templates `141`
   (Spandrel), `152` (Backfill_Arch), and `147` (Backfill_Load). The structural
   exterior strips match, but the interior fill material keys differ from the
   default template set.

## Verification

```bash
PYTHONPATH=/tmp/opencode/pydeps:histra-job-builder/src:histra-python \
  python3 -m pytest -q histra-job-builder/tests
```

Current status: `139 passed, 1 skipped` (optional real-HRX gate).
