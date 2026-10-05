# 5. The Vee link (SysML ↔ STEP)

Goal: connect an element in a SysML model to the STEP data that
realizes it — the actual "Systems-Engineering Vee" join.

## The idea

The Vee model: requirements decompose on the left, the system is
architected in the middle, verification integrates on the right.
In data terms:

- **left/middle** — SysML v2 models (`.sysml`): requirements, part
  definitions, ports, behaviors. sysmlpy parses and analyzes them.
- **right** — STEP AP242 (`.stp`): the concrete geometry, product
  structure, and PMI that realizes those definitions.

The join is a **link table**: one row per identity edge,

```
SysML qualified name        SysML stable @id      STEP instance
'NistModel.NIST Test Case 1' 'sysml:45305c0c-…'    '#4374'
```

## Where each half comes from

**SysML side** — sysmlpy (0.96.4+) attaches a side table to every
stable-ids export:

```python
import sysmlpy
from sysmlpy import to_interchange, qn_registry

m = sysmlpy.loads("""
package NistModel {
    part def 'NIST Test Case 1' {
        attribute thrust : Real;
    }
}
""")
doc = to_interchange(m, stable_ids=True)
qn = qn_registry(doc)
# {'NistModel': 'sysml:…', "NistModel.'NIST Test Case 1'": 'sysml:…', …}
```

The keys are **deduped declared qualified-name paths**; the values
are the stable `@id`s (content-addressed — they survive edits that
insert unrelated siblings, and explicit ids written in the source via
`doc /* @id: … */` survive even renames).

**STEP side** — the seeder/structure payload (tutorial 3): every
STEP resource knows its `step:sourceRef` (`'#4374'`).

## Auto-linking

`POST /oslc/step/vee` with a registry map auto-matches by leaf name
(quoted SysML names stripped before comparing against STEP titles):

```bash
curl -X POST http://localhost:5000/oslc/step/vee \
  -H 'Content-Type: application/json' \
  -d '{"registry": {"NistModel": "sysml:…",
       "NistModel.'\''NIST Test Case 1'\''": "sysml:45305c0c-…"}}'
```

Response:

```json
{"new_links": 1, "status": "ok", "total": 1}
```

The link records:

```json
{"kind": "realizes",
 "step_ref": "#4374",
 "step_resource_id": "4374",
 "sysml_id": "sysml:45305c0c-…",
 "sysml_qn": "NistModel.'NIST Test Case 1'"}
```

## Querying both directions

```bash
# What STEP data realizes this SysML element?
curl 'http://localhost:5000/oslc/step/vee?sysml_qn=NistModel.%27NIST%20Test%20Case%201%27'

# And reverse — which SysML element is THIS STEP instance?
curl 'http://localhost:5000/oslc/step/vee?step_ref=%234374'
```

## Manual links

Auto-matching by name is a convenience; the general case is manual
edges with an explicit kind:

```bash
curl -X POST http://localhost:5000/oslc/step/vee \
  -d '{"sysml_qn": "Spec.Cabin", "sysml_id": "sysml:…",
       "step_ref": "#123", "step_resource_id": "123",
       "kind": "specifies"}'
```

Kinds: `realizes` (the STEP thing is the concrete realization),
`specifies` (the SysML element states what the STEP thing must be),
`traces` (loose provenance).

## Persistence

In-memory by default (matches the demo servers). For a persistent
deployment give the registry a JSON sidecar — the same pattern as
sysmlpy's reconcile registry:

```python
from app.api.adapter.namespaces.step.vee import VeeRegistry

reg = VeeRegistry(sidecar="vee-links.json")
reg.load()      # reads previous links at startup
reg.save()      # writes them after ingest
```

## What's next

[Baselines](baselines.md) — pin a configuration of BOTH sides as a
verifiable released artifact.