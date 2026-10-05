# -*- coding: utf-8 -*-
"""ISO 10303-21 (STEP P21) exchange-structure parser.

Pure Python, no dependencies.  Parses the clear-text encoding of the
STEP exchange structure:

    ISO-10303-21;
    HEADER; FILE_DESCRIPTION(...); ... ENDSEC;
    ANCHOR; <uuid>=#10; ... ENDSEC;          (edition 3+)
    DATA; #10=ENTITY(...); #20=(A() B()); ... ENDSEC;
    END-ISO-10303-21;

Values are parsed to nested Python structures:

* ``#123``            -> :class:`Ref` (entity reference)
* ``'text'``          -> ``str``   (encoded ``''`` escape decoded)
* ``.ENUM.``          -> :class:`Enum`
* ``"0101"``          -> :class:`Binary`
* ``1.5`` / ``42``    -> ``float`` / ``int``
* ``$``               -> :class:`UNSET`
* ``*``               -> :class:`DERIVED`
* ``TYPE(...)``       -> :class:`Typed`  (nested typed value)
* ``(A(...) B(...))`` -> :class:`ComplexEntity` (multi-type record)

The parser is tolerant of the shapes seen in real CAD exports
(CRLF, embedded newlines in args, multi-line complex entities) and
strict where the standard requires it (section keywords, instance
grammar).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


class Unset:
    """The ``$`` unset-value of a P21 attribute (per ISO 10303-21)."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "$"


class Derived:
    """The ``*`` derived-value marker of a P21 attribute."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "*"


UNSET = Unset()
DERIVED = Derived()


class Ref(int):
    """``#123`` — a reference to entity instance 123."""
    def __repr__(self) -> str:
        return f"#{int(self)}"


class Enum(str):
    """``.TRUE.`` / ``.B_SPLINE.`` — an enumeration value (dots kept)."""
    def __repr__(self) -> str:
        return f".{str(self)[1:-1] if str(self).startswith('.') else self}."


class Binary(str):
    """``"0101"`` — a binary literal."""
    def __repr__(self) -> str:
        return f'"{self}"'


class Typed:
    """``TYPE(args...)`` — a nested typed value."""

    __slots__ = ("type", "args")

    def __init__(self, type: str, args: List[Any]):
        self.type = type
        self.args = args

    def __repr__(self):
        inner = ", ".join(repr(a) for a in self.args)
        return f"{self.type}({inner})"

    def __eq__(self, other):
        return (isinstance(other, Typed) and self.type == other.type
                and self.args == other.args)


class ComplexEntity:
    """``(#12=(A(...)B(...)))`` — a complex (multi-type) instance whose
    parts share one instance id."""

    __slots__ = ("parts",)

    def __init__(self, parts: List[Typed]):
        self.parts = parts

    def types(self) -> List[str]:
        return [p.type for p in self.parts]

    def get(self, type_name: str) -> Optional[Typed]:
        for p in self.parts:
            if p.type == type_name:
                return p
        return None

    def has_type(self, type_pattern: str) -> bool:
        return any(p.type == type_pattern for p in self.parts)

    def __repr__(self):
        return f"ComplexEntity({self.types()})"


class SimpleEntity:
    """``#12=NAME(arg...)`` — an ordinary instance."""

    __slots__ = ("name", "args")

    def __init__(self, name: str, args: List[Any]):
        self.name = name
        self.args = args

    def __repr__(self):
        return f"{self.name}({len(self.args)} args)"


# ---------------------------------------------------------------------------
# tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""(?P<ref>\#\d+)
      | (?P<anchor><[^>]*>)
      | (?P<enum>\.[A-Za-z0-9_]+\.)
      | (?P<str>'(?:[^']|'')*')
      | (?P<bin>"[01]*")
      | (?P<comment>/\*.*?\*/)
      | (?P<end>[Ee][Nn][Dd]-[Ii][Ss][Oo]-10303-21)
      | (?P<start>[Ii][Ss][Oo]-10303-21)
      | (?P<kw>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<num>[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][+-]?\d+)?)
      | (?P<punct>[(),;=$*])
      | (?P<ws>\s+)
    """,
    re.VERBOSE,
)


def tokenize(text: str):
    """Yield (kind, value, line) tokens. Raises SyntaxError on garbage.

    ``/* ... */`` comments (ISO 10303-21 edition 2 data-section comments)
    are skipped and never yield.
    """
    pos, line, n = 0, 1, len(text)
    while pos < n:
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise SyntaxError(
                f"line {line}: cannot tokenize P21 text at: "
                f"{text[pos:pos + 40]!r}")
        kind = m.lastgroup
        val = m.group()
        if kind not in ("ws", "comment"):
            yield (kind, val, line)
        line += val.count("\n")
        pos = m.end()


# ---------------------------------------------------------------------------
# decoder for literals
# ---------------------------------------------------------------------------

def _decode_string(val: str) -> str:
    """``'...''...'`` -> ``...''...`` (ISO 10303-21 doubled-quote escape)."""
    body = val[1:-1]
    return body.replace("''", "'")


def _decode_number(val: str):
    if "." in val or "e" in val.lower():
        return float(val)
    return int(val)


_NUM_ONLY_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][+-]?\d+)?$")


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

class P21File:
    """A parsed P21 exchange file."""

    def __init__(self):
        self.header: List[Tuple[str, List[Any]]] = []
        self.anchors: Dict[str, str] = {}
        self.data: Dict[str, Any] = {}   # str(int id) -> SimpleEntity | ComplexEntity
        self.schema_names: List[str] = []
        self.file_name: Optional[str] = None
        self.section_signatures: List[str] = []

    @property
    def instances(self) -> Dict[str, Any]:
        return self.data

    def entity_types(self) -> Dict[str, int]:
        """Histogram of entity type names.  A complex multi-type instance
        contributes once to EACH member type, so the sum can exceed the
        instance count (an instance may have several types)."""
        from collections import Counter
        c = Counter()
        for inst in self.data.values():
            if isinstance(inst, ComplexEntity):
                c.update(inst.types())
            else:
                c[inst.name] += 1
        return dict(c)

    def instance_type(self, ref) -> str:
        """Best-effort type label for an instance (last complex member wins)."""
        inst = self.data.get(str(int(ref)))
        if inst is None:
            return "?"
        if isinstance(inst, ComplexEntity):
            ts = inst.types()
            return ts[-1] if ts else "?"
        return inst.name


class P21Parser:
    def __init__(self, text: str):
        self.toks = list(tokenize(text))
        self.i = 0
        self.out = P21File()

    # -- token stream helpers -----------------------------------------
    def peek(self) -> Tuple[str, str, int]:
        return self.toks[self.i] if self.i < len(self.toks) else (None, None, -1)

    def next(self) -> Tuple[str, str, int]:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def peek_val(self):
        return self.peek()[1]

    def expect(self, val: str):
        kind, v, _ = self.next()
        if v != val:
            raise SyntaxError(
                f"expected {val!r} but got {v!r} (token {self.i}, "
                f"line {self.toks[self.i - 1][2] if self.i <= len(self.toks) else '?'})")

    # -- grammar -------------------------------------------------------
    def parse(self) -> P21File:
        kind, v, _ = self.peek()
        if v is None or v.lower() != "iso-10303-21":
            raise SyntaxError(
                f"not a P21 file: first token is {v!r} (expected "
                f"ISO-10303-21)")
        self.next()
        self.consume_semi()
        while True:
            kind, v, _ = self.peek()
            low = (v or "").lower()
            if v is None:
                raise SyntaxError("unexpected EOF (missing END-ISO-10303-21;)")
            if low == "header":
                self.next()
                self.consume_semi()
                self.parse_header()
            elif low == "anchor":
                self.next()
                self.consume_semi()
                self.parse_anchor()
            elif low == "data":
                self.next()
                self.parse_data()
            elif low == "endsec":
                self.next()
                self.consume_semi()
            elif low == "end-iso-10303-21":
                self.next()
                self.consume_semi()
                break
            else:
                raise SyntaxError(
                    f"unexpected top-level token {v!r} (line "
                    f"{self.peek()[2]})")
        if self.i < len(self.toks):
            raise SyntaxError(f"trailing tokens after END-ISO-10303-21; "
                              f"at line {self.peek()[2]}")
        self._extract_header_fields()
        return self.out

    def consume_semi(self):
        kind, v, _ = self.peek()
        while v == ";":
            self.next()
            kind, v, _ = self.peek()

    def parse_header(self):
        while True:
            kind, v, _ = self.peek()
            if v is None:
                raise SyntaxError("unexpected EOF in HEADER")
            if v.lower() == "endsec":
                self.next()
                self.consume_semi()
                return
            if kind != "kw":
                raise SyntaxError(
                    f"HEADER expects NAME(...); got kind={kind} {v!r} "
                    f"(line {self.peek()[2]})")
            name = self.next()[1]
            self.expect("(")
            # Header args: no entity refs inside; parse as values.
            args = self.parse_value_list(close=")")
            self.consume_semi()
            self.out.header.append((name, args))

    def parse_anchor(self):
        out_anchors = self.out.anchors
        while True:
            kind, v, _ = self.peek()
            if v is None:
                raise SyntaxError("unexpected EOF in ANCHOR")
            if v.lower() == "endsec":
                self.next()
                self.consume_semi()
                return
            if kind != "anchor":
                raise SyntaxError(
                    f"ANCHOR expects <key>=#ref; got {v!r} "
                    f"(line {self.peek()[2]})")
            key = self.next()[1][1:-1]
            self.expect("=")
            kind2, ref, _ = self.next()
            if kind2 != "ref":
                raise SyntaxError(
                    f"ANCHOR value must be #ref, got {ref!r}")
            out_anchors[key] = ref
            self.consume_semi()

    def parse_data(self):
        # optional ('SIG',(...)) signature params BEFORE the ';'
        kind, v, _ = self.peek()
        if v == "(":
            self.next()
            sig = self.parse_value_list(close=")")
            if sig:
                self.out.section_signatures.append(repr(sig))
        self.consume_semi()
        while True:
            kind, v, line = self.peek()
            if v is None:
                raise SyntaxError("unexpected EOF in DATA")
            if v.lower() == "endsec":
                self.next()
                self.consume_semi()
                return
            if kind != "ref":
                raise SyntaxError(
                    f"DATA expects #id=instance; got kind={kind} {v!r} "
                    f"(line {line})")
            ent_id = self.next()[1][1:]
            self.expect("=")
            self.out.data[ent_id] = self.parse_instance()
            self.consume_semi()

    def parse_instance(self):
        kind, v, _ = self.peek()
        if v == "(":
            self.next()
            parts = []
            while True:
                kind2, v2, _ = self.peek()
                if v2 is None:
                    raise SyntaxError("unexpected EOF in complex entity")
                if v2 == ")":
                    self.next()
                    break
                if kind2 != "kw":
                    raise SyntaxError(
                        f"complex entity expects NAME(...), got {v2!r}")
                name = self.next()[1]
                self.expect("(")
                args = self.parse_value_list(close=")")
                parts.append(Typed(name, args))
            return ComplexEntity(parts)
        if kind == "kw":
            name = self.next()[1]
            self.expect("(")
            args = self.parse_value_list(close=")")
            return SimpleEntity(name, args)
        raise SyntaxError(
            f"instance expects NAME( or (A()B()...), got {v!r}")

    def parse_value_list(self, close: str) -> List[Any]:
        """Parse a comma-separated value list UP TO (and consuming) the
        closing ``close`` paren.  The CALLER consumes the opening paren.
        Nested groups/lists/typed values are parsed recursively."""
        args: List[Any] = []
        while True:
            kind, v, _ = self.peek()
            if v is None:
                raise SyntaxError("unexpected EOF in value list")
            if v == close:
                self.next()
                return args
            if v == ";":
                self.next()
                return args
            if v == ",":
                self.next()
                continue
            args.append(self.parse_value())
        return args

    def parse_value(self):
        """Parse ONE value: literal / ref / enum / binary / typed /
        nested group."""
        kind, v, _ = self.next()
        if v in (None,):
            raise SyntaxError("unexpected EOF in value")
        if v == "(":
            # nested group: list or complex value — parse until ')'
            items = []
            while True:
                kind2, v2, _ = self.peek()
                if v2 is None:
                    raise SyntaxError("unexpected EOF in nested group")
                if v2 == ")":
                    self.next()
                    return items
                items.append(self.parse_value())
        if v == "$":
            return UNSET
        if v == "*":
            return DERIVED
        if kind == "ref":
            return Ref(int(v[1:]))
        if kind == "kw":
            # typed value: TYPE(...)  (commas inside must be skipped)
            self.expect("(")
            args = []
            while True:
                kind2, v2, _ = self.peek()
                if v2 is None:
                    raise SyntaxError("unexpected EOF in typed value")
                if v2 == ")":
                    self.next()
                    break
                if v2 == ",":
                    self.next()
                    continue
                args.append(self.parse_value())
            return Typed(v, args)
        if kind == "str":
            return v[1:-1].replace("''", "'")
        if kind == "enum":
            return Enum(v)
        if kind == "bin":
            return Binary(v[1:-1])
        if kind == "num" and _NUM_ONLY_RE.match(v):
            return _decode_number(v)
        # anything else (rare multi-token residue): keep raw text
        return v

    def _flush(self, args, cur, refs):
        raw = "".join(cur).strip()
        if not raw:
            return
        args.append(self._decode_token(raw))

    def _decode_token(self, raw: str):
        # ref-only case
        if raw.startswith("#") and raw[1:].isdigit():
            return Ref(int(raw[1:]))
        # single quoted string (possibly with doubled-quote escapes)
        if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1].replace("''", "'")
        # single enumeration
        if len(raw) >= 2 and raw.startswith(".") and raw.endswith("."):
            return Enum(raw)
        # single binary
        if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
            return Binary(raw[1:-1])
        # bare number
        if _NUM_ONLY_RE.match(raw):
            return _decode_number(raw)
        # unset / derived markers
        if raw == "$":
            return UNSET
        if raw == "*":
            return DERIVED
        # nested typed value that was not caught in parse_value_list's
        # fast path (e.g. inside parens) — keep raw for now (spike-grade,
        # typed args inside lists are rare in practice)
        return raw

    def _extract_header_fields(self):
        for name, args in self.out.header:
            if name == "FILE_SCHEMA":
                for a in (args or []):
                    if isinstance(a, list):
                        for item in a:
                            self.out.schema_names.append(str(item))
                    else:
                        self.out.schema_names.append(str(a))
            elif name == "FILE_NAME":
                if args and isinstance(args[0], str):
                    self.out.file_name = args[0]


def parse_p21(text: str) -> P21File:
    """Parse P21 text into a :class:`P21File`."""
    return P21Parser(text).parse()


def load_p21(path) -> P21File:
    """Load and parse a P21 file (encoding-tolerant)."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_p21(fh.read())