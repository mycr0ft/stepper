# Beginner's Guide

Welcome! This guide assumes **no prior STEP knowledge** — you need
only Python 3.9+ and this repository checked out. Every command in
this guide is verified against the NIST test files that ship in
`tests/fixtures/nist/`, so you can follow along line by line.

## What is STEP, in one minute

STEP (ISO 10303) is *the* neutral format CAD systems exchange product
data in. When Boeing sends Airbus a part model, they send a STEP file
(an "AP242" file, in the aerospace version of the format). Inside:

- a **Part 21 exchange structure** — the text format
  (`#123=CARTESIAN_POINT('',(1.0,2.0,3.0));` — one line per data
  "instance", everything referenced by `#number`),
- describing data in the shape of an **EXPRESS schema** — the data
  model the file conforms to. AP242 ("Managed model based 3D
  engineering") is the schema for aerospace-scale models: product
  structure, geometry, tolerances (PMI), materials.

A STEP file is *data*; the schema is *the vocabulary it uses*.
stepper reads both.

## What stepper does today

| capability | command | status |
|------------|---------|--------|
| read any Part 21 file | `stepper inspect` | ✅ |
| check instances against the AP242 schema | `stepper check` | ✅ |
| extract product structure as OSLC | `stepper structure` | ✅ |
| serve structure via pyoslc | (pyoslc side) | ✅ |
| link SysML ↔ STEP elements | (pyoslc Vee registry) | ✅ |
| pin releases as baselines | (pyoslc baselines) | ✅ |

## What you need

```bash
cd ~/proj/stepper
poetry install          # creates the venv, installs stepper + deps
poetry run pytest tests -q   # sanity: 35-40 tests should pass
```

The NIST fixtures (~4 MB total) ship in the repo — every example
below uses them, so nothing else to download.

## The tutorial

1. [Inspecting a STEP file](inspect.md) — open, read, understand
   what's inside.
2. [Checking models](check.md) — parse + schema validation with exit
   codes your CI can gate on.
3. [Product structure → OSLC](structure.md) — the bridge to linked
   data.
4. [Serving as OSLC](serve.md) — run the pyoslc server and query
   STEP data over HTTP.
5. [The Vee link](vee.md) — connect a SysML model to STEP data.
6. [Baselines](baselines.md) — pin and verify a released
   configuration.

Each page is short, ends with a working result, and explains the
*why* — not just the command.