# 1. Inspecting a STEP file

Goal: open a real AP242 file from NIST and understand what is inside.

```bash
cd ~/proj/stepper
poetry run stepper inspect tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp
```

Output (trimmed):

```
nist_ctc_01_asme1_ap242-e1.stp
  instances: 4350
  schema: AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF {1 0 10303 442 1 1 4}
  anchors: 0
  top entity types:
    ORIENTED_EDGE    636
    STYLED_ITEM      554
    CARTESIAN_POINT  395
    EDGE_CURVE       318
    AXIS2_PLACEMENT_3D 257
    VECTOR           214
    LINE             214
    VERTEX_POINT     206
```

## Reading this output

- **instances** — the number of data records in the file's DATA
  section. Each is one "thing" in the product model.
- **schema** — which EXPRESS data model the file declares. The `{1 0
  10303 442 1 1 4}` part is the *schema instance identifier*: part
  442 = AP242, edition 4.
- **entity types** — the instance histogram. This file is a
  **B-rep solid model with PMI**: hundreds of edges/points/faces
  (the solid shape), styled items (annotations), and — the "01" test
  case being a GD&T test — dimension and tolerance records.

## The same thing in Python

```python
from stepper import load_p21

p = load_p21("tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp")

print(len(p.instances), "instances")
print(p.schema_names)

hist = p.entity_types()           # dict: type name -> count
top = sorted(hist.items(), key=lambda kv: -kv[1])[:10]
for name, n in top:
    print(f"{name:40s} {n}")
```

## Looking at individual instances

Every instance has an id (`#123`), a type, and arguments:

```python
from stepper import load_p21, ComplexEntity, Ref

p = load_p21("tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp")

# one CARTESIAN_POINT: the tip of a coordinate
inst = next(i for i in p.instances.values()
            if not isinstance(i, ComplexEntity)
            and i.name == "CARTESIAN_POINT")
print(inst)          # CARTESIAN_POINT(3 args)
print(inst.args)     # ['', (1.77, 2.09, 0.0)]  (name + coordinates)

# a COMPLEX entity: one instance carrying SEVERAL types at once
complex_inst = next(i for i in p.instances.values()
                    if isinstance(i, ComplexEntity))
print(complex_inst.types())    # e.g. ['PRODUCT', 'MECHANICAL_CONTEXT', ...]
```

Decoded value types you'll meet:

| P21 syntax | Python value |
|------------|--------------|
| `#123` | `Ref(123)` — reference to another instance |
| `'text'` | `'text'` (escaped `''` already decoded) |
| `.ENUM.` | `Enum('.ENUM.')` |
| `$` | `UNSET` (no value) |
| `*` | `DERIVED` (derived from other values) |
| `(1.0, 2.0)` | Python list |

!!! tip "Why some lines start with `(`"

    Complex entities (`#21=(A() B() C())`) are one instance that
    *is* several types simultaneously — the unit system `(SI_UNIT()
    NAMED_UNIT(...))` pattern you'll see everywhere. stepper models
    them as `ComplexEntity` with a `.parts` list and helper
    `.get(TYPE)` / `.has_type(TYPE)`.

## What's next

Head to [Checking models](check.md) to validate this file against
the AP242 schema.