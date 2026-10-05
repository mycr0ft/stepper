# Where next — the directions this infrastructure unlocks

Everything below builds on machinery that already works (P1–P4, all
probed on real data). Ordered by expected value against effort.

## Near term (high value, small work)

### 1. STEP gate in CI — `stepper check` as a merge blocker

The sysmlpy pattern (`sysml ci`) applied to STEP: a reusable GitHub
workflow + GitLab template that fails a merge whenever a `.stp`
file stops parsing or (once trusted) fails schema validation.

**What exists:** parse + check engine with CI exit codes; the
sysml-check workflow to copy.
**Work left:** `step-check.yml` reusable workflow (~30 lines DFA/
cache pattern from sysmlpy's), a pre-commit hook, docs.
**Why first:** zero new concepts — the discipline that caught 3
real parser bugs on its first run already.

### 2. Baseline-driven CI gate

A pipeline step that re-creates a baseline from the working tree
and **fails when the id differs from the pinned one** — the
"geometry must not drift during a release cycle" gate. Cheap:
baseline idempotency already gives exact content-equality semantics.

**What exists:** `create_baseline` + content-addressed ids.
**Work left:** a CLI (`stepper baseline create|verify --id bl:…`) so
pipelines don't need pyoslc running; a sidecar manifest format.

### 3. `stepper structure --output` and diff

Persist structure payloads to files, and diff two structures:
products added/removed, geometry counts changed, PMI counts changed.
The sysmlpy `diff_models` engine is the model to borrow.

**Why:** the "what changed in this CAD revision?" review question —
today answerable only by opening the files in a CAD system.

## Mid term

### 4. Full schema validation (WHERE rules)

The AP242 Ed.4 longform carries ~500 WHERE rules (subtype
constraints, uniqueness, domain checks). A scoped evaluator — start
with the declarative ones that pattern-match (UNIQUE, type-valued)
and leave procedural ones advisory — plus a strict mode promotion
path per project.

**What exists:** the schema reader (entities, supertypes,
where-rule names), the advisory label system.
**Work left:** an EXPRESS-expression evaluator (the big lift —
ISO 10303-11 expressions), rule-selection policy, corpus runs.

### 5. STEP⇄SysML semantic bridge (ISO/TS 10303-400)

The standards-track ARM-in-SysML modules (10303-400:2025,
modules 439/442) define SysML classes for the product backbone —
`PartDefinition`-shaped. Generating the ARM from the AP242 MIM (the
mapping is published) would let `stepper structure` emit resources
that are *literally SysML-v2-typed*, loadable as sysmlpy Models.

**What exists:** both parsers; the qn_registry identity join; the
Vee link table.
**Work left:** ARM .exp acquisition (10303-400's ARM is in SMRL),
mapping table implementation, round-trip tests against the NIST
corpus.

### 6. Geometry/PMI deep view

Today's structure payloads carry item COUNTS. A phase-B structure
mode could surface the real B-rep graph (solids → shells → faces →
loops → edges → vertices) and PMI semantics (which face carries
which tolerance), as OSLC resources or a JSON tree for web viewers.

**What exists:** the P21 reader resolves the whole instance graph
already.
**Work left:** traversal walkers per representation kind, an
output format, (optionally) an STL/glTF exporter for preview.

## Further out (research-scale)

### 7. Full AP242 model-loading (the sysmlpy-for-EXPRESS play)

The EXPRESS reader grows into a full ISO 10303-11 parser, AP242
Ed.4 loads as a typed model (the 2,407-entity graph), and instance
files validate completely — the analogue of what sysmlpy does for
SysML, for the CAD-interop world. Ambitious; the NIST corpus is the
gate.

### 8. Lyo/other-consumer interop round-robin

Test pyoslc's STEP provider against Eclipse Lyo clients, OSLC
Reference UI, and real PLM OSLC endpoints (Teamcenter/Windchill
adapters) — the interop matrix every serious OSLC project eventually
fills. Also unblocks the pyoslc fork's CI runner issue (currently
workflows sit queued).

### 9. Baseline-driven configuration picker (full OSLC Config UI)

The component/config selection dialogs (`pyoslc` has skeletons)
wired to the Vee baselines: pick a baseline in a PLM-agnostic UI,
get the pinned SysML + STEP snapshot URLs in return — the OSLC
Config-Management service proper.

### 10. STEP-XML (P28) implementation method

Part 28 (STEP-XML) is the XML form of the same data — a second
reader/writer would let stepper consume systems that emit P28 (and
it composes with 10303-15's published SysML XMI ⇔ XSD transform —
the other standards-track SysML hook).

## The meta-pattern

Every item above exists because the P1–P4 foundation made its
*question* answerable cheaply:

| question | machinery that answers it |
|----------|--------------------------|
| is this file good? | parse + check gate |
| what does it contain? | structure extraction |
| is it connected to the model? | Vee registry |
| what did we review/release? | baselines |
| is the release still intact? | baseline verification |

Pick directions that deepen one of those five answers.