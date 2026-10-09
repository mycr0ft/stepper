# -*- coding: utf-8 -*-
"""Semantic checks for STEP files: instance data against its schema.

`stepper check` engine — the sysmlpy-ci pattern for AP242/other-step
data. Exit codes: 0 clean, 1 findings at/above threshold, 2 errors.

Phase A checks (parse + schema inventory):
- every instance's declared name(s) exist in the loaded schema
- attribute-count agreement for SimpleEntity instances
- reference resolution: every #n points to a declared instance
Complex entities are checked for at least one recognized name.

Advisory-by-default semantics, strict opt-in — same rationale as
sysmlpy ci: the full EXPRESS-validated subset is still growing, so
findings are labeled and reported without blocking until Phase B.
"""

from __future__ import annotations

import os

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .express import ExpressSchema
from .p21 import (
    ComplexEntity, P21File, Ref, SimpleEntity,
)


@dataclass
class Finding:
    file: str
    level: str        # "error" | "warning"
    stage: str        # "parse" | "schema" | "refs"
    code: str
    message: str
    instance: Optional[str] = None

    def as_dict(self):
        d = {"file": self.file, "level": self.level, "stage": self.stage,
             "code": self.code, "message": self.message}
        if self.instance:
            d["instance"] = self.instance
        return d


@dataclass
class CheckResult:
    files_checked: int = 0
    instances_checked: int = 0
    findings: List[Finding] = field(default_factory=list)
    exit_code: int = 0
    semantic_mode: str = "advisory"

    @property
    def parse_failures(self):
        return [f for f in self.findings if f.stage == "parse" and f.level == "error"]

    def as_dict(self):
        return {
            "files_checked": self.files_checked,
            "instances_checked": self.instances_checked,
            "semantic_mode": self.semantic_mode,
            "exit_code": self.exit_code,
            "summary": {
                "parse_failures": len(self.parse_failures),
                "errors": sum(1 for f in self.findings if f.level == "error"),
                "warnings": sum(1 for f in self.findings if f.level == "warning"),
            },
            "findings": [f.as_dict() for f in self.findings[:200]],
        }

    def as_text(self):
        mode = self.semantic_mode
        out = [f"stepper check: {self.files_checked} file(s), "
               f"{self.instances_checked} instance(s), semantics {mode}"]
        for f in self.findings[:200]:
            inst = f" [{f.instance}]" if f.instance else ""
            out.append(f"{f.file}: {f.level}: {f.stage}: {f.code}: "
                       f"{f.message}{inst}")
        if len(self.findings) > 200:
            out.append(f"  ... {len(self.findings) - 200} more findings")
        n_err = sum(1 for f in self.findings if f.level == "error")
        n_warn = sum(1 for f in self.findings if f.level == "warning")
        out.append("")
        out.append(f"summary: {len(self.parse_failures)} parse failure(s), "
                   f"{n_err} error(s), {n_warn} warning(s)")
        out.append(f"result: {['PASS', 'FAIL', 'ERROR'][self.exit_code]}")
        return "\n".join(out)


def check_schema_instances(
    p21: P21File,
    schema: Optional[ExpressSchema],
    file: str = "-",
    max_findings: int = 10000,
) -> List[Finding]:
    """Phase-A schema validation findings for one loaded P21 file."""
    findings: List[Finding] = []
    if schema is None:
        return findings

    known = set(schema.entities)

    def add(f):
        if len(findings) < max_findings:
            findings.append(f)

    for eid, inst in p21.instances.items():
        if isinstance(inst, ComplexEntity):
            types = inst.types()
            unknown = [t for t in types if t.upper() not in
                       set(n.upper() for n in known)]
            if unknown and all(t not in known for t in types if t in known):
                # complex entities whose declared names are all unknown
                add(Finding(
                    file, "warning", "schema", "UNKNOWN_ENTITY",
                    f"complex entity types not in schema: {', '.join(unknown)}",
                    f"#{eid}"))
        else:
            if inst.name.upper() not in set(n.upper() for n in known):
                add(Finding(
                    file, "warning", "schema", "UNKNOWN_ENTITY",
                    f"entity type '{inst.name}' not in schema "
                    f"(schema: {schema.name})", f"#{eid}"))

        # attribute-count agreement (simple entities declared in schema)
        if isinstance(inst, SimpleEntity):
            se = schema.get(inst.name)
            if se is not None and len(inst.args) != len(se.attributes):
                add(Finding(
                    file, "warning", "schema", "ARG_COUNT_MISMATCH",
                    f"{inst.name}: file has {len(inst.args)} args, "
                    f"schema declares {len(se.attributes)} attrs "
                    f"(may reflect redeclaration/inherited gaps)",
                    f"#{eid}"))

    # reference resolution
    refs = set(p21.instances.keys())
    for eid, inst in p21.instances.items():
        members = []
        if isinstance(inst, ComplexEntity):
            for part in inst.parts:
                members.extend(part.args)
        else:
            members.extend(inst.args)
        for a in members:
            if isinstance(a, Ref):
                if str(int(a)) not in refs:
                    add(Finding(
                        file, "error", "refs", "DANGLING_REF",
                        f"reference #{int(a)} not in file", f"#{eid}"))
    return findings


def check_file(
    path: str,
    schema: Optional[ExpressSchema] = None,
    semantic: str = "advisory",
) -> CheckResult:
    from .p21 import load_p21

    result = CheckResult(semantic_mode=semantic)
    result.files_checked = 1
    try:
        p21 = load_p21(path)
    except SyntaxError as e:
        result.findings.append(Finding(path, "error", "parse", "PARSE", str(e)))
        result.exit_code = 1
        return result
    result.instances_checked = len(p21.instances)
    if semantic != "off" and schema is not None:
        f = check_schema_instances(p21, schema, file=path)
        result.findings.extend(f)
        # -- Phase C item 4: WHERE-rule evaluation
        where_enabled = os.environ.get("STEPPER_WHERE", "1") != "0"
        if where_enabled:
            from .where import evaluate_where_rules
            wr = evaluate_where_rules(p21, schema)
            for x in wr.failures:
                # a genuinely-failing decidable rule: blocks in strict mode;
                # advisory mode flags it as a warning (same contract as the
                # schema stage)
                result.findings.append(Finding(
                    path,
                    "error" if semantic == "strict" else "warning",
                    "where", "WHERE_FAIL",
                    f"{x.entity}.{x.rule}: {x.detail}",
                    x.instance))
            # (strict mode: the indeterminate rows are already visible as
            # warnings — they cannot block, by definition: undecided ≠ failed)
            for x in wr.indeterminate:
                result.findings.append(Finding(
                    path, "warning", "where",
                    "WHERE_INDETERMINATE" if x.outcome == "indeterminate"
                    else "WHERE_NOT_EVALUATED",
                    f"{x.entity}.{x.rule}: {x.family}"
                    + (f": {x.detail}" if x.detail else ""),
                    x.instance))
    blocking = [x for x in result.findings
                if x.level == "error"
                and (x.stage in ("parse", "refs", "where") or semantic == "strict")]
    result.exit_code = 1 if blocking else 0
    return result