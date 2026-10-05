#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stepper CLI: `stepper check` (gate), `stepper inspect` (stats)."""

import argparse
import json
import sys
from pathlib import Path

from .check import check_file
from .express import load_express
from .p21 import load_p21

SOURCE_EXTENSIONS = (".stp", ".step", ".p21", ".stpx")


def discover(paths, exclude=()):
    found, seen = [], set()
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            if p.suffix in SOURCE_EXTENSIONS and p not in seen:
                seen.add(p)
                found.append(p)
        elif p.is_dir():
            for ext in SOURCE_EXTENSIONS:
                for fp in sorted(p.rglob(f"*{ext}")):
                    if fp.is_file() and fp not in seen and not any(
                            x in fp.as_posix() for x in exclude):
                        seen.add(fp)
                        found.append(fp)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stepper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="parse gate + schema checks")
    p_check.add_argument("paths", nargs="+",
                         help=".stp/.step/.p21 files or directories")
    p_check.add_argument("-s", "--schema", help="EXPRESS schema (.exp)")
    p_check.add_argument("--semantic", choices=("off", "advisory", "strict"),
                         default="advisory")
    p_check.add_argument("--exclude", action="append", default=None)
    p_check.add_argument("--format", choices=("text", "json"), default="text")

    p_inspect = sub.add_parser("inspect", help="entity histogram")
    p_inspect.add_argument("file", help=".stp file")
    p_inspect.add_argument("--top", type=int, default=20)

    p_struct = sub.add_parser(
        "structure",
        help="extract product structure as OSLC JSON-LD / Turtle (P1)")
    p_struct.add_argument("file", help=".stp file")
    p_struct.add_argument("--base", default="https://example.org/stepper/",
                          help="base URL for emitted resources")
    p_struct.add_argument("--format", choices=("jsonld", "turtle"),
                          default="jsonld")

    args = ap.parse_args(argv)

    if args.cmd == "check":
        from stepper.check import CheckResult, Finding
        files = discover(args.paths, exclude=args.exclude or ())
        if not files:
            print("no .stp/.step/.p21 files found", file=sys.stderr)
            return 2
        schema = load_express(args.schema) if args.schema else None
        result = CheckResult(semantic_mode=args.semantic)
        for f in files:
            r = check_file(str(f), schema=schema, semantic=args.semantic)
            result.files_checked += 1
            result.instances_checked += r.instances_checked
            result.findings.extend(r.findings)
            if r.exit_code:
                for fl in r.parse_failures:
                    result.findings.append(fl)
        blocking = [x for x in result.findings
                    if x.level == "error"
                    and (x.stage in ("parse", "refs")
                         or args.semantic == "strict")]
        result.exit_code = 1 if blocking else 0
        import time
        result.duration_s = 0.0
        print(json.dumps(result.as_dict(), indent=2)
              if args.format == "json" else result.as_text())
        return result.exit_code

    if args.cmd == "inspect":
        p21 = load_p21(str(args.file))
        hist = p21.entity_types()
        print(f"{args.file}")
        print(f"  instances: {len(p21.instances)}")
        print(f"  schema: {', '.join(p21.schema_names) or '(none)'}")
        print(f"  anchors: {len(p21.anchors)}")
        print(f"  top entity types:")
        for name, n in sorted(hist.items(), key=lambda kv: -kv[1])[:args.top]:
            print(f"    {name:45s} {n}")
        return 0

    if args.cmd == "structure":
        from stepper.structure import structure_file
        _, jsonld, turtle = structure_file(str(args.file), base=args.base)
        if args.format == "turtle":
            print(turtle, end="")
        else:
            print(json.dumps(jsonld, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())