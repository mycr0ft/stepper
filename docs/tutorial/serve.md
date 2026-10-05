# 4. Serving STEP as OSLC (pyoslc)

Goal: run the pyoslc OSLC server, load a STEP file into it, and
query the product structure over HTTP.

## Prerequisites

The pyoslc sibling repo (with P2 installed):

```bash
git clone https://github.com/mycr0ft/pyoslc.git ~/proj/pyoslc
cd ~/proj/pyoslc
uv venv && uv sync
uv pip install -e ~/proj/stepper      # the seeder importss stepper
```

## What the P2 integration added

The STEP domain in pyoslc — `app/api/adapter/namespaces/step/` —
serves four resource classes at `/oslc/step/…`:

| endpoint | resource |
|----------|----------|
| `/oslc/step/product` | `step:Product` — one per PRODUCT record |
| `/oslc/step/productDefinition` | `step:ProductDefinition` |
| `/oslc/step/shapeRepresentation` | geometry carriers |
| `/oslc/step/file` | the exchange file itself (provenance) |
| `/oslc/step/vee` | SysML↔STEP identity links (tutorial 5) |
| `/oslc/step/baselines` | released configurations (tutorial 6) |

Plus the service provider in the OSLC catalog: provider `Step-1`
with a query capability and creation factory, and resource shapes at
`/oslc/resourceShapes/stepProduct` (et al.).

## Loading a STEP file

In Python (the seeder's full pipe):

```python
from app import create_app
from app.config import Config
from app.api.adapter.namespaces.step.repository import (
    set_step_repository, InMemoryStepRepository)
from app.api.adapter.namespaces.step.seeder import seed_from_step_file

app = create_app(Config)
app.testing = True
set_step_repository(InMemoryStepRepository())

with app.app_context():
    created = seed_from_step_file(
        "~/proj/stepper/tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp")
    print(f"{len(created)} resources loaded")
```

For automatic app startup, set `STEP_FIXTURES` (colon-separated
paths) and the app factory seeds on start.

## Querying over HTTP

With the Flask app running (`flask run` inside the project with
`FLASK_APP=app`):

```bash
# All products, as JSON-LD
curl -H 'Accept: application/json-ld' http://localhost:5000/oslc/step/product

# One product, as Turtle
curl -H 'Accept: text/turtle' http://localhost:5000/oslc/step/product/4374

# Shape representations
curl -H 'Accept: application/json-ld' http://localhost:5000/oslc/step/shapeRepresentation

# The OSLC catalog now advertises the STEP provider
curl -H 'Accept: application/rdf+xml' http://localhost:5000/oslc/services/catalog | grep -i step
```

The STEP provider appears **in the same catalog** as the SysML and
requirements providers — one discovery point for all Vee domains.

## Resource shapes

OSLC clients discover *what fields a resource carries* through
ResourceShapes:

```bash
curl -H 'Accept: text/turtle' \
  http://localhost:5000/oslc/resourceShapes/stepProduct
```

declares `step:productId`, `step:sourceRef`, `dcterms:title`, … —
the shape stepper's emitter fills.

## The pyoslc-client CLI

```bash
pip install pyoslc-client

pyoslc catalog http://localhost:5000/oslc
pyoslc query http://localhost:5000/oslc/services/provider/Step-1/... \
  --where 'dcterms:identifier="#4374"'
```

## What's next

[The Vee link](vee.md) — connect a SysML model to this STEP data by
shared element identity.