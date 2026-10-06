# STEPmod EXPRESS corpus (provenance)

317 EXPRESS schemas pulled from the **SourceForge `stepmod` project**
(https://sourceforge.net/projects/stepmod/ — the WG12 "STEP Module
Repository" download mirror), 2004–2006 era module snapshots. Public
ISO/STEP committee working-draft distribution; keep out of any product
that claims normative-current standards data — these editions are 20
years old and useful only as parser/reader regression input.

## Sources, as fetched 2026-10-06

| SF path | contents |
|---------|----------|
| `config_control_3d_design_ed2/20041124/9999-...zip` | the full CC3D ed.2 module tree: 56 modules (arm/mim + longforms) + 33 resource schemas + 116 TS-part files (`express/partNNNNts_*arm/mim`) |
| `OldFiles/WG12N2882_20041110.zip` | TS ballots 1050/1051/1052/1130/1131 (corrupt central dir — salvaged 235 files via streaming local headers) |
| `OldFiles/WG3N999_20041104.zip` | same 5 TS ballots, complete (779 files salvaged) |
| `OldFiles/wg12n1721-203e2_gdt-20040816.zip` | AP203 E2 GDT modules (elemental_geometric_shape etc.) |
| `pdm-publication/20041112/check_pdm_ballot_072002.zip` | PDM modules (arm/mim/longforms) |
| `ap203e2_apdoc/20041201/check_ap203e2_apdoc.zip` | AP203 ed.2 application-object documentation |

## Layout

- `modules/` (129) — module ARM + MIM shortforms and longforms
  (`arm.exp`, `mim.exp`, `*_arm_lf.exp`, `*_mim_lf.exp`) across the
  CC3D, PDM and GDT modules. Where the same basename came from
  different modules, the file carries a `__<module>` suffix.
- `resources/` (42) — the standalone integrated-resource schemas
  (geometry_schema 60 KB, topology_schema, measure_schema,
  representation_schema, …).
- `ts/` (142) — the technical-specification module files
  (`partNNNNts_…`), including -1050/-1051/-1052/-1130/-1131 ballots in
  both TS and CD-TS versions.

## Verify before trusting these counts

`poetry run pytest tests/express_corpus_test.py` pins the counts and
parses every file (schema readers: `stepper.express.load_express`).

## What this is NOT

- NOT the ISO/TS 10303-400:2025 SysML-mapping ARM — that is not
  published anywhere free (checked standards.iso.org and the stepmod
  mirrors; see the stepper-pyoslc-vee skill for the acquisition story).
- NOT a current-edition corpus — if a schema disagrees with AP242 Ed.4
  (`ap242ed4_mim_lf.exp` in the vendor tree), AP242 wins.