# -*- coding: utf-8 -*-
"""WHERE-rule evaluator — Phase C item 4 (scoped, stratified).

Evaluates the decidable subset of ISO 10303-11 WHERE-rule expressions
against Part 21 instance data, and CLASSIFIES the rest (reported as
not-evaluated, never silently dropped):

Stratum A — evaluated here:
  * attribute-chain comparisons:  ``a.b :<>: c.d``, ``x = y``, ordering
  * ``EXISTS(attr)`` / ``NOT EXISTS …``
  * ``IN`` / list-set membership on chains
  * ``NOT``/``AND``/``OR`` combinators of the above
  * ``TYPEOF(v : T)`` — via the schema's supertype closure
  * ``SIZEOF(chain) > 0``-style plain size tests
  * ``SELF <> …`` instance-identity tests

Stratum C — classified, NOT evaluated (reported per rule):
  * ``QUERY(<* … | …)`` collection logic
  * ``USEDIN`` (needs the whole-file inverse index — phase 2)
  * calls to schema-local FUNCTIONs (make_elementary_space et al.)

The classic decision here mirrors the check gate's advisory-by-default:
a rule we can parse but not evaluate stays a *label*, never a false
failure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .express import ExpressSchema
from .p21 import ComplexEntity, P21File, Ref, SimpleEntity

__all__ = [
    "WhereFinding", "WhereResult", "evaluate_entity",
    "evaluate_where_rules", "rule_family",
]


# -- finding + result ----------------------------------------------------------


@dataclass
class WhereFinding:
    instance: str          # '#123'
    entity: str            # schema entity name
    rule: str              # 'WR1'
    outcome: str           # 'fail' | 'pass' | 'indeterminate' | 'unevaluated'
    family: str            # decided family or the C-stratum kind
    detail: str = ""

    def as_dict(self):
        return {"instance": self.instance, "entity": self.entity,
                "rule": self.rule, "outcome": self.outcome,
                "family": self.family, "detail": self.detail}


@dataclass
class WhereResult:
    rules_seen: int = 0
    rules_evaluated: int = 0
    rules_unevaluated: int = 0
    failures: List[WhereFinding] = field(default_factory=list)
    indeterminate: List[WhereFinding] = field(default_factory=list)
    families: Dict[str, int] = field(default_factory=dict)

    def as_dict(self):
        return {
            "rules_seen": self.rules_seen,
            "rules_evaluated": self.rules_evaluated,
            "rules_unevaluated": self.rules_unevaluated,
            "failures": [f.as_dict() for f in self.failures],
            "indeterminate": [f.as_dict() for f in self.indeterminate][:100],
            "families": dict(self.families),
        }


# -- the expression tokenizer ---------------------------------------------------

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>\(\*.*?\*\))
  | (?P<string>'(?:[^']|'')*')
  | (?P<number>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<kw>[A-Za-z_]\w*)
  | (?P<self>SELF)
  | (?P<op><>|:=|:=:|:<>:|<=|>=|\.\.|[,()\[\]{}=<>:+*/|!&])
""", re.X | re.S)

KEYWORDS = {"AND", "OR", "NOT", "IN", "EXISTS", "TYPEOF", "SIZEOF", "QUERY",
            "USEDIN", "TRUE", "FALSE", "UNKNOWN", "SELF", "OPTIONAL",
            "BAG", "SET", "OF", "MOD", "DIV"}

AND_KWS = KEYWORDS


def _token_pos(tokens, target) -> int:
    for i, tok in enumerate(tokens):
        if tok is target:
            return i
    return -1


def _tokenize(expr: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            pos += 1          # tolerate unknown byte (robust reader stance)
            continue
        kind = m.lastgroup
        text = m.group()
        pos = m.end()
        if kind in ("ws", "comment"):
            continue
        out.append((kind, text))
    return out


# -- family classification (cheap, before any evaluation) ------------------------

_QUERY_RE = re.compile(r"\bQUERY\s*\(", re.I)
_USEDIN_RE = re.compile(r"\bUSEDIN\s*\(", re.I)
_FUNC_CALL_RE = re.compile(r"\b[a-z]\w+\s*\(", re.I)


_QUERY_VAR_RE = re.compile(r"QUERY\s*\(\s*([A-Za-z_]\w*)\s*<", re.I)


def _query_vars(expr: str) -> set:
    """Variables bound by QUERY expressions in this rule."""
    return {m.group(1).lower() for m in _QUERY_VAR_RE.finditer(expr)}


def _chain_anchors(tokens: List[Tuple[str, str]]) -> List[Tuple[str, List[str]]]:
    """Every attribute-chain anchor in a token stream: (anchor, path-names).

    Chains start at a kw that is NOT a builtin (after a '(', a '.', or
    an operator position) and extend through '.' hops. Builtin heads
    (EXISTS/SIZEOF/TYPEOF/QUERY/USEDIN) are transparent.
    """
    builtins = {"EXISTS", "SIZEOF", "TYPEOF", "QUERY", "USEDIN", "NOT",
                "AND", "OR", "IN", "SELF", "TRUE", "FALSE", "UNKNOWN",
                "BAG", "SET", "OF", "OPTIONAL", "MOD", "DIV"}
    anchors = []
    i = 0
    n = len(tokens)
    while i < n:
        kind, text = tokens[i]
        if kind == "kw" and text.upper() not in builtins:
            # is this a chain start? (prev is '(' or ',' or an op — not '.')
            prev = tokens[i - 1][1] if i else "("
            if prev in ("(", ",", "=") or (prev in ("<", ">", "<=", ">=",
                                                  "<>", ":<>:", ":=:")):
                path = [text]
                j = i + 1
                while j + 1 < n and tokens[j][1] == "." and tokens[j + 1][0] == "kw":
                    path.append(tokens[j + 1][1])
                    j += 2
                anchors.append((text, path))
                i = j
                continue
        i += 1
    return anchors


def rule_family(expr: str) -> str:
    """C-stratum kinds win; otherwise the (evaluable) A-stratum label.
    QUERY is EVALUABLE since Phase C item 4 v2 (per-member binding); the
    tokenizer + _eval_query handle it."""
    if _USEDIN_RE.search(expr):
        return "usedin"
    if re.search(r"\b[a-z]\w+\s*\(", expr):     # schema-local function call
        return "function-call"
    return "evaluable"


# -- a recursive-descent evaluator over the token stream -------------------------

class _Eval:
    """One instance's variable environment + the P21 resolution context."""

    def __init__(self, p21: P21File, schema: ExpressSchema,
                 instance_id: str, entity_name: str):
        self.p21 = p21
        self.schema = schema
        self.instance_id = instance_id          # str (the p21 key)
        self.entity_name = entity_name
        self.instance = p21.instances.get(instance_id)
        self._layouts: Dict[str, Dict[str, int]] = {}

    def instance_types(self) -> List[str]:
        if self.instance is None:
            return []
        if isinstance(self.instance, SimpleEntity):
            return [self.instance.name]
        return self.instance.types() if isinstance(self.instance, ComplexEntity) else []

    # -- value resolution -------------------------------------------------
    def args(self, inst) -> tuple:
        if isinstance(inst, ComplexEntity):
            types = inst.types()
            if types:
                v = inst.get(types[-1])
                return tuple(v) if isinstance(v, (list, tuple)) else ()
        elif isinstance(inst, SimpleEntity):
            return tuple(inst.args) if isinstance(inst.args, (list, tuple)) else ()
        return ()

    def _casefold_entity(self, name: str):
        """Entity lookup tolerant of writer case drift (PAIR vs pair)."""
        ents = self.schema.entities
        if name in ents:
            return ents[name]
        upper = {n.upper(): n for n in ents}
        return ents.get(upper.get(name.upper(), name))

    def attr_layout(self, entity_name: str) -> Dict[str, int]:
        """Cumulative arg-positional layout of an entity: inherited
        attributes FIRST (root supertype's attrs come before the
        subtype's own), matching how Part 21 writes complex/simple
        instance arguments. Redeclared attrs (SELF + backslash + x.y)
        map to the inherited position."""
        cached = self._layouts.get(entity_name)
        if cached is not None:
            return cached
        ents = self.schema.entities

        def visit(name: str, stack: set, order: List[str]) -> None:
            if name in stack or name in order or name is None:
                return
            ent = ents.get(name) or self._casefold_entity(name)
            if ent is None:
                return
            # visit supertypes first (they contribute earlier positions)
            for sup in ent.supertypes:
                visit(sup, stack | {name}, order)
            if name not in order:
                order.append(name)

        order: List[str] = []
        visit(entity_name, set(), order)
        layout: Dict[str, int] = {}
        idx = 0
        for name in order:
            ent = ents.get(name) or self._casefold_entity(name)
            for attr_name, _type_text in ent.attributes:
                key = attr_name.lower()
                if key not in layout:      # first (redeclaration) wins
                    layout[key] = idx
                    idx += 1
            # derived attrs occupy NO argument position in Part 21 files
            # (computed; ISO 10303-21 carries only explicit/inherited)
            for attr_name, _expr in ent.derived_attrs:
                layout.setdefault(attr_name.lower(), idx)
        self._layouts[entity_name] = layout
        return layout

    def attr_index(self, entity_name: str, attr: str) -> Optional[int]:
        """Positional index of `attr` in entity's full arg layout."""
        layout = self.attr_layout(entity_name)
        return layout.get(attr.lower())

    def resolve_attr(self, attr_chain_head_entity: str, attr: str):
        """Attr → (part_args, idx) for the instance THIS eval anchors.

        Complex entities store ONE arg-list PER PART (ComplexEntity.get(type));
        the layout's linear index is valid only against the OWNING part's
        arg tuple. Walks the part types to find the part declaring `attr`.
        Returns (args_tuple, idx) or None."""
        entity = self._casefold_entity(attr_chain_head_entity)
        if entity is None:
            return None
        attr_l = attr.lower()
        # the attr may live on a supertype of the anchor entity — candidate
        # parts = the instance's declared types + their supertype closures
        for part_type in self.instance_types():
            part_entity = self._casefold_entity(part_type)
            if part_entity is None:
                continue
            # layout of the PART's own entity (its inherited chain)
            layout = self.attr_layout(part_entity.name if hasattr(part_entity, "name") else part_type)
            if attr_l in layout:
                idx = layout[attr_l]
                args = self.args_of_part(part_type)
                if idx < len(args):
                    return args, idx
        return None

    def args_of_part(self, part_type: str):
        """The args of one PART of a complex instance (or the whole args of
        a simple instance). ComplexEntity.get returns EITHER a raw list of
        args or the part's internal object carrying .args — handle both."""
        inst = self.instance
        if isinstance(inst, ComplexEntity):
            try:
                v = inst.get(part_type)
            except Exception:
                return ()
            if isinstance(v, (list, tuple)):
                return tuple(v)
            for attr in ("args", "parameters", "params", "values"):
                inner = getattr(v, attr, None)
                if isinstance(inner, (list, tuple)):
                    return tuple(inner)
            return ()
        return self.args(inst)

    def value_of_chain(self, chain: List[str]) -> List[Any]:
        """SELF backslash-entity.attr(.attr)* → derefed values (bag flattening)."""
        names = list(chain)
        if names and names[0].lower() == "self":
            names = names[1:]
        self.last_attr_status = None      # set when the anchor attr is special
        if names and self.instance is not None:
            anchor = names[0]
            types = ([self.instance.name] if isinstance(self.instance, SimpleEntity)
                     else (self.instance.types()
                           if isinstance(self.instance, ComplexEntity) else []))
            for t in reversed(types):
                e = self._casefold_entity(t)
                if e is None:
                    continue
                if any(a[0].lower() == anchor.lower() for a in e.derived_attrs):
                    self.last_attr_status = "derived-attr"
                    break
        # the token after SELF\ may be the REDECLARED ENTITY name — skip it
        if (names and self.entity_name
                and names[0] in self.schema.entities
                and names[0].lower().replace("_", "")   # entity not attr-like
                and len(names) > 1
                and names[0] != self.attr_root_of(names)):
            names = names[1:]          # drop an entity anchor when more names follow
        cur = self.instance
        # hop 1: the instance's own attribute
        while names and cur is not None:
            attr = names[0]
            resolved = None
            if cur is self.instance and self.entity_name:
                resolved = self.resolve_attr(self.entity_name, attr)
            if resolved is None:
                # generic walk (member instances inside QUERY bodies etc.)
                idx = None
                types = ([cur.name] if isinstance(cur, SimpleEntity)
                         else (cur.types() if isinstance(cur, ComplexEntity) else []))
                for t in reversed(types):
                    idx = self.attr_index(t, attr)
                    if idx is not None:
                        break
                if idx is None:
                    return []
                args = self.args(cur)
                if idx >= len(args):
                    return []
                head = names[1:]
                return self._walk(args[idx], head)
            resolved_args, idx = resolved
            head = names[1:]
            return self._walk(resolved_args[idx], head)
        return []

    def attr_root_of(self, names: List[str]) -> Optional[str]:
        """If names[0] is an ATTRIBUTE of the anchor, return it (else None)."""
        if self.instance is None:
            return None
        return names[0] if self.attr_index(self.entity_name, names[0]) is not None else None

    def _walk(self, v, rest: List[str]) -> List[Any]:
        """Deref v (Ref/compound) then continue down `rest` (bags flatten)."""
        values = self._deref(v)
        if not rest:
            return values
        out = []
        for item in values:
            if isinstance(item, (ComplexEntity, SimpleEntity)):
                cur = item
                attr = rest[0]
                idx = None
                types = ([cur.name] if isinstance(cur, SimpleEntity)
                         else (cur.types() if isinstance(cur, ComplexEntity) else []))
                for t in reversed(types):
                    idx = self.attr_index(t, attr)
                    if idx is not None:
                        break
                if idx is None:
                    continue
                args = self.args(cur)
                if idx >= len(args):
                    continue
                out.extend(self._walk(args[idx], rest[1:]))
        return out

    def _deref(self, v) -> List[Any]:
        """Resolve refs; a list is a BAG — SIZEOF sees its top-level
        members, so nested lists stay intact (inner items resolved
        only when a later chain hop descends into them)."""
        if isinstance(v, (list, tuple)):
            out = []
            for x in v:
                if isinstance(x, Ref):
                    inst = self.p21.instances.get(str(int(x)))
                    if inst is not None:
                        out.append(inst)
                else:
                    out.append(x)
            return out
        if isinstance(v, Ref):
            inst = self.p21.instances.get(str(int(v)))
            return [inst] if inst is not None else []
        return [v]

    # -- the grammar --------------------------------------------------------
    def eval_expr(self, tokens: List[Tuple[str, str]]) -> bool:
        """Evaluate a boolean expression (A-stratum); raises _Uneval on
        anything outside the grammar."""
        val, pos = self.parse_or(tokens, 0)
        if pos != len(tokens):
            raise _Uneval("trailing tokens")
        return val

    def parse_or(self, t, i):
        left, i = self.parse_and(t, i)
        while i < len(t) and t[i][1].upper() == "OR":
            right, i = self.parse_and(t, i + 1)
            left = left or right
        return left, i

    def parse_and(self, t, i):
        left, i = self.parse_not(t, i)
        while i < len(t) and t[i][1].upper() == "AND":
            right, i = self.parse_not(t, i + 1)
            left = left and right
        return left, i

    def parse_not(self, t, i):
        if i < len(t) and t[i][1].upper() == "NOT":
            v, i = self.parse_not(t, i + 1)
            return (not v), i
        return self.parse_comparison(t, i)

    def parse_comparison(self, t, i):
        left, i = self.parse_primary(t, i)
        if i < len(t) and (t[i][0] == "op" or
                           (t[i][0] == "kw" and
                            t[i][1].upper() in ("IN",))):
            op = t[i][1]
            op_up = t[i][1].upper()
            # IN membership (ISO 10303-11: 'a IN set'; the set side is a
            # TYPEOF-string list, an aggregate value, or a select type)
            if op_up == "IN":
                right, j = self.parse_primary(t, i + 1)
                return self._in_test(left, right), j
            if op == "*":     # select-multiply: 'Schema.Type' * TYPEOF(SELF)
                right, j = self.parse_primary(t, i + 1)
                return self._in_test(right, left), j
            rhs_ops = {"=", "!=", "<>", ":", "<", ">", "<=", ">=", ":<>:", ":=:"}
            if op in rhs_ops and i + 1 < len(t):
                right, j = self.parse_primary(t, i + 1)
                # ISO 10303-11 12.3: comparison with UNKNOWN/unset yields
                # UNKNOWN — indeterminate, never False
                if _is_unknown(left) or _is_unknown(right):
                    raise _Uneval(f"unset operand: {left!r} {op} {right!r}")
                if op in (":<>:", "<>", "!=", ):  # instance/value inequality
                    return (self._ne_comparable(left, right)), j
                if op == ":=:":
                    return (left is right or left == right), j
                if op == "=":
                    return self._eq_comparable(left, right), j
                if op in ("<", ">", "<=", ">="):
                    try:
                        return (compare_num(left, right, op)), j
                    except (TypeError, ValueError):
                        raise _Uneval(f"ordering on non-numeric: {left!r} {op} {right!r}")
        return left, i

    @staticmethod
    def _eq_comparable(left, right) -> bool:
        """Value equality tolerant of instance-vs-primitive mismatches:
        two entity instances compare by identity; mixed kinds are unequal
        (not a failure)."""
        if isinstance(left, (ComplexEntity, SimpleEntity)) or \
                isinstance(right, (ComplexEntity, SimpleEntity)):
            return left is right if type(left) is type(right) else False
        return left == right

    @staticmethod
    def _ne_comparable(left, right) -> bool:
        return not _Eval._eq_comparable(left, right)

    @staticmethod
    def _in_test(item, collection) -> bool:
        """item IN collection — collection: a string (TYPEOF form:
        'SCHEMA.ENTITY' substring test per ISO 10303-11: a string is
        treated as the type-name collection), a list/bag, or an entity
        instance (its type closure)."""
        if isinstance(collection, str):
            # TYPEOF form: collection is one qualified type string —
            # item (also a string) must match; both sides plain-compared
            return item == collection or (isinstance(item, str)
                                          and _type_name_of(item) == _type_name_of(collection))
        if isinstance(collection, (list, tuple, set)):
            return any(_type_name_of(item) == _type_name_of(x) or item == x
                       for x in collection)
        if isinstance(collection, (ComplexEntity, SimpleEntity)):
            types = (_type_names_of_instance(collection))
            return _type_name_of(item) in types
        return False

    def parse_primary(self, t, i):
        if i >= len(t):
            raise _Uneval("unexpected end")
        kind, text = t[i]

        if text == "{":
            # interval expression: {low <= attr <= high} (ISO 10303-11 §12.7)
            vals, j = self._parse_interval(t, i + 1)
            return vals, j

        if text == "[":
            # aggregate literal: ['a', 'b', ...] (type-name lists and more)
            items, j = self._parse_aggregate_lit(t, i + 1)
            return items, j

        if text == "(":
            # TYPEOF argument form? TYPEOF(v) handled below; a bare paren
            # group with a SINGLE value inside (e.g. ('#1')) is a 1-bag
            val, j = self.parse_or(t, i + 1)
            if j < len(t) and t[j][1] == ")":
                return val, j + 1
            raise _Uneval("unclosed paren")

        if text.upper() == "QUERY":
            if i + 1 < len(t) and t[i + 1][1] == "(":
                kept, j = self._eval_query(t, i + 2)
                return kept, j      # a bag; SIZEOF/compare consumes it
            raise _Uneval("QUERY without '('")

        if text.upper() == "TYPEOF":
            if i + 1 < len(t) and t[i + 1][1] == "(":
                operand, j = self.parse_primary(t, i + 2)
                if j < len(t) and t[j][1] == ")":
                    j += 1
                    return _typeof_strings(operand, self), j
            raise _Uneval("TYPEOF without '('")

        if kind == "kw" and text[0].islower() and i + 1 < len(t) and \
                t[i + 1][1] == "(" and text.upper() not in ():
            # schema-local function call — OUT of the evaluable subset
            # (e.g. acyclic_mapped_representation(SELF)); classification,
            # not failure
            raise _Uneval(f"schema-function-call: {text}")

        if text.upper() == "EXISTS":
            if i + 1 < len(t) and t[i + 1][1] == "(":
                chain, j = self.parse_chain(t, i + 2)
                vals = self.value_of_chain(chain)
                exists = bool(vals) and any(x is not None and x != "$" for x in vals)
                # skip closing paren
                if j < len(t) and t[j][1] == ")":
                    j += 1
                return exists, j
            raise _Uneval("EXISTS without '('")

        if text.upper() == "SIZEOF":
            if i + 1 < len(t) and t[i + 1][1] == "(":
                inner, j = self.parse_sizeof_arg(t, i + 2)
                if j < len(t) and t[j][1] == ")":
                    j += 1
                # possible relational suffix handled by parse_comparison
                return len(inner), j
            raise _Uneval("SIZEOF without '('")

        if kind == "number":
            return (_int_or_float(text)), i + 1
        if kind == "string":
            return text[1:-1].replace("''", "'"), i + 1
        if text.upper() in ("TRUE", "FALSE"):
            return (text.upper() == "TRUE"), i + 1

        # attribute chain (may start SELF)
        chain, j = self.parse_chain(t, i)
        vals = self.value_of_chain(chain)
        if len(vals) == 1:
            return vals[0], j
        if not vals:
            return None, j
        return vals, j

    def parse_sizeof_arg(self, t, i):
        """SIZEOF(QUERY(var <* chain | expr>)) → evaluate the query and
        return the surviving members (bag); SIZEOF(chain) → the bag."""
        if i < len(t) and t[i][1].upper() == "QUERY":
            return self._eval_query(t, i + 1)
        chain, j = self.parse_chain(t, i)
        return self.value_of_chain(chain), j

    def _eval_query(self, t, i):
        """QUERY(var <* source | body> or QUERY(var <* source | body))

        Evaluates the query: resolves the source bag (a chain or a nested
        QUERY), binds var per member, keeps members whose body is TRUE.
        Delimiter: '>' (BNF form) or the query's own ')' (real-world
        writer form — most of the corpus and several toolchains omit the
        '>'; both accepted, whichever comes first at depth 0).
        """
        # tolerate being called AT the QUERY token or AFTER it
        if i < len(t) and t[i][1].upper() == "QUERY":
            i += 1
        if i < len(t) and t[i][1] == "(":
            i += 1
        if i >= len(t) or t[i][0] != "kw":
            raise _Uneval("QUERY: expected variable")
        var_name = t[i][1].lower()
        j = i + 1
        if not (j < len(t) and t[j][1] == "<" and j + 1 < len(t) and
                t[j + 1][1] == "*"):
            raise _Uneval("QUERY: expected <*")
        j += 2
        # -- source: a chain OR a nested QUERY whose bag feeds this one
        if j < len(t) and t[j][0] == "kw" and t[j][1].upper() == "QUERY":
            members, j = self._eval_query(t, j)
        else:
            chain, j = self.parse_chain(t, j)
            members = self.value_of_chain(chain)
        if not (j < len(t) and t[j][1] == "|"):
            raise _Uneval("QUERY: expected |")
        # -- body: up to '>' (BNF) or our ')' (world form)
        depth = 0
        k = j + 1
        closed_at = None
        while k < len(t):
            tx = t[k][1]
            if tx == "(":
                depth += 1
            elif tx == ")":
                if depth == 0:
                    closed_at = k
                    break
                depth -= 1
            elif tx == ">" and depth == 0:
                closed_at = k
                break
            k += 1
        if closed_at is None:
            raise _Uneval("QUERY: missing > or ')'")
        body = t[j + 1:closed_at]
        kept = []
        for member in members:
            sub = self._bind_member(member)
            try:
                if sub.parse_or(list(body), 0)[0] is True:
                    kept.append(member)
            except _Uneval:
                raise      # member bodies must stay in the subset
        return kept, closed_at + 1

    def _bind_member(self, member):
        """Scoped _Eval whose SELF is the member (query bodies address the
        member with bare attribute chains)."""
        member_id = str(int(member)) if isinstance(member, int) else \
            getattr(member, "instance_id", None)
        if member_id is None:
            for e_id, inst in self.p21.instances.items():
                if inst is member:
                    member_id = e_id
                    break
        ent_name = self.entity_name
        if isinstance(member, SimpleEntity):
            ent_name = member.name.lower()
        elif isinstance(member, ComplexEntity) and member.types():
            ent_name = member.types()[0].lower()
        return _Eval(self.p21, self.schema, member_id, ent_name)

    def _parse_aggregate_lit(self, t, i):
        """[ item, item, ... ] → list of values (strings, numbers)."""
        items = []
        while i < len(t):
            if t[i][1] == "]":
                return items, i + 1
            if t[i][1] == ",":
                i += 1
                continue
            kind, text = t[i]
            if kind == "string":
                items.append(text[1:-1].replace("''", "'"))
                i += 1
            elif kind == "number":
                items.append(_int_or_float(text))
                i += 1
            elif kind == "kw":
                items.append(text)
                i += 1
            else:
                raise _Uneval(f"unsupported aggregate item {t[i]}")
        raise _Uneval("unclosed aggregate literal")

    def _parse_interval(self, t, i):
        """{low op1 attr op2 high} → bool (ISO §12.7)."""
        low, i = self.parse_primary(t, i)
        op1 = t[i][1]
        if op1 not in ("<", "<=", ">", ">="):
            raise _Uneval("interval not of form {low op mid op high}")
        if op1 in ("<", "<="):
            mid, i = self.parse_primary(t, i + 1)
            op2 = t[i][1]
            if op2 not in ("<", "<=", ">", ">=") or i + 1 >= len(t) or \
                    t[i + 1][1] != "}":
                raise _Uneval("interval missing '}'")
            if _is_unknown(mid):
                raise _Uneval("interval over unset value")
            high = self._interval_bound(t, i + 2)
            a = float(low) <= float(mid) if op1 == "<=" else float(low) < float(mid)
            b = (float(mid) <= float(high)) if op2 == "<=" else (float(mid) < float(high))
            return (a and b), i + 3
        raise _Uneval("interval high-first form unsupported (use low <= mid)")

    def _interval_bound(self, t, i):
        if i >= len(t):
            raise _Uneval("interval missing bound")
        kind, text = t[i]
        if kind == "number":
            return _int_or_float(text)
        vals = self.value_of_chain(self.parse_chain(t, i)[0])
        return vals[0] if len(vals) == 1 else None

    def parse_chain(self, t, i) -> Tuple[List[str], int]:
        """chain := SELF backslash-entity name (. name)*  — returns names."""
        names = []
        if i < len(t) and t[i][1].upper() == "SELF":
            names.append("SELF")
            i += 1
            if i < len(t) and t[i][1] == "\\":
                i += 1
                if i < len(t) and t[i][0] == "kw":
                    names.append(t[i][1])       # the redeclared entity name
                    i += 1
        while i < len(t) and t[i][0] == "kw":
            names.append(t[i][1])
            i += 1
            if i < len(t) and t[i][1] == ".":
                i += 1
                continue
            break
        if not names:
            raise _Uneval(f"expected a chain at {t[i:i + 2]}")
        return names, i


class _Uneval(Exception):
    """Raised when an expression leaves the evaluable subset."""


def _int_or_float(text: str):
    f = float(text)
    return int(f) if f.is_integer() and "." not in text and "e" not in text.lower() else f


def _is_unknown(v) -> bool:
    """ISO 10303-11 UNKNOWN: unset (?) values and the UNKNOWN logical —
    plus UNSET/DERIVED sentinels from the P21 reader."""
    from .p21 import UNSET, DERIVED
    return v is None or v is UNSET or v is DERIVED or (
        isinstance(v, str) and v == "UNKNOWN")


def _type_name_of(x) -> str:
    """Normalize a type name to its bare entity part (qualified 'S.E' → 'e'),
    case-folded."""

    def fold(name: str) -> str:
        return name.split(".")[-1].strip().lower()
    if isinstance(x, str):
        return fold(x.strip("'").strip('"'))
    if isinstance(x, (ComplexEntity, SimpleEntity)):
        return _type_name_of(_type_names_of_instance(x)[0]) if \
            _type_names_of_instance(x) else ""
    return fold(str(x))


def _type_names_of_instance(inst) -> List[str]:
    """All type names of a P21 instance, casefolded (complex: every part)."""
    if isinstance(inst, ComplexEntity):
        return [t.lower() for t in inst.types()]
    if isinstance(inst, SimpleEntity):
        return [inst.name.lower()]
    return []


def _typeof_strings(operand, ev: "_Eval") -> List[str]:
    """ISO 10303-11 TYPEOF(v) — the SUPERTYPE-CLOSED set of the operand's
    type names as 'SCHEMA.ENTITY' strings (the corpus' rule texts test
    e.g. 'SCHEMA.ENTITY' IN TYPEOF(x)).  Casefolded + bare-name + Upper
    aliases, so rules written either way match. The closure walks the
    schema's supertype graph (composite_curve_segment's parent_curve
    instance TRIMMED_CURVE → + curve + geometric_representation_item…)."""
    names: List[str] = []
    if isinstance(operand, (ComplexEntity, SimpleEntity)):
        types = ([operand.name] if isinstance(operand, SimpleEntity)
                 else operand.types())
        ents = ev.schema.entities

        def closure(name: str, seen: set) -> None:
            key = name.lower()
            if key in seen:
                return
            seen.add(key)
            names.append(key)
            names.append(name.upper())
            qualified = f"{_schema_prefix(ev)}.{name}".lower()
            names.append(qualified)
            ent = ents.get(name) or ev._casefold_entity(name)
            if ent is not None:
                for sup in ent.supertypes:
                    closure(sup, seen)

        for t in types:
            closure(t, set())
    elif isinstance(operand, str):
        names.append(operand.lower())
    elif operand is None:
        pass
    else:
        names.append(str(operand).lower())
    return names


def _schema_prefix(ev: "_Eval") -> str:
    """File's schema name, camel-stripped for the qualified form."""
    s = getattr(ev.p21, "schema_names", []) or []
    if s:
        return str(s[0]).split("(")[0].strip("('\" ")
    return getattr(ev.schema, "name", "").split("(")[0]


def compare_num(left, right, op) -> bool:
    lf, rf = float(left), float(right)
    if op == "<":
        return lf < rf
    if op == ">":
        return lf > rf
    if op == "<=":
        return lf <= rf
    return lf >= rf


# -- the per-entity driver ------------------------------------------------------


def evaluate_entity(p21: P21File, schema: ExpressSchema, entity_name: str,
                    instance_id: str) -> Tuple[int, int, List[WhereFinding]]:
    """Evaluate one instance's WHERE rules → (rules_seen, evaluated, findings)."""
    ent = schema.entities.get(entity_name)
    if ent is None:
        return 0, 0, []
    findings: List[WhereFinding] = []
    seen = 0
    evaluated = 0
    if not ent.where_rules and not getattr(ent, "_unique_keys", None):
        return 0, 0, findings
    ev = _Eval(p21, schema, instance_id, entity_name)
    for rule_name in ent.where_rules:
        seen += 1
        expr = (ent.where_rules.get(rule_name) or "").strip()
        if not expr:
            # rule body text not retained in the subset reader — classify only
            continue
        fam = rule_family(expr)
        if fam != "evaluable":
            findings.append(WhereFinding(
                f"#{instance_id}", entity_name, rule_name,
                "unevaluated", fam, expr[:120]))
            continue
        try:
            tokens = _tokenize(expr)
            # anchor-name sanity: an anchor attribute unknown to every declared
            # type (or a DERIVED one) leaves the evaluable subset — never fail
            # -- A-stratum anchor analysis: EVERY attribute chain in the rule
            # must resolve to an EXPLICIT attribute; derived (computed) or
            # unknown anchors leave the subset → indeterminate, never a false
            # failure. Chains whose head is a bound QUERY variable are
            # exempt (they resolve per-member at evaluation).
            bound_vars = _query_vars(expr)
            chains = [(name, path) for name, path in _chain_anchors(tokens)
                      if name.lower() not in bound_vars]
            verdict = None       # None=indeterminate | True=ok
            if not chains:
                verdict = True   # constant-only/QUERY-only rule
            else:
                verdict = True
                for anchor in chains:
                    anchor_name, path = anchor
                    resolved = None          # None unknown | True derived | False explicit
                    for known_type in ev.instance_types():
                        ent_def = ev._casefold_entity(known_type)
                        if ent_def is None:
                            continue
                        if any(a[0].lower() == anchor_name.lower()
                               for a in ent_def.derived_attrs):
                            resolved = True
                            break
                        if any(a[0].lower() == anchor_name.lower()
                               for a in ent_def.attributes):
                            resolved = False
                            break
                    if resolved is not False:
                        verdict = None
                        break
            if not verdict:
                findings.append(WhereFinding(
                    f"#{instance_id}", entity_name, rule_name,
                    "indeterminate", "derived-or-unknown-anchor", expr[:120]))
                continue
            ok = ev.eval_expr(tokens)
            evaluated += 1
            if not ok:
                findings.append(WhereFinding(
                    f"#{instance_id}", entity_name, rule_name,
                    "fail", "evaluable", expr[:120]))
        except _Uneval as ue:
            findings.append(WhereFinding(
                f"#{instance_id}", entity_name, rule_name,
                "indeterminate", "evaluable-unfinished", str(ue)))
        except Exception as exc:       # never explode the check on one rule
            findings.append(WhereFinding(
                f"#{instance_id}", entity_name, rule_name,
                "indeterminate", "evaluator-error", str(exc)[:120]))
    return seen, evaluated, findings


def evaluate_where_rules(p21: P21File, schema: ExpressSchema,
                         max_instances: int = 0) -> WhereResult:
    """Evaluate every instance's WHERE rules against the schema."""
    result = WhereResult()
    known = {n.upper(): n for n in schema.entities}
    for eid, inst in p21.instances.items():
        types = ([inst.name] if isinstance(inst, SimpleEntity)
                 else (inst.types() if isinstance(inst, ComplexEntity) else []))
        for t in types:
            canonical = known.get(t.upper())
            if canonical is None:
                continue
            seen, evaluated, findings = evaluate_entity(
                p21, schema, canonical, eid)
            result.rules_seen += seen
            result.rules_evaluated += evaluated
            for f in findings:
                result.families[f.family] = result.families.get(f.family, 0) + 1
                if f.outcome == "fail":
                    result.failures.append(f)
                elif f.outcome in ("indeterminate", "unevaluated"):
                    result.rules_unevaluated += 1
                    result.indeterminate.append(f)
            if evaluated and result.families.get("evaluable"):
                pass
    return result