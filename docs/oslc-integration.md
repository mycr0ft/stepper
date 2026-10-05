# stepper × pyoslc — Systems-Engineering Vee ↔ PLM/OSLC integration

Architecture note. Written after the probes on 2026-10-05; all
claims below are backed by running code or fetched standards, not
projections.

## The vision

The Systems Engineering Vee — requirements on the left, assembly and
verification on the right, design in the middle — spans two data
worlds this repo pair already handles:

- **Left/Middle (requirements, function, behavior):** SysML v2
  models — `sysmlpy` parses and analyzes them; `pyoslc` already
  serves them as OSLC resources (Saturn V example, v0.4.0).
- **Right (geometry, product structure, PMI, manufacturing):**
  STEP AP242 data — `stepper` now reads it (P21 + AP242 Ed.4
  schema + check gate; 300,851-instance NIST corpus validated).

The Vee link is the integration glue: the same *element identity*
flows through both worlds, and PLM lifecycle state (approved /
released / obsoleted) becomes OSLC Config Management resources
instead of files.

## Proven building blocks (this session)

| block | status | evidence |
|-------|--------|----------|
| AP242 P21 parse | works | 28 NIST files, 0 failures |
| AP242 schema validation (advisory) | works | 300,851 inst, 0 err @ 1,800/s |
| product structure extraction | works | PRODUCT / PRODUCT_DEFINITION / NAUO (assembly) identified in NIST files; assemblies present in FTC-09 (4 products) |
| OSLC-shaped emission (Turtle/JSON-LD) | works | rdflib round-trip against pyoslc's actual `OSLC_SYSML` namespace — namespace match: True |
| pyoslc SysML server | exists | v0.4.0, Saturn V 142-element model, InMemorySysMLRepository, ResourceShapes |
| pyoslc-client CLI | exists | discovery/query/CRUD/compact, OAuth1/Basic |
| OSLC Config Mgmt vocabulary | exists | `pyoslc/vocabularies/config.py` |

## The standards story (why this is not just glue)

- **ISO/TS 10303-400 (2025)** — the STEP ARM is *built in SysML*
  (modules 439=AP239 PLCS + 442=AP242). Part 4000 is the Core model
  with Domain Model → ARM mappings.
- **ISO/TS 10303-15 (2021)** — the SysML XMI ⇔ XSD transform.
- **OSLC PLCS spec** (OASIS PLCS TC, retired but published) defines
  the binding of AP239/PLCS data to OSLC; AP242-to-OSLC follows the
  same pattern (same product-structure backbone).
- **OSLC Config Management** — baseline/configuration/versioning of
  the PLM side; `pyoslc` already carries the vocabulary.

So the Vee link is standards-track: STEP's arm-in-SysML structure
becomes sysmlpy models; sysmlpy models become OSLC resources via
pyoslc; AP242 geometry/PMI instances hang off the same element ids
via stepper. One tool serves the full Vee.

## Proposed architecture

    .sysml (Vee left/middle)          .stp AP242 (Vee right)
         │                                      │
         │ sysmlpy.loads()/analyze()            │ stepper.load_p21()
         ▼                                      ▼
    sysmlpy Model                        step model (products,
         │                               assemblies, PMI, geometry)
         │  ◄──── shared element identity (sysmlpy stable_ids /
         ▼        interchange @id ↔ STEP ANCHOR section UUIDs) ────────►
    pyoslc server (OSLC SysML domain)          stepper→OSLC adapter
         │                                          │
         └────────────── OSLC ◄─────────────────────┘
                 ServiceProviderCatalog
                 (RM/QM/AM + PLM domain of this project)

    Consumer: pyoslc-client CLI / Eclipse Lyo / any OSLC tool
    Lifecycle: OSLC Config Mgmt baselines version BOTH sides.

## Phases

- **P1 — stepper: structure extraction ✅ (7bee9dc).**
  `stepper structure file.stp` emits OSLC-shaped JSON-LD/Turtle:
  PRODUCT → `Product` resources,
  NEXT_ASSEMBLY_USAGE_OCCURRENCE → containment links,
  geometry summary (shape representations per product). P21 ANCHOR
  UUIDs (AP242 files carry them; NIST files have them when saved
  with P21 e3) become the `@id`s — same discipline as sysmlpy's
  stable-ids registry.
- **P2 — pyoslc: STEP domain adapter ✅ (pyoslc ef1aa2a).**
  `StepProduct` / `StepProductDefinition` / `StepShapeRepresentation`
  / `StepFile` resource classes at the `oslc:Resource` level, typed
  by the stepper vocabulary; `/oslc/step/*` REST endpoints;
  `Step-1` service provider in the catalog; resource shapes; seeder
  from stepper's P1 output (`seed_from_step_file(.stp)` full pipe).
  **Root-cause fix carried:** core.py's class-decorated
  `@api.representation` broke every flask-restx error path — real
  serializers now registered last.
- **P3 — the Vee link ✅ (this repo P3 tests; sysmlpy qn_registry).**
  The join table is built on sysmlpy's new **`qn_registry()`** export
  side table (deduped declared-QN path → stable `@id`), which rides
  every `to_interchange(stable_ids=True)` document under
  `"#qn_registry"`. pyoslc's `VeeRegistry`
  (`namespaces/step/vee.py`) stores the edges and exposes them at
  `/oslc/step/vee`:
  - `POST /oslc/step/vee {"registry": {...qn_registry output...}}` —
    auto-links by leaf name (quoted SysML short names stripped);
  - `POST {"sysml_qn":..., "sysml_id":..., "step_ref":...,
    "kind": "realizes|specifies|traces"}` — manual edges;
  - `GET ?sysml_qn=…` / `?step_ref=%23…` — both directions;
  - optional JSON sidecar (`VeeRegistry(sidecar=…)`) — persists the
    links across restarts, the sysmlpy-reconcile-registry pattern.
  Demonstrated end-to-end: NIST CTC-01 product ↔ a SysML part with
  the matching short name links automatically; the honest no-match
  case reports zero new links.
- **P4 — Config Management baselines ✅ (pyoslc 964bab5).**
  `create_baseline()` pins the Vee configuration by content hash:
  `.sysml` + `.stp` source bytes land in a sha256
  content-addressed artifact store; the DERIVED payloads ride the
  manifest — the sysml interchange stable-ids JSON (with its
  `qn_registry`) and stepper's structure JSON-LD per .stp — plus a
  snapshot of the Vee link table. Baseline id = manifest digest:
  identical content is idempotent (re-creation raises), any content
  change mints a new id, `derived_from` chains baselines into a
  release history, and `verify_baseline(id)` re-hashes every stored
  artifact (tamper detection pinned by test). Immutable — the REST
  surface (`/oslc/step/baselines`) is read/create/verify only.

## Immediate next step (when picked up)

1. `stepper structure` (P1): emit OSLC JSON-LD for a NIST AP242
   file — small, useful, testable against rdflib + pyoslc's own
   vocabulary (the namespace-match probe above is the pattern).
2. Add the STEP domain adapter to pyoslc's example app (P2),
   following `examples/saturn_v/` conventions.
3. Prove the Vee link on ONE element: Saturn V F-1 engine (SysML
   side) ↔ a NIST CTC/FTC file with an annotated hole or boss
   (AP242 side), linked by a shared element id — the demo that
   makes the architecture tangible.

## Risks / unknowns

- Where-rule evaluation on AP242 data is large (4,784 ARM entities
  in_ed7); advisory-mode until Phase B scope settles.
- STEP ANCHOR sections are optional — files without them need the
  position-id fallback (the sysmlpy stable_ids vs position lesson
  applies directly).
- pyoslc's InMemorySysMLRepository pattern is fine for demos; a
  persistent backend matters before P4. (`pyoxigraph` support is
  already scaffolded in pyoslc.)
- OSLC OAuth flows in pyoslc are Flask/OAuthlib — works; Lyo or
  other consumers interop tested only against pyoslc-client so far.