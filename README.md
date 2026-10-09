# stepper

[![stepper checks](https://github.com/mycr0ft/stepper/actions/workflows/check.yml/badge.svg)](https://github.com/mycr0ft/stepper/actions/workflows/check.yml)
[![docs](https://github.com/mycr0ft/stepper/actions/workflows/docs.yml/badge.svg)](https://github.com/mycr0ft/stepper/actions/workflows/docs.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://mycr0ft.github.io/stepper/)

**Pure-Python toolbox for STEP (ISO 10303) product data** — read
Part 21 exchange files, load EXPRESS schemas, check AP242 data,
serve it as OSLC, link it to SysML models, and pin releases as
verifiable baselines.

stepper is the **right side of the Systems-Engineering Vee**
(geometry, product structure, PMI) of a fully open-source toolchain:

```
     requirements & design              geometry & PMI
     .sysml — sysmlpy — OSLC — stepper — .stp
                    pyoslc serves both sides
                 as one catalog; baselines pin
                  released configurations
```

| sibling | role |
|---------|------|
| [sysmlpy](https://github.com/mycr0ft/sysmlpy) | SysML v2 parser/semantic analyzer (left Vee) |
| [pyoslc](https://github.com/mycr0ft/pyoslc) | OSLC server SDK — hosts both domains + the Vee link |

## Status: P1–P4 complete, in daily use

The OSLC/Config-Management integration (phases P1–P4) is **done and
verified end-to-end on real data** — NIST's [CAD Models and STEP
Files with PMI](https://www.nist.gov/el/systems-integration-division-73400/mbe-pmi-validation-and-conformance-testing)
corpus (28 files, ~300k instances) plus the Airbus Saturn V SysML
model.

## What works

| capability | command / API | verified by |
|------------|--------------|-------------|
| Read any Part 21 file (geometry, PMI, assemblies) | `stepper inspect` | 35-test suite incl. AP242 ed. 1–4 + AP203 |
| Parse + schema gate with CI exit codes | `stepper check -s ap242.exp` | NIST corpus: 0 failures @ ~1,800 inst/s |
| Extract product structure as OSLC JSON-LD/Turtle | `stepper structure` | rdflib-verified on 6 fixtures |
| Serve STEP as OSLC resources (+ shapes, provider in catalog) | pyoslc `/oslc/step/*` | 72-test pyoslc suite |
| Link SysML elements ↔ STEP instances (the Vee join) | pyoslc `/oslc/step/vee` | sysmlpy `qn_registry()` + auto/manual links |
| Pin + verify released configurations | pyoslc `/oslc/step/baselines` | content-addressed, immutable, tamper-detecting |

## Install

```bash
pip install stepper                     # the STEP reader
git clone https://github.com/mycr0ft/pyoslc.git   # the OSLC server side
```

From source (this repo):

```bash
git clone https://github.com/mycr0ft/stepper.git
cd stepper && poetry install
poetry run pytest                     # 35+ tests should pass
```

## 30-second tour

```bash
# What's in a STEP file?
$ stepper inspect tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp
  instances: 4350
  schema: AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF {1 0 10303 442 1 1 4}
    ORIENTED_EDGE    636
    CARTESIAN_POINT  395
    ...

# Check it against the AP242 Ed.4 schema
$ curl -O https://standards.iso.org/iso/ts/10303/-442/ed-7/tech/express/mim_lf.exp
$ stepper check tests/fixtures/nist/ -s mim_lf.exp

# Product structure as OSLC (Turtle or JSON-LD)
$ stepper structure nist_ctc_01_asme1_ap242-e1.stp --format turtle
```

## The OSLC side in one minute

With [pyoslc](https://github.com/mycr0ft/pyoslc) (P2+ integration),
STEP data becomes a first-class OSLC domain:

- `/oslc/step/product` — every PRODUCT record as an OSLC resource,
  with ResourceShapes and a `Step-1` service provider in the shared
  OSLC catalog,
- `/oslc/step/vee` — the **Vee link**: identity edges between SysML
  elements (qualified name + stable `@id` from sysmlpy's
  `qn_registry()`) and STEP resources, queryable in both directions;
- `/oslc/step/baselines` — **released configurations**: a baseline
  pins the `.sysml` + `.stp` bytes AND their derived payloads
  (interchange JSON with the QN registry; structure JSON-LD) plus the
  Vee link snapshot. Baseline id = manifest digest — identical
  content is idempotent, any change is a new release, and
  `?verify=1` re-hashes every artifact (tamper detection).

Full walkthrough for beginners: **[the mkdocs
site](https://mycr0ft.github.io/stepper/)** — six lessons assuming no
prior STEP knowledge, every command verified on the vendored files.

## CI/CD gates

```yaml
jobs:
  step-check:
    uses: mycr0ft/stepper/.github/workflows/step-check.yml@main
    with:
      paths: "step/"
      semantic: "advisory"     # off | advisory | strict
      baseline-manifest: "config-mgmt/baseline.json"   # optional
```

Parse is **always blocking**; schema semantics are advisory by
default. Adding `baseline-manifest` gates merges against a pinned,
content-addressed released configuration (`stepper baseline
create/gate` — any drift exits 1 and prints the first differing
artifact). GitLab template + pre-commit hook in the repo; details in
[`docs/ci-integration.md`](docs/ci-integration.md). (PyPI's `stepper`
name is an unrelated project — pins resolve from GitHub.)

## Roadmap

See [`docs/directions.md`](docs/directions.md) for the ten ranked
directions this foundation unlocks, each with what-exists / work-left:
STEP CI gates, baseline-driven release gates, structure diffing,
WHERE-rule validation, the ISO/TS 10303-400 ARM⇄SysML bridge,
B-rep/PMI deep views, full EXPRESS loading, Lyo interop, and more.

Design record (probes, decisions, per-phase commit refs):
[`docs/oslc-integration.md`](docs/oslc-integration.md).

## Test corpus

`tests/fixtures/nist/` vendors a license-clean subset of NIST's
[MBE PMI Validation and Conformance Testing](https://data.nist.gov/od/id/ark:/88434/mds00jwkr0)
files (public domain; see `tests/fixtures/nist/README.md`): CTC/FTC/STC
cases across AP242 editions 1–4 plus an AP203 control. The full 28-file
corpus (available from NIST) runs the gate in ~170 s locally.

## Development

```bash
poetry install                 # venv: stepper-*
uv pip install --python $(poetry env info --path)/bin/python pytest rdflib
poetry run pytest
mkdocs serve                   # local docs site
```

MIT license. The NIST fixtures are US-government public domain.