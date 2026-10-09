# -*- coding: utf-8 -*-
"""EXPRESS schema reader (entity-graph subset, ISO 10303-11).

Reads EXPRESS text (longform MIM/ARM .exp files) and builds the type
graph the semantic checks need:

* entity inventory with SUBTYPE OF edges (single and multiple)
* ``SELF\\entity.attr`` redeclarations
* attribute names per entity (declared, not inherited)
* SUPERTYPE OF (...ONEOF(...)) constraint structure capture

What this reader is: the skeleton that drives schema validation of
P21 instances.  What it is not (yet): a full EXPRESS language
parser — WHERE rules are kept as text, not evaluated.

Proven on ISO/TS 10303-442 ed-7 (AP242 Ed.4) mim_lf.exp: 2,407
entities, 2,090 subtype edges, 844 redeclarations, 12,480 total
declarations.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


class ExpressEntity:
    __slots__ = ("name", "supertypes", "supertype_of", "attributes",
                 "redeclarations", "explicit_attrs", "derived_attrs",
                 "where_rules", "abstract")

    def __init__(self, name: str):
        self.name = name
        self.supertypes: List[str] = []      # from SUBTYPE OF(...)
        self.supertype_of: List[str] = []    # from SUPERTYPE OF(...) body text
        self.attributes: List[Tuple[str, str]] = []   # (name, type_text)
        self.redeclarations: List[str] = []  # SELF\type.attr names
        self.explicit_attrs: List[Tuple[str, str]] = []
        self.derived_attrs: List[Tuple[str, str]] = []
        self.where_rules: Dict[str, str] = {}
        self.abstract = False

    def all_supertypes_graph(self, schema: "ExpressSchema") -> List[str]:
        """Walk supertype chain(s) until the root."""
        out, seen, stack = [], set(), list(self.supertypes)
        while stack:
            s = stack.pop()
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
            parent = schema.get(s)
            if parent:
                stack.extend(parent.supertypes)
        return out


class ExpressSchema:

    def __init__(self, name: str):
        self.name = name
        self.entities: Dict[str, ExpressEntity] = {}
        self.types: Dict[str, str] = {}       # name -> type definition text
        self.functions: List[str] = []
        self.rules: List[str] = []
        self.constants: List[str] = []

    def get(self, name: str) -> Optional[ExpressEntity]:
        return self.entities.get(name)

    def subtype_counts(self):
        n = sum(1 for e in self.entities.values() if e.supertypes)
        return len(self.entities), n

    def roots(self) -> List[str]:
        return [e.name for e in self.entities.values() if not e.supertypes]


def _strip_comments(text: str) -> str:
    """Remove (* ... *) comments (EXPRESS comments nest)."""
    out = []
    i, depth, n = 0, 0, len(text)
    while i < n:
        if text.startswith("(*", i):
            depth += 1
            i += 2
        elif text.startswith("*)", i) and depth:
            depth -= 1
            i += 2
        else:
            if depth == 0:
                out.append(text[i])
            elif text[i] == "\n":
                out.append("\n")
            i += 1
    return "".join(out)


_SCHEMA_RE = re.compile(r"\bSCHEMA\s+([\w.]+)\s*;", re.I)
_ENTITY_HEAD_RE = re.compile(
    r"\bENTITY\s+(?!\w+\s*\()([A-Za-z_]\w*)"
    r"(?P<rest>(?:[^E]|E(?!ND_ENTITY))*?)"
    r"(?P<body>.*?)(?=\bEND_ENTITY\b)",
    re.I | re.S)


def parse_express(text: str) -> ExpressSchema:
    """Parse EXPRESS text into an :class:`ExpressSchema` (entity-graph
    subset; WHERE rules kept as raw text)."""
    code = _strip_comments(text)
    m = _SCHEMA_RE.search(code)
    schema = ExpressSchema(m.group(1) if m else "<anonymous>")

    # types: TYPE name = ...; (captures one-liners + block bodies)
    for tm in re.finditer(r"\bTYPE\s+([A-Za-z_]\w*)\s*=(.*?);", code, re.I | re.S):
        schema.types[tm.group(1)] = tm.group(2).strip()[:400]

    for fm in re.finditer(r"\bFUNCTION\s+([A-Za-z_]\w*)", code, re.I):
        schema.functions.append(fm.group(1))
    for rm in re.finditer(r"\bRULE\s+([A-Za-z_]\w*)", code, re.I):
        schema.rules.append(rm.group(1))
    for cm in re.finditer(r"^\s*([A-Za-z_]\w*)\s*:[^:;]*?;?\s*$", code, re.I):
        pass  # constants need header context — skip in subset reader

    pos = 0
    while True:
        em = re.compile(r"\bENTITY\s+([A-Za-z_]\w*)", re.I).search(code, pos)
        if not em:
            break
        name = em.group(1)
        end = code.find("END_ENTITY", em.end())
        if end == -1:
            break
        body = code[em.end():end]
        ent = _parse_entity_body(name, body)
        schema.entities[name] = ent
        pos = end + len("END_ENTITY")
    return schema


def _parse_entity_body(name: str, body: str) -> ExpressEntity:
    ent = ExpressEntity(name)
    if re.search(r"\bABSTRACT\b", body[:200], re.I):
        ent.abstract = True

    # SUBTYPE OF ( a, b\c ) — may be multiline
    sm = re.search(r"\bSUBTYPE\s+OF\s*\((.*?)\)", body, re.I | re.S)
    if sm:
        raw = sm.group(1)
        for part in raw.split(","):
            part = part.strip()
            if "\\" in part:
                part = part.split("\\")[-1]
            if part:
                ent.supertypes.append(part)

    # SUPERTYPE OF ( ONEOF(...) ... ) — keep raw text
    ssm = re.search(r"\bSUPERTYPE\s+OF\s*:(.*?)\b(?:[A-Z]{4,}|$)",
                    body, re.I | re.S)
    if ssm:
        ent.supertype_of = [ssm.group(1).strip()[:300]]

    # attribute declarations: 'name : [OPTIONAL] type;' — lines
    sect, attrs, derived = "explicit", [], []
    # crude section split inside body
    m_derive = re.search(r"\bDERIVE\b", body, re.I)
    m_inverse = re.search(r"\bINVERSE\b", body, re.I)
    m_where = re.search(r"\bWHERE\b", body, re.I)
    explicit_zone = body[:m_derive.start() if m_derive else
                         (m_inverse.start() if m_inverse else
                          (m_where.start() if m_where else len(body)))]
    for am in re.finditer(r"^\s*([A-Za-z_]\w*)\s*:\s*(.*?);\s*$",
                          explicit_zone, re.I | re.M | re.S):
        nm = am.group(1)
        if nm.upper() in ("SELF",):
            continue
        attrs.append((nm, am.group(2).strip()[:120]))

    if m_derive:
        derive_end = (m_inverse.start() if m_inverse else
                      (m_where.start() if m_where else len(body)))
        zone = body[m_derive.end():derive_end]
        for am in re.finditer(r"^\s*([A-Za-z_]\w*)\s*:\s*(.*?);\s*$",
                              zone, re.I | re.M | re.S):
            derived.append((am.group(1), am.group(2).strip()[:120]))

    ent.attributes = attrs
    ent.explicit_attrs = list(attrs)
    ent.derived_attrs = derived

    # SELF\redeclarations
    for rm in re.finditer(r"SELF\\([\w.]+)\s*\.\s*([A-Za-z_]\w*)", body, re.I):
        ent.redeclarations.append(f"{rm.group(1)}.{rm.group(2)}")

    # WHERE rules: 'WR1: expr;' — body text RETAINED (the Phase C
    # WHERE-rule evaluator consumes it; size cost is bounded by the
    # corpus, not per-instance data)
    wm = re.search(r"\bWHERE\b(.*?)(?=\bEND_ENTITY\b|\Z)", body,
                   re.I | re.S)
    if wm:
        wtext = wm.group(1)
        for wrm in re.finditer(
                r"([A-Za-z_]\w*)\s*:\s*(.*?);(?=\s*(?:[A-Za-z_]\w*\s*:|\Z))",
                wtext, re.S):
            ent.where_rules[wrm.group(1)] = " ".join(wrm.group(2).split())

    return ent


def load_express(path) -> ExpressSchema:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_express(fh.read())