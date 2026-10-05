# 6. Baselines — pinning a released configuration

Goal: turn "the model as of our review" into a **verifiable,
immutable artifact** — the PLM released-configuration concept, built
on OSLC Config-Management ideas.

## What a baseline is

A baseline pins a Vee configuration by **content hash**:

| pinned artifact | kind | how |
|----------------|------|-----|
| the `.sysml` source files | source | raw bytes, sha256 |
| the `.stp` STEP files | source | raw bytes, sha256 |
| the SysML interchange payload (+ QN registry) | derived | computed at baseline time |
| the stepper structure payload per .stp | derived | computed at baseline time |
| the Vee link table | join | snapshot |

Everything hangs in a sha256 content-addressed store; the baseline's
**id is the digest of its manifest** — so:

- identical content → identical id (re-creating the same
  configuration is idempotent; the duplicate raises),
- any change → a new id (a history, not an edit),
- `derived_from` chains baselines into a release lineage,
- integrity is verifiable forever by re-hashing.

## Creating one

Via REST:

```bash
curl -X POST http://localhost:5000/oslc/step/baselines \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "SRR-1 review baseline",
    "description": "Saturn V packages + CTC-01 geometry",
    "sysml_files": ["/path/SystemPackage.sysml", "/path/TechnicalComponentsPackage.sysml"],
    "step_files":   ["/path/nist_ctc_01_asme1_ap242-e1.stp"],
    "author": "jf"
  }'
```

Response (trimmed):

```json
{
  "id": "bl:70b2bf15c276fbdc",
  "created": "2025-05-21T14:03:11",
  "artifacts": [
    {"kind": "sysml", "path": "SystemPackage.sysml",
     "sha256": "3629912cf0fdf409…", "size": 4096},
    {"kind": "sysml_interchange", "path": "-",
     "sha256": "03f8208f030705bb…", "qn_registry": {"SystemPackage": "sysml:…", …}},
    {"kind": "step_structure", "path": "nist_ctc_01_asme1_ap242-e1.stp",
     "sha256": "fbaa404a0d132a9b…"}
  ],
  "vee_links": []
}
```

## Verifying one

```bash
curl 'http://localhost:5000/oslc/step/baselines/bl:70b2bf15c276fbdc?verify=1'
```

`verify_baseline` re-hashes every stored artifact and compares with
the recorded digests:

```json
{
  "id": "bl:70b2bf15c276fbdc",
  "integrity": {
    "verified": true,
    "artifacts": [
      {"path": "SystemPackage.sysml", "sha256": "3629912c…", "status": "ok"},
      ...
    ]
  }
}
```

A `MISSING` status means the bytes under a recorded digest changed or
disappeared — corruption or tampering, detected after the fact.

## Why immutable

PLM released configurations are *promises*: "this design data is
what we reviewed and released." Editing such a record in place would
rewrite history. Baselines behave like git tags + content-addressed
storage: a new release is a new baseline, `derived_from` records the
parent, and old baselines stay valid forever (as long as their
artifacts remain in the store and verify).

## The Python API

```python
from app.api.adapter.namespaces.step.baselines import (
    BaselineInput, create_baseline, verify_baseline,
)

b = create_baseline(BaselineInput(
    title="SRR-1",
    sysml_files=["model/A.sysml", "model/B.sysml"],
    step_files=["geometry/bracket.stp"],
    derived_from="bl:previous-id",
    author="jf"))
print(b["id"])

result = verify_baseline(b["id"])
assert result["verified"]
```

## Relation to OSLC Config Management

The pinned vocabulary (`oslc:Configuration`, `prov:wasDerivedFrom`,
…) matches `pyoslc/vocabularies/config.py` and the OSLC Config spec
so downstream consumers can treat these baseline resources as the
config-managed artifacts they are. What P4 implements is the
*content-model*; exposing the full Config-Management *service*
dialogs (config picker, stream switching) is future work — see
[Where next](../directions.md).