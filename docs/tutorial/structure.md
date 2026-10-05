# 3. Product structure → OSLC

Goal: extract the product backbone of a STEP file and emit it as
OSLC-shaped linked data.

## Why OSLC

OSLC (Open Services for Lifecycle Collaboration) is the standard REST
dialect lifecycle tools speak — requirements managers (DOORS, Codebeamer),
PLM systems (Teamcenter, Windchill), and quality tools can all consume
an OSLC catalog. stepper's `structure` command turns STEP product data
into that dialect, so a STEP file becomes *queryable, linkable
lifecycle data* instead of a geometry tombstone.

## The command

```bash
cd ~/proj/stepper
poetry run stepper structure tests/fixtures/nist/nist_ctc_01_asme1_ap242-e1.stp \
    --format turtle
```

Output (trimmed):

```turtle
@prefix oslc:  <http://open-services.net/ns/core#> .
@prefix step:  <https://github.com/mycr0ft/stepper/vocab#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

<https://example.org/stepper/file/0> a oslc:Resource ;
    dcterms:title "nist_ctc_01_asme1_ap242-e1.stp" ;
    dcterms:description "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF {1 0 10303 442 1 1 4}" ;
    step:productCount 1 .

<https://example.org/stepper/product/4374> a oslc:Resource ;
    dcterms:identifier "#4374" ;
    dcterms:title "NIST Test Case 1" ;
    step:sourceRef "#4374" .

<https://example.org/stepper/product_definition/4268> a oslc:Resource ;
    dcterms:title "SDR" ;
    sysml:part <https://example.org/stepper/shape_rep/4267> .

<https://example.org/stepper/shape_rep/4267> a oslc:Resource ;
    dcterms:title "SHAPE_REPRESENTATION #4267" ;
    step:geometryItemCount 1 .
```

## Reading this

- **products** — the `PRODUCT` records (the part: "NIST Test Case 1").
- **product definitions** — a product *used in a context*; linked to
  its geometry by `sysml:part` (the property name matches pyoslc's
  SysML vocabulary deliberately — the two domains are linkable).
- **shape representations** — geometry carriers with an item count
  (how much geometry hangs off each).
- **PMI summary** — counts of shape aspects, tolerances, dimensions
  when the file carries them.

Assembly-bearing files (try `nist_ftc_09_asme1_ap242-e1.stp`, 6 MB)
produce 4 products with 4 different geometry kinds — the multi-part
case.

## JSON-LD form

```bash
poetry run stepper structure tests/fixtures/nist/nist_ftc_09_asme1_ap242-e1.stp \
  --format jsonld | python3 -m json.tool | head -40
```

A `@graph` of node objects — the same data, JSON-LD dialect; both
forms are verified to express identical resources in the test suite.

## Python API

```python
from stepper import structure_file

s, jsonld, turtle = structure_file("model.stp")
print(len(s.of_kind("product")), "products")
print(len(s.of_kind("product_definition")), "product definitions")
pmi = s.of_kind("pmi_summary")
if pmi:
    print("PMI counts:", pmi[0].pmi)
```

## What's next

[Serving as OSLC](serve.md) — put this data behind a real OSLC
server and query it over HTTP.