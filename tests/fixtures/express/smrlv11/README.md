# SMRL v11 EXPRESS corpus (provenance)

Source: **expresslang/smrlv11**
(https://github.com/expresslang/smrlv11) — the EXPRESS Language
Foundation's annotated import of the official
`standards.iso.org/iso/10303/smrl/v11/tech/smrlv11.zip`, with ELF
annotation comments (BSD-style license on the annotations, ISO
copyright on the schemas — ISO expressly permits use and
redistribution of the schemas per the repo README).

Mirrored 2026-10-06 (clone at `~/proj/third_party/smrlv11`, upstream
last pushed 2025-09-25). Vendored here with:

- per-module `arm.exp` / `mim.exp` for all 590 modules
- **longforms + concatenations retained only for**:
  `ap242_managed_model_based_3d_engineering` (-442 Ed.4),
  `ap239_product_life_cycle_support` (-439 Ed.4), and
  `reference_schema_for_sysml_mapping` (-400) — the SysML-bridge chain
- all 135 resource schemas
- 3 `unannotated/` originals

Trimmed vs upstream (1,433 → 1,326 files; 31 → 20 MB): other modules'
longforms/concatenations dropped — reconstructible from the shortforms
or re-clone the upstream repo.

## Phase C cornerstone

`modules/reference_schema_for_sysml_mapping/` IS ISO/TS 10303-400:2025
(WG12 N11378, supersedes N11008) — the module every earlier corpus
lacked. Its shortform carries the SELECT-based proxies binding the
-239/-442 OBP domain onto the SMV core model
(`assignment_object_proxy`, `relationship_object_proxy`,
`association_object_proxy` + the `part400_*_item` extension types);
its longform concatenates the full -239/-442 domain (2,431 entities)
— the concrete ARM to map AP242 data onto.

Note the SMV core model's abstract classes
(`AssignmentObject`, `RelationshipObject`, `AssociationObject`)
referenced in -400's comments are defined in the SMV TS series
(10303-4600…), which ISO has not folded into the SMRL — the
published OBP counterpart is ISO/TS 10303-3001
(`managed_model_based_3d_engineering_bom`, at
ap238.org/smrl/data/business_object_models/, 402 entities) —
vendor this separately when the mapper needs it.

## Verify

`poetry run pytest tests/smrlv11_corpus_test.py` — parse pins,
v11 corpus completeness, -400 presence, per-file parse.