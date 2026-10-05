# 2. Checking models

Goal: run the parse + schema-validation gate, the same check a CI
pipeline runs on every commit.

## The command

```bash
cd ~/proj/stepper
poetry run stepper check tests/fixtures/nist/ \
    --schema ap242.ed4.exp --semantic advisory
```

If you have the AP242 schema downloaded (the tutorial uses the
real ISO/TS 10303-442 Ed.4 longform; download once and point
`--schema` at it):

```bash
curl -O https://standards.iso.org/iso/ts/10303/-442/ed-7/tech/express/mim_lf.exp
mv mim_lf.exp ap242.ed4.exp

poetry run stepper check tests/fixtures/nist/ -s ap242.ed4.exp
```

Output on the vendored NIST files (trimmed):

```
stepper check: 6 file(s), 82455 instance(s), semantics advisory
PASS ...
summary: 0 parse failure(s), 0 error(s), 0 warning(s)
result: PASS
```

The exit code is `0` — wire it into CI and the build fails whenever
a model stops parsing.

## What the check actually does

For every file:

1. **Parse** (blocking): the full Part-21 structure must parse —
   header, sections, every instance. A syntax error is a finding
   with line information.
2. **Schema** (advisory by default): with a schema loaded, every
   instance's declared type must exist in the schema, argument
   counts must agree, and every `#123` reference must resolve to a
   declared instance.

## The three semantic modes

| mode | findings reported | findings block? |
|------|------------------|-----------------|
| `--semantic off` | none | parse failures still do |
| `--semantic advisory` (default) | yes, labeled | parse failures only |
| `--semantic strict` | yes | errors DO block |

Why advisory default? The AP242 schema has WHERE rules (hard
constraints like "this subtype combination is disallowed") that the
checker does not fully evaluate yet — a strict default could reject
valid models. Advisory gives you the findings without the false
gate. Promote to `strict` per project once your corpus is clean.

## JSON output for tooling

```bash
poetry run stepper check tests/fixtures/nist/ -s ap242.ed4.exp --format json
```

```json
{
  "files_checked": 6,
  "instances_checked": 82455,
  "exit_code": 0,
  "summary": {"parse_failures": 0, "errors": 0, "warnings": 0},
  "findings": []
}
```

## Python API

```python
from stepper import check_file, load_express

schema = load_express("ap242.ed4.exp")
result = check_file("tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp",
                    schema=schema, semantic="advisory")
print(result.exit_code)                # 0
print(result.instances_checked)        # 4350
for f in result.findings:
    print(f.level, f.stage, f.code, f.message)
```

## What's next

[Product structure → OSLC](structure.md) — turn this raw instance
cloud into a linked product tree.