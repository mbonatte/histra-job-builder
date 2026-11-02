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
  - The wizard-generated exterior strips have `141:308, 18:56, 22:6`;
    the saved, edited reference has 12 additional material-141 quads and
    two fewer material-22 pulvinos per strip.
  - Foundation restraints now match the native count (48 from 18 GLRs).
  - The saved model has remeshed abutment regions: 48 footing quads use
    different column boundaries, and 12 additional quads lie above the
    footing. Its abutment GLRs have keys 16–21 and width 50 rather than the
    wizard lane widths. These saved edits do not establish the wizard's
    original generated topology; treat them as a separate comparison.
  - Fixture: `tests/fixtures/csharp/bridge3_abutment_wizard.hrx`.
  - Test: `tests/test_csharp_bridge3_golden.py`.

- `Bridge_scour_3d.hrx` (root of `histra-job-builder/`)
  - 3 spans, 2 piers, 8 x 36 cm strips.
  - Pier footings: `Hf=70`, `B1f=B3f=50`, `W1f=W3f=25`.
  - 2520 quads, 96 GLRs, 136 restraints, 7 model points.
  - Our generated mesh now matches exactly at the quad/material/GLR level:
    `2520` quads, `96` GLRs, material counts
    `19:1664, 18:448, 141:360, 22:48`, and the two ±156.5 wing strips.
  - The builder now also emits 136 restraints across the 96 GLRs. All saved
    restraint footprints and all 2520 quad geometries and thicknesses match
    at 0.1 cm precision, with matching material keys. General
    intersection and exact serialized restraint parity remain unverified.
  - Fixture: `tests/fixtures/csharp/bridge_scour_3d_wizard.hrx`.
  - Test: `tests/test_csharp_scour3d_golden.py`.

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
    - Test: `tests/test_csharp_asymmetric.py` (`S1/S2`, unequal spans,
      3 piers). The straight C# `AddBridgeRow1` uses `Adx` for both halves;
      independent `Asx` behavior is not implied by this test.

20. **Straight support and reinforcement fixes**
    - Subdivide `AddMesh3` rows across their width and segment aligned support
      lines across the resulting bottom quad edges.
    - Preserve each lane's width in arch, fill and pulvino quads; use the
      native `Adx` check for both adjacent-span discretizers.
    - Map foundation fixity flags and `Kz` to native restraint attributes.
      The current `histra-python` solver rejects free or elastic restraint
      DOFs during preparation, even though the builder now preserves them.
    - Generate rectangular shaft reinforcement and arch reinforcement;
      preserve their material keys on import. Export requires templates for
      all generated quad materials, including reinforcement materials.
    - These paths are based on the C# source; native golden geometry and
      solver validation of the reinforcement cases are still needed.
    - Ported longitudinal slope as `z += x * slope` and preserved the
      layer generation and uniform/nonuniform material settings. The flat
      layer paths have tests; curved transitions still need native goldens.
    - Ported the straight, untapered strip inclination transform, extrusion
      normals, widths, and support footprints. The generated example loads
      and prepares in the solver; native geometry and tapered-edge behavior
      still need verification.
    - Restored native material-template attributes on HRX import and export.
      Fixed extra subdivisions in elevated exterior bands: all 914 saved
      `Bridge_1` quad geometries and thicknesses now match at 0.1 cm precision.
      Four saved quads have material changes not present in their WizardData.
    - Added native GLR restraint-key lists and reference systems to export.
      The regenerated scour model loads and prepares with 136 restraint
      interfaces in `histra-python`.
    - `Bridge.H` now uses the highest Z3 elevation, as in `Bridge.Init`.
    - Preserve imported bridge-definition and lane attributes, variable
      stratigraphy, and trunk data. Curved trunks, passive pressure,
      RailBridge2, enabled wizard vehicle loads, and inclined tapered
      supports now fail explicitly rather than silently generating a
      different bridge.

21. **Native load and analysis schema**
    - Emits the complete native startup schema: 11 `LoadCondition`, 12 `LoadCombination`, 32 `LoadFunction` and 64 `LoadFunctionItem` elements.
    - Emits the 13-analysis native tree (`Vert`, `Modal_0`, `LiveLoad_1`, `scour_1`...`LiveLoad_4`) with native attributes, not-executed states and model-point links.
    - Keeps `ForceMoment` on the three pipeline stages; the other analyses retain the native `Work` criterion.
    - Restores native 0 -> 1 scour load functions (the zero `Mult` prevents gravity reapplication).
    - Test: `tests/test_csharp_analyses.py` against `tests/fixtures/csharp/analyses.json`.

## Remaining golden-dependent branches

These are implemented only at the formula/structural level, or not at all,
because no native golden model exists in the repository:

1. Multi-layer curved transition / `AddMesh2` triangle topology.
2. Footing edge cases beyond the supplied models: triangular reinforcement
   (`Vertex` elements), and general restraint intersections outside aligned
   foundation edges.
3. Passive earth-pressure `SurfaceRestraint` path.
4. Inclined tapered-edge and curved bridge transforms; native validation of
   the straight inclination and slope paths.
5. RailBridge2 / masonry walls / `BackFill` path.
6. Full-section alignment/reinforcement/cutwater paths.
7. Custom user-authored model points.
8. Asymmetric arch `Tb1/Tb2`-specific behavior and native coverage of the
   C# path's `Adx` treatment.
9. DB-derived template export with serialized enum names.
10. Native vehicle and lane-load generation. Wizard attributes are preserved,
    but the builder does not yet recreate all C# traffic-load behavior.

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

1. **Restraint expansion**: aligned, subdivided foundation edges now emit one
   restraint per quad. Counts match both supplied models (`Bridge_3_abutment`:
   48 from 18 GLRs; `Bridge_scour_3d`: 136 from 96 GLRs). General geometric
   intersections and exact native restraint fields still need verification.
2. **Saved abutment modifications**: the saved `Bridge_3_abutment` has 48
   footing quads with different column boundaries plus 12 quads above them,
   and edited abutment support widths. Establish which edits must be
   preserved when importing an existing model versus regenerating a wizard.
3. **Project-specific material keys**: native uses custom templates `141`
   (Spandrel), `152` (Backfill_Arch), and `147` (Backfill_Load). The structural
   exterior strips match, but the interior fill material keys differ from the
   default template set.

## Verification

```bash
python -m pip install -e ".[test]"
python -m pip install "histra-python @ git+https://github.com/mbonatte/histra-python.git@v1.2.2"
python -m pytest -q
```

Current status: `153 passed, 1 skipped` (optional real-HRX gate).
