# stepper

A pure-Python toolbox for STEP (ISO 10303) product-model data: read
Part 21 exchange files, load EXPRESS schemas, and check AP242 data
semantically — the same gate-style checks `sysmlpy` gives SysML
models, brought to STEP.

Status: **early development** (Phase A). Parse gate + schema inventory
work on real NIST AP242 files; semantic checks are next.

## What works today

- ISO 10303-21 (P21) exchange-structure parser: HEADER / ANCHOR / DATA
  sections, simple + complex multi-type entities, references, enums,
  binary/encoded strings, CRLF-tolerant. Tested against NIST PMI test
  case files (AP242 editions 1–4 and AP203).
- EXPRESS reader (subset): entity inventory with SUBTYPE OF edges,
  SELF-redeclarations, multi-supertypes on the real ISO/TS 10303-442
  (AP242 Ed.4) longform schema — 2,407 entities, supertype chains
  verified.
- `stepper check` — parse gate + advisory semantic findings (the
  `sysmlpy ci` pattern, applied to STEP).

## Roadmap

- **Phase B** — schema-validated P21: every instance checked against
  its schema (entity names, attribute counts, reference validity).
  WHERE rules advisory.
- **Phase C** — STEP ⇄ SysML bridge via ISO/TS 10303-400 (Reference
  schema for SysML mapping): map AP242 data to a SysML-shaped ARM and
  reuse sysmlpy's interchange/identity/diff machinery.

## Test corpus

The `tests/fixtures/nist/` directory vendors a small license-clean
subset of NIST's [CAD Models and STEP Files with
PMI](https://www.nist.gov/program-areas/mbe-pmi-validation-and-conformance-testing)
(public domain / NIST software license; see `tests/fixtures/nist/README.md`).

## Development

```bash
poetry install
poetry run pytest
```