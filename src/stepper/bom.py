"""STEP AP242 MIM instances → ISO/TS 10303-3001 OBP entity model.

Phase C item 2 (the STEP⇄SysML bridge's mapping-table layer): map the
Part 21 instance graph onto the OBP (Business Object Model) classes
whose naming ISO/TS 10303-400 uses for the SysML mapping.

The published MIM→BOM mapping table (-3001, applied to the entities
the AP242 P21 files actually carry — verified against bom.exp from
ap238.org/smrl/data/business_object_models/):

    PRODUCT                          → Part
    PRODUCT_DEFINITION_FORMATION(+_WITH_SPECIFIED_SOURCE)
                                     → PartVersion
    PRODUCT_DEFINITION               → IndividualPartView
    SHAPE_REPRESENTATION             → ExternalGeometricModel
    ADVANCED_BREP_SHAPE_REPRESENTATION
                                     → ExternalAdvancedBrepShapeRepresentation
    MANIFOLD_SURFACE_SHAPE_REPRESENTATION
                                     → ExternalManifoldSurfaceShapeRepresentation
    GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION
                                     → ExternalGeometricallyBoundedWireframeShapeRepresentation
    OTHER SHAPE_REPRESENTATION subtypes → ExternalGeometricModel
    SHAPE_DEFINITION_REPRESENTATION  → (edge) IndividualPartView.definingGeometry
    NEXT_ASSEMBLY_USAGE_OCCURRENCE   → NextAssemblyViewUsage
    CONTEXT_DEPENDENT_SHAPE_REPRESENTATION → AssemblyViewRelationship

Every OBP node keeps its STEP provenance (\"#123\") — the -400 shortform's
assignment/relationship proxies bind these identifiers when the SysML
side consumes them.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .p21 import ComplexEntity, P21File, SimpleEntity, load_p21

__all__ = [
    "OBPNode",
    "OBPModel",
    "to_obp",
    "bom_schema",
]

# -- the mapping table --------------------------------------------------------

MIM_TO_OBP_EXACT = {
    "PRODUCT": "Part",
    "PRODUCT_DEFINITION_FORMATION": "PartVersion",
    "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE": "PartVersion",
    "PRODUCT_DEFINITION": "IndividualPartView",
    "SHAPE_REPRESENTATION": "ExternalGeometricModel",
    "ADVANCED_BREP_SHAPE_REPRESENTATION": "ExternalAdvancedBrepShapeRepresentation",
    "MANIFOLD_SURFACE_SHAPE_REPRESENTATION": "ExternalManifoldSurfaceShapeRepresentation",
    "GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION":
        "ExternalGeometricallyBoundedWireframeShapeRepresentation",
    "NEXT_ASSEMBLY_USAGE_OCCURRENCE": "NextAssemblyViewUsage",
    "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION": "AssemblyViewRelationship",
}

SHAPE_REP_PREFIX = "SHAPE_REPRESENTATION"
MAPPED_KINDS = set(MIM_TO_OBP_EXACT)
UNMAPPED_KINDS = ("APPLIED_", "PRESENTATION_STYLE", "SURFACE_STYLE", "GEOMETRIC_ITEM_SPECIFIC_USAGE")


def bom_schema() -> Dict[str, Any]:
    """The OBP class inventory (from ISO/TS 10303-3001 bom.exp)."""
    import os

    schema_path = os.path.join(os.path.dirname(__file__), "_bom", "bom.exp")
    if not os.path.exists(schema_path):  # corpus checkout, not an install
        return {}
    from .express import load_express

    schema = load_express(schema_path)
    return {
        name: {
            "supertypes": e.supertypes,
            "attributes": list(e.explicit_attrs),
            "abstract": e.abstract,
        }
        for name, e in schema.entities.items()
    }


# -- model ---------------------------------------------------------------------


@dataclass
class OBPNode:
    """One OBP entity built from a STEP instance."""

    obp_class: str          # e.g. "Part" — a bom.exp entity name
    step_ref: str           # provenance: the #id the mapping came from
    name: str = ""
    description: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    obp_refs: List[str] = field(default_factory=list)   # OBP ids this node references


@dataclass
class OBPModel:
    """A P21 file's product structure expressed in OBP classes."""

    file: str = ""
    schema: str = ""
    nodes: Dict[str, OBPNode] = field(default_factory=dict)   # obp id ("obp:Part#123")
    unmapped: Dict[str, int] = field(default_factory=dict)
    report: Dict[str, Any] = field(default_factory=dict)

    def node(self, step_ref: str) -> Optional[OBPNode]:
        """The OBP node mapped from a given STEP #ref."""
        for n in self.nodes.values():
            if n.step_ref == step_ref:
                return n
        return None

    def of_class(self, obp_class: str) -> List[OBPNode]:
        return [n for n in self.nodes.values() if n.obp_class == obp_class]


# -- extraction ----------------------------------------------------------------


def _types(inst) -> List[str]:
    if isinstance(inst, ComplexEntity):
        return inst.types()
    if isinstance(inst, SimpleEntity):
        return [inst.name]
    return []


def _args_of(inst) -> tuple:
    """Positional arguments of a P21 entity (its last-named type's args)."""
    if isinstance(inst, ComplexEntity):
        args = inst.get(_types(inst)[-1]) if inst.types() else ()
        return tuple(args) if isinstance(args, (list, tuple)) else ()
    if isinstance(inst, SimpleEntity):
        return tuple(inst.args) if isinstance(inst.args, (list, tuple)) else ()
    return ()


def _name_of(inst) -> str:
    args = _args_of(inst)
    if len(args) >= 1:
        v = args[0]
        if isinstance(v, str) and v not in ("$", "", "*"):
            return v
        if len(args) >= 2 and isinstance(args[1], str) and args[1] not in ("$", "", "*"):
            return args[1]
    return ""


def to_obp(path_or_file, file_label: str = "-") -> OBPModel:
    """Map a P21 file's AP242 MIM instances onto OBP (10303-3001) classes."""
    p21 = path_or_file if isinstance(path_or_file, P21File) else load_p21(str(path_or_file))
    model = OBPModel(
        file=file_label,
        schema=", ".join(p21.schema_names),
    )
    data = p21.instances

    # pass 1 — class per instance
    instances_by_class: Dict[str, List[tuple]] = {}   # obp_class -> [(ref, inst, mim_name)]
    kind_counts: Counter = Counter()
    for eid, inst in data.items():
        types = _types(inst)
        obp = None
        for t in types:
            if t in MIM_TO_OBP_EXACT:
                obp = MIM_TO_OBP_EXACT[t]
                break
        if obp is None and any(t.startswith(SHAPE_REP_PREFIX) or t.endswith("SHAPE_REPRESENTATION")
                               for t in types):
            obp = "ExternalGeometricModel"
        if obp is None:
            for t in types:
                kind_counts[t] += 1
            continue
        instances_by_class.setdefault(obp, []).append((eid, inst, types[-1]))
        node = OBPNode(
            obp_class=obp,
            step_ref=f"#{eid}",
            name=_name_of(inst),
        )
        # OBP id: class + provenance (deterministic, -400-proxy friendly)
        obp_id = f"obp:{obp}#{eid}"
        # attributes: mirror the MIM args as OBP attrs with camelCase names where known
        node.attributes = _obp_attributes(obp, inst)
        model.nodes[obp_id] = node

    # pass 2 — OBP references (edges in the BOM's own vocabulary)
    _link(model, data)

    # pass — report
    mapped_kinds = Counter()
    for obp, lst in instances_by_class.items():
        mapped_kinds[obp] = len(lst)
    model.report = {
        "instances_total": len(data),
        "mapped": dict(mapped_kinds),
        "mapped_total": sum(mapped_kinds.values()),
        "unmapped_total": sum(kind_counts.values()),
        "unmapped_top": dict(kind_counts.most_common(12)),
    }
    return model


def _obp_attributes(obp_class: str, inst) -> Dict[str, Any]:
    """MIM arguments → OBP attribute names (the -3001 mapping's renamed columns)."""
    types = _types(inst)
    mim = types[-1] if types else ""
    raw = _args_of(inst)
    names = _ATTR_NAMES.get(mim)
    out: Dict[str, Any] = {}
    for i, v in enumerate(raw):
        key = (names[i] if names and i < len(names) else f"arg{i}")
        out[key] = _atom(v)
    return out


def _atom(v):
    from .p21 import Ref
    if isinstance(v, Ref):
        return v  # keep the provenance-carrying Ref (reprs "#123")
    if isinstance(v, str):
        return {"$": None, "*": "derived", "": None}.get(v, v)
    if isinstance(v, (list, tuple)):
        return [_atom(x) for x in v]
    return v


_ATTR_NAMES = {
    # only the entities the bridge actually uses — full tables live in -3001 Annex
    "PRODUCT": ["id", "name", "description", "frame_of_reference"],
    "PRODUCT_DEFINITION_FORMATION": ["id", "description", "of_product"],
    "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE": [
        "id", "description", "of_product", "make_or_buy"],
    "PRODUCT_DEFINITION": ["id", "description", "formation", "frame_of_reference"],
    "NEXT_ASSEMBLY_USAGE_OCCURRENCE": ["id", "name", "description",
                                       "relating_product_definition",
                                       "related_product_definition",
                                       "reference_designator"],
    "SHAPE_REPRESENTATION": ["name", "items", "context_of_items"],
}


def _link(model: OBPModel, data) -> None:
    """Populate obp_refs using the BOM's relations:

    Part → PartVersion.partOf → IndividualPartView.definingGeometry →
    External*GeometricModel; NextAssemblyViewUsage.relating/related.
    """
    version_of = {}     # version obp id -> part obp id
    view_of = {}        # view obp id   -> version obp id
    geom_of = {}        # view obp id   -> geometric model obp id

    from .p21 import Ref
    for oid, n in model.nodes.items():
        if n.obp_class == "PartVersion":
            parent_ref = n.attributes.get("of_product")
            if isinstance(parent_ref, Ref):
                parent = f"obp:Part#{int(parent_ref)}"
                if parent in model.nodes:
                    n.obp_refs.append(parent)
                    version_of[oid] = parent
        elif n.obp_class == "IndividualPartView":
            parent_ref = n.attributes.get("formation")
            if isinstance(parent_ref, Ref):
                parent = f"obp:PartVersion#{int(parent_ref)}"
                if parent in model.nodes:
                    n.obp_refs.append(parent)
                    view_of[oid] = parent

    # SHAPE_DEFINITION_REPRESENTATION links IndividualPartView ↔ ExternalGeometricModel
    # SDR args = [PRODUCT_DEFINITION_SHAPE, representation]; PDS args = [name,
    # description, definition(=PRODUCT_DEFINITION ref, optionally wrapped)]
    for eid, inst in data.items():
        types = _types(inst)
        if "SHAPE_DEFINITION_REPRESENTATION" not in types:
            continue
        sdr_args = _args_of(inst)
        if len(sdr_args) < 2:
            continue
        pds_ref, rep_ref = sdr_args[0], sdr_args[1]
        view_ref = None
        if isinstance(pds_ref, Ref):
            pds = data.get(str(int(pds_ref)))
            pds_types = _types(pds)
            if pds is not None and "PRODUCT_DEFINITION_SHAPE" in pds_types:
                pds_args = _args_of(pds)
                # PDS args: (name, description, definition[, definition_path])
                for cand in pds_args[2:]:
                    if isinstance(cand, Ref):
                        view_ref = int(cand)
                        break
                    if isinstance(cand, (list, tuple)) and cand and isinstance(cand[0], Ref):
                        view_ref = int(cand[0])
                        break
        if isinstance(rep_ref, Ref):
            geom_id = f"obp:ExternalGeometricModel#{int(rep_ref)}"
            view_id = f"obp:IndividualPartView#{view_ref}" if view_ref else None
            if view_id and view_id in model.nodes and geom_id in model.nodes:
                model.nodes[view_id].obp_refs.append(geom_id)

    # NextAssemblyViewUsage: relating/related IndividualPartView refs
    for oid, n in model.nodes.items():
        if n.obp_class == "NextAssemblyViewUsage":
            for key in ("relating_product_definition", "related_product_definition"):
                v = n.attributes.get(key)
                if isinstance(v, Ref):
                    target = f"obp:IndividualPartView#{int(v)}"
                    if target in model.nodes:
                        n.obp_refs.append(target)


def structure_to_obp(model) -> OBPModel:
    """Convenience: reuse the P1 `stepper.structure` extraction as the instance source."""
    from .structure import ProductStructure  # noqa: F401  (typing only; kept for API shape)
    return model  # no-op placeholder; to_obp() already consumes P21 directly


def to_obp_json(model: OBPModel) -> Dict[str, Any]:
    """OBP model as a JSON payload (the -400/vee-consumable form).

    Every node carries: its OBP class (a 10303-3001 entity name), the
    STEP provenance ref, and obp_refs edges in the BOM's own relation
    vocabulary — the payload the pyoslc Vee registry and baselines
    consume (Phase C item 3).
    """
    return {
        "file": model.file,
        "schema": model.schema,
        "obm": "iso-ts-10303-3001",
        "nodes": [
            {
                "id": oid,
                "@type": n.obp_class,
                "name": n.name or None,
                "step_ref": n.step_ref,
                "attributes": {
                    k: (str(v) if isinstance(v, (list, tuple)) and v and hasattr(v[0], "name")
                        else v)
                    for k, v in n.attributes.items()
                },
                "obp_refs": n.obp_refs,
            }
            for oid, n in sorted(model.nodes.items())
        ],
        "report": model.report,
    }


# -- the UUID identity bridge (ISO/TS 10303-400 v12 vocabulary) ----------------

# Hash_based_v5_uuid_attribute: uuid + hash_function + identified_item.
# uuids here are uuid5(content) — the same content-addressing spirit as
# sysmlpy's stable interchange ids (hash the declared identity, never
# the resolved context).

OBUUID_NAMESPACE = "6f1a2f52-9d0e-4b8a-9c1f-0b7a58d2e100"   # stepper OBP uuid ns


def instance_uuid(obp_class: str, step_ref: str, name: str = "") -> str:
    """Hash-based v5 uuid of one OBP node (deterministic across runs and
    machines; stable across unrelated edits — mirrors sysmlpy's
    stable-id rules: hash the declared identity, not resolved state)."""
    import uuid as _uuid

    key = "|".join((obp_class, step_ref, name))
    return str(_uuid.uuid5(_uuid.UUID(OBUUID_NAMESPACE), key))


def uuid_bridge(model: OBPModel) -> Dict[str, Any]:
    """The -400 identity payload for an OBP model:

    - ``attributes`` — one pseudo-instance per OBP node, in the
      Hash_based_v5_uuid_attribute shape
      (``{uuid, hash_function: 'stepper-obp-v1', identified: {...}}``);
    - ``provenance`` — step_ref → uuid (the join key the Vee registry
      resolves STEP-side);
    - ``relationships`` — the obp_refs edges as -400 Uuid_relationship
      rows (uuid_1 + uuid_2 + role).
    """
    uuid_of: Dict[str, str] = {}
    for oid, n in model.nodes.items():
        uuid_of[oid] = instance_uuid(n.obp_class, n.step_ref, n.name)

    return {
        "obm": "iso-ts-10303-400-uuid",
        "hash_function": "stepper-obp-v1",
        "file": model.file,
        "attributes": [
            {
                "uuid": uuid_of[oid],
                "identified": {
                    "obp_class": n.obp_class,
                    "step_ref": n.step_ref,
                    "obp_id": oid,
                },
            }
            for oid, n in sorted(model.nodes.items())
        ],
        "provenance": {
            n.step_ref: uuid_of[oid]
            for oid, n in sorted(model.nodes.items())
        },
        "relationships": [
            {
                "identifier": f"{uuid_of[src]}~{uuid_of[dst]}~references",
                "uuid_1": uuid_of[src],
                "uuid_2": uuid_of[dst],
                "role": "references",
            }
            for src, n in sorted(model.nodes.items())
            for dst in n.obp_refs
            if dst in uuid_of
        ],
    }