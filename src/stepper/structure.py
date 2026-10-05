# -*- coding: utf-8 -*-
"""P1: product-structure extraction from AP242 P21 files.

`stepper structure file.stp` walks the product backbone — PRODUCT →
PRODUCT_DEFINITION_FORMATION → PRODUCT_DEFINITION → SHAPE_DEFINITION_
REPRESENTATION (+ assembly links when NEXT_ASSEMBLY_USAGE_OCCURRENCE
is present) — and emits OSLC-shaped resources:

* each PRODUCT_DEFINITION becomes an ``oslc:Resource`` whose shape is
  ``.../shapes/ProductDefinition``
* the shape representation becomes a ``sysml:part``-style contained
  resource (geometry carrier)
* SHAPE_ASPECT / tolerance counts ride as dcterms properties (PMI
  summary)
* P21 ANCHOR section UUIDs (edition-3 files) become ``@id``s;
  files without anchors fall back to position-stable ids derived
  from the instance number (documented fallback, same lesson as
  sysmlpy stable_ids vs position).

The vocabulary is exactly pyoslc's ``OSLC_SYSML`` namespace
(``https://www.omg.org/spec/sysml/vocabulary#`` — namespace match
probed against pyoslc itself) so the emitted resources load into a
sysml-pyOSLC server without translation.

Emitters return plain Python dicts (JSON-LD-ready) and Turtle text;
both are produced from one normalized intermediate model
(:class:`ProductStructure`).
"""

from __future__ import annotations

import json
import os.path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .p21 import ComplexEntity, P21File, Ref, SimpleEntity, load_p21

# pyoslc-compatible namespaces (verified: pyoslc.vocabularies.sysml)
OSLC_SYSML = "https://www.omg.org/spec/sysml/vocabulary#"
OSLC_CORE = "http://open-services.net/ns/core#"
DCTERMS = "http://purl.org/dc/terms/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


# ---------------------------------------------------------------------------
# normalized intermediate
# ---------------------------------------------------------------------------

@dataclass
class StructureNode:
    """One extracted product-structure element."""

    kind: str            # "product" | "product_definition" | "shape_rep" |
                         # "assembly_usage" | "pmi_summary"
    ref: str             # STEP instance id as "#123"
    name: str = ""
    description: str = ""
    product_ref: Optional[str] = None
    formation_ref: Optional[str] = None
    definition_ref: Optional[str] = None
    shape_kind: Optional[str] = None      # SHAPE_REPRESENTATION subtype
    geometry: Dict[str, Any] = field(default_factory=dict)   # counts
    pmi: Dict[str, int] = field(default_factory=dict)        # PMI counts
    linked_refs: List[str] = field(default_factory=list)     # outgoing STEP refs
    linked_from: List[str] = field(default_factory=list)     # incoming SDR sources


@dataclass
class ProductStructure:
    """Normalized product structure of one P21 file."""

    file: str
    schema: str = ""
    nodes: List[StructureNode] = field(default_factory=list)
    anchors: Dict[str, str] = field(default_factory=dict)

    def of_kind(self, kind: str) -> List[StructureNode]:
        return [n for n in self.nodes if n.kind == kind]


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

_SHAPE_REP_SUFFIX = "SHAPE_REPRESENTATION"


def _walk_instance_args(inst, out: List[Any]):
    if isinstance(inst, ComplexEntity):
        for part in inst.parts:
            out.extend(part.args)
    else:
        out.extend(inst.args)


def extract_structure(path_or_file, file_label: str = "-") -> ProductStructure:
    """Extract the product structure from a P21 file (path or loaded)."""
    p21 = path_or_file if isinstance(path_or_file, P21File) else load_p21(
        str(path_or_file))
    schema = ", ".join(
        n.split("(")[0].strip("('\"") for n in p21.schema_names
    ) or ""
    out = ProductStructure(file=file_label, schema=schema,
                           anchors=dict(p21.anchors))

    # index by ref for resolution
    data = p21.instances

    def name_of(instance_id: str) -> str:
        inst = data.get(instance_id)
        if inst is None:
            return ""
        if isinstance(inst, ComplexEntity):
            return inst.types()[-1] if inst.types() else ""
        return inst.name

    # -- products -----------------------------------------------------
    products = {}
    for eid, inst in data.items():
        if isinstance(inst, ComplexEntity) and inst.has_type("PRODUCT"):
            products[eid] = inst
        elif (isinstance(inst, SimpleEntity) and inst.name == "PRODUCT"):
            products[eid] = inst

    for eid, prod in products.items():
        args = (prod.get("PRODUCT").args if isinstance(prod, ComplexEntity)
                else prod.args)
        node = StructureNode(
            kind="product", ref=f"#{eid}",
            name=args[0] if len(args) > 0 else "",
            description=(args[1] or args[2]) if len(args) > 2 else "",
        )
        out.nodes.append(node)

    # -- product definitions ------------------------------------------
    for eid, inst in data.items():
        if isinstance(inst, ComplexEntity) or \
                not (isinstance(inst, SimpleEntity)
                     and inst.name == "PRODUCT_DEFINITION"):
            continue
        args = inst.args
        formation = args[2] if len(args) > 2 else None
        node = StructureNode(
            kind="product_definition", ref=f"#{eid}",
            name=args[1] or args[0] or "",
            formation_ref=(f"#{int(formation)}" if isinstance(formation, Ref)
                           else None),
        )
        # resolve formation -> product
        if node.formation_ref:
            fid = node.formation_ref[1:]
            form = data.get(fid)
            pref = None
            if isinstance(form, SimpleEntity) and form.name == \
                    "PRODUCT_DEFINITION_FORMATION":
                pref = form.args[2]
            if isinstance(pref, Ref):
                node.product_ref = f"#{int(pref)}"
        out.nodes.append(node)

    # -- shape_definition_representation: PD -> shape rep -------------
    sdrs = []
    for eid, inst in data.items():
        if not isinstance(inst, ComplexEntity) and \
                isinstance(inst, SimpleEntity) and \
                inst.name.endswith(_SHAPE_REP_SUFFIX):
            # A shape representation itself — count contents
            _collect_shape_rep(inst, f"#{eid}", out)
        elif not isinstance(inst, ComplexEntity) and \
                isinstance(inst, SimpleEntity) and \
                inst.name == "SHAPE_DEFINITION_REPRESENTATION":
            sdrs.append((eid, inst))

    for eid, sdr in sdrs:
        # SDR(name?, definition, used_representation) — some CAD exports
        # omit the name attribute; find the two Ref args in order.
        refs = [a for a in sdr.args if isinstance(a, Ref)]
        node = StructureNode(
            kind="product_definition", ref=f"#{eid}",
            name=str(sdr.args[0] or "SDR") if sdr.args
                 and not isinstance(sdr.args[0], Ref) else "SDR",
            definition_ref=(f"#{int(refs[0])}" if refs else None),
            shape_kind="definition",
        )
        out.nodes.append(node)
        rep_ref = refs[1] if len(refs) > 1 else None
        if isinstance(rep_ref, Ref):
            # find the rep's own node or add a summary
            _collect_shape_rep(data.get(str(int(rep_ref))),
                               f"#{int(rep_ref)}", out, linked_from=node.ref)

    # -- PMI counts ----------------------------------------------------
    hist: Dict[str, int] = {}
    for inst in (i for i in data.values()):
        if isinstance(inst, ComplexEntity):
            for t in inst.types():
                hist[t] = hist.get(t, 0) + 1
        else:
            hist[inst.name] = hist.get(inst.name, 0) + 1
    pmi_types = [t for t in hist if t in (
        "SHAPE_ASPECT", "GEOMETRIC_TOLERANCE", "DIMENSIONAL_SIZE",
        "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION",
        "PLANE_ANGLE_MEASURE_WITH_UNIT",
        "DESCRIPTIVE_REPRESENTATION_ITEM")]
    if pmi_types:
        out.nodes.append(StructureNode(
            kind="pmi_summary", ref="#0", name="PMI summary",
            pmi={t: hist[t] for t in pmi_types},
        ))

    # -- assembly occurrences (when present) ---------------------------
    for eid, inst in data.items():
        is_nauo = (not isinstance(inst, ComplexEntity)
                   and inst.name == "NEXT_ASSEMBLY_USAGE_OCCURRENCE")
        nauo_complex = (isinstance(inst, ComplexEntity)
                        and inst.has_type("NEXT_ASSEMBLY_USAGE_OCCURRENCE"))
        if not (is_nauo or nauo_complex):
            continue
        args = (inst.get("NEXT_ASSEMBLY_USAGE_OCCURRENCE").args
                if isinstance(inst, ComplexEntity) else inst.args)
        out.nodes.append(StructureNode(
            kind="assembly_usage", ref=f"#{eid}",
            name=args[0] or args[1] or "",
            linked_refs=[f"#{int(a)}" for a in args if isinstance(a, Ref)],
        ))

    return out


def _collect_shape_rep(inst, ref: str, out: ProductStructure,
                       linked_from: Optional[str] = None):
    """Add a shape_rep node with a geometry summary (or extend the
    linked_from list when the same rep is referenced again)."""
    if inst is None:
        return
    label = inst.types()[0] if isinstance(inst, ComplexEntity) else inst.name
    args = (inst.args if not isinstance(inst, ComplexEntity)
            else inst.get(label).args if inst.get(label) else [])
    items = [f"#{int(a)}" for a in args if isinstance(a, Ref)]
    for existing in out.nodes:
        if existing.kind == "shape_rep" and existing.ref == ref:
            if linked_from and linked_from not in existing.linked_from:
                existing.linked_from.append(linked_from)
            return
    node = StructureNode(
        kind="shape_rep", ref=ref, name=label, shape_kind=label,
        geometry={"items": len(items)},
        linked_refs=items,
        linked_from=[linked_from] if linked_from else [],
    )
    out.nodes.append(node)


# ---------------------------------------------------------------------------
# OSLC emission
# ---------------------------------------------------------------------------

def _oslc_id(label: str, ref: str, base: str) -> str:
    """Stable URL for a STEP element.  Uses the ANCHOR uuid when the file
    carries one; the STEP instance ref otherwise (documented fallback)."""
    return f"{base}{label}/{ref.lstrip('#')}"


_STEP_VOCAB = "https://github.com/mycr0ft/stepper/vocab#"


def to_oslc_jsonld(struct: ProductStructure,
                   base: str = "https://example.org/stepper/") -> dict:
    """Emit OSLC-shaped JSON-LD (a @graph of resources)."""
    ctx = {
        "oslc": OSLC_CORE,
        "sysml": OSLC_SYSML,
        "dcterms": DCTERMS,
        "rdf": RDF,
        "stepper": _STEP_VOCAB,
    }
    graph: List[dict] = []

    file_uri = _oslc_id("file", "0", base)
    graph.append({
        "@id": file_uri,
        "@type": "oslc:Resource",
        "dcterms:identifier": struct.file,
        "dcterms:title": os.path.basename(struct.file)
        if "/" in struct.file or "\\" in struct.file else struct.file,
        "dcterms:description": struct.schema,
        "stepper:productCount": len(struct.of_kind("product")),
    })

    for p in struct.of_kind("product"):
        graph.append({
            "@id": _oslc_id("product", p.ref, base),
            "@type": "oslc:Resource",
            "dcterms:identifier": p.ref,
            "dcterms:title": p.name or "(unnamed product)",
            "dcterms:description": p.description,
        })

    # PD -> [product, shape reps]: one link list per PD
    shape_reps_by_source: Dict[str, List[StructureNode]] = {}
    for sr in struct.of_kind("shape_rep"):
        if sr.ref == "#0":
            continue
        # the SDR node carries its rep ref in linked_refs; the SDR node's
        # own ref is the SDR instance, the linked ref the rep
        for src in sr.linked_from or []:
            shape_reps_by_source.setdefault(src, []).append(sr)

    for pd in struct.of_kind("product_definition"):
        res: Dict[str, Any] = {
            "@id": _oslc_id("product_definition", pd.ref, base),
            "@type": "oslc:Resource",
            "dcterms:identifier": pd.ref,
            "dcterms:title": pd.name or f"Product definition {pd.ref}",
        }
        parts: List[dict] = []
        if pd.product_ref:
            parts.append({"@id": _oslc_id("product", pd.product_ref, base)})
        for src, reps in shape_reps_by_source.items():
            if src == pd.ref:
                parts.extend({"@id": _oslc_id("shape_rep", s.ref, base)}
                             for s in reps)
        if parts:
            res["sysml:part"] = parts
        graph.append(res)

    seen = set()
    for sr in struct.of_kind("shape_rep"):
        if sr.ref == "#0" or sr.ref in seen:
            continue
        seen.add(sr.ref)
        graph.append({
            "@id": _oslc_id("shape_rep", sr.ref, base),
            "@type": "oslc:Resource",
            "dcterms:identifier": sr.ref,
            "dcterms:title": f"{sr.shape_kind} {sr.ref}",
            "stepper:geometryItemCount": sr.geometry.get("items", 0),
        })

    pmi = struct.of_kind("pmi_summary")
    if pmi:
        graph.append({
            "@id": _oslc_id("pmi", pmi[0].ref, base),
            "@type": "oslc:Resource",
            "dcterms:title": "PMI summary",
            **{f"stepper:{k.lower()}": v for k, v in pmi[0].pmi.items()},
        })

    return {"@context": ctx, "@graph": graph}


def to_oslc_turtle(struct: ProductStructure,
                   base: str = "https://example.org/stepper/") -> str:
    """Emit the same resources as Turtle (mirrors to_oslc_jsonld)."""
    lines = [
        f"@prefix oslc: <{OSLC_CORE}> .",
        f"@prefix sysml: <{OSLC_SYSML}> .",
        f"@prefix dcterms: <{DCTERMS}> .",
        f"@prefix rdf: <{RDF}> .",
        f"@prefix stepper: <{_STEP_VOCAB}> .",
        "",
    ]

    def esc(s: str) -> str:
        return (s or "").replace("\\", "\\\\").replace('"', '\\"') \
                         .replace("\n", "\\n")

    def statement(uri: str, preds):
        """Emit one subject with list-of-(predicate, object) pairs."""
        out = [f"<{uri}>"]
        chunks = []
        for pred, obj in preds:
            chunks.append(f"    {pred} {obj}")
        out.append(" ;\n".join(chunks))
        return " ;\n".join(["\n".join(out[:1])] + chunks) + " .\n"

    def s_literal(v: str) -> str:
        return f'"{esc(v)}"'

    file_uri = _oslc_id("file", "0", base)
    title = (os.path.basename(struct.file)
             if "/" in struct.file or "\\" in struct.file
             else struct.file)
    lines.append(statement(file_uri, [
        ("a", "oslc:Resource"),
        ("dcterms:identifier", s_literal(struct.file)),
        ("dcterms:title", s_literal(title)),
        ("dcterms:description", s_literal(struct.schema)),
        ("stepper:productCount",
         str(len(struct.of_kind("product")))),
    ]))

    for p in struct.of_kind("product"):
        uri = _oslc_id("product", p.ref, base)
        preds = [
            ("a", "oslc:Resource"),
            ("dcterms:identifier", s_literal(p.ref)),
            ("dcterms:title", s_literal(p.name or "(unnamed product)")),
            ("dcterms:description", s_literal(p.description)),
        ]
        lines.append(statement(uri, preds))

    shape_reps_by_source: Dict[str, List[StructureNode]] = {}
    for sr in struct.of_kind("shape_rep"):
        if sr.ref == "#0":
            continue
        for src in sr.linked_from or []:
            shape_reps_by_source.setdefault(src, []).append(sr)

    for pd in struct.of_kind("product_definition"):
        uri = _oslc_id("product_definition", pd.ref, base)
        preds = [
            ("a", "oslc:Resource"),
            ("dcterms:identifier", s_literal(pd.ref)),
            ("dcterms:title",
             s_literal(pd.name or f"Product definition {pd.ref}")),
        ]
        parts = []
        if pd.product_ref:
            parts.append(f"<{_oslc_id('product', pd.product_ref, base)}>")
        for src, reps in shape_reps_by_source.items():
            if src == pd.ref:
                parts.extend(f"<{_oslc_id('shape_rep', s.ref, base)}>"
                             for s in reps)
        if parts:
            parts_str = ",\n        ".join(parts)
            preds.append(("sysml:part", parts_str))
        lines.append(statement(uri, preds))

    seen = set()
    for sr in struct.of_kind("shape_rep"):
        if sr.ref == "#0" or sr.ref in seen:
            continue
        seen.add(sr.ref)
        uri = _oslc_id("shape_rep", sr.ref, base)
        lines.append(statement(uri, [
            ("a", "oslc:Resource"),
            ("dcterms:identifier", s_literal(sr.ref)),
            ("dcterms:title", s_literal(f"{sr.shape_kind} {sr.ref}")),
            ("stepper:geometryItemCount",
             str(sr.geometry.get("items", 0))),
        ]))

    pmi = struct.of_kind("pmi_summary")
    if pmi:
        uri = _oslc_id("pmi", pmi[0].ref, base)
        preds = [("a", "oslc:Resource"),
                 ("dcterms:title", s_literal("PMI summary"))]
        for k, v in pmi[0].pmi.items():
            preds.append((f"stepper:{k.lower()}", str(v)))
        lines.append(statement(uri, preds))

    return "\n".join(lines)


def structure_file(path, base: str = "https://example.org/stepper/"):
    """Convenience: extract + emit both forms (returned as a tuple)."""
    label = str(path)
    s = extract_structure(path, file_label=label)
    return s, to_oslc_jsonld(s, base), to_oslc_turtle(s, base)