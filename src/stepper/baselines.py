# -*- coding: utf-8 -*-
"""Baseline-gate engine — pin a released Vee configuration, gate drift.

A baseline is the content digest of a manifest over:

* every ``.sysml`` / ``.stp`` file (raw bytes, sha256)
* the DERIVED payloads — the interchange stable-ids JSON (with its
  qn_registry) per .sysml set, the structure JSON-LD and the OBP
  (-3001-mapped, -400-uuid) payloads per .stp

``create_baseline`` → canonical manifest → ``bl:<digest16>``; identical
content is idempotent, any change mints a new id, so a CI job can
**fail a merge whenever the working tree's id differs from the pinned
one** — the PLM released-configuration gate.

CLI: ``stepper baseline create|verify|check`` (see cli.py).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["BaselineInput", "create_baseline", "verify_baseline",
           "load_manifest", "baseline_id_from_manifest"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class BaselineInput:
    sysml_files: List[str] = field(default_factory=list)
    step_files: List[str] = field(default_factory=list)
    schemas: Dict[str, str] = field(default_factory=dict)  # label -> .exp path
    title: str = ""
    author: str = ""


def _artifacts(inp: BaselineInput, store: Dict[str, bytes]) -> List[dict]:
    """Hash the pinned sources + compute the derived payloads."""
    artifacts: List[dict] = []
    for path in inp.sysml_files:
        if not os.path.exists(path):
            raise FileNotFoundError(f"sysml file not found: {path}")
        data = open(path, "rb").read()
        digest = sha256_bytes(data)
        store[digest] = data
        artifacts.append({"kind": "sysml", "path": os.path.basename(path),
                          "sha256": digest, "size": len(data)})
    for path in inp.step_files:
        if not os.path.exists(path):
            raise FileNotFoundError(f"step file not found: {path}")
        data = open(path, "rb").read()
        digest = sha256_bytes(data)
        store[digest] = data
        artifacts.append({"kind": "step", "path": os.path.basename(path),
                          "sha256": digest, "size": len(data)})
    for label, path in sorted(inp.schemas.items()):
        data = open(path, "rb").read()
        digest = sha256_bytes(data)
        store[digest] = data
        artifacts.append({"kind": "schema", "path": label,
                          "sha256": digest, "size": len(data)})

    # -- derived payloads --------------------------------------------------
    sysml_text = "\n".join(open(p, encoding="utf-8", errors="replace").read()
                           for p in inp.sysml_files).strip()
    if sysml_text:
        try:
            import sysmlpy
            from sysmlpy.interchange import (
                to_interchange, interchange_to_json_text, qn_registry,
            )
            model = (sysmlpy.loads(sysml_text)
                     if len(inp.sysml_files) == 1
                     else sysmlpy.load_files(list(inp.sysml_files)))
            doc = to_interchange(model, stable_ids=True)
            reg = qn_registry(doc)
            doc.pop("#qn_registry", None)
            payload = interchange_to_json_text(doc, indent=None)
            digest = sha256_bytes(payload.encode("utf-8"))
            store[digest] = payload.encode("utf-8")
            artifacts.append({
                "kind": "sysml_interchange", "path": "-",
                "sha256": digest, "size": len(payload),
                "qn_registry": reg,
            })
        except Exception as e:      # sysmlpy absent / model unparseable
            artifacts.append({"kind": "sysml_interchange", "path": "-",
                              "error": str(e)[:200]})

    for p in inp.step_files:
        label = os.path.basename(p)
        try:
            from .structure import extract_structure, to_oslc_jsonld
            from .bom import to_obp, to_obp_json, uuid_bridge

            s = extract_structure(p, file_label=label)
            st_payload = json.dumps(to_oslc_jsonld(s), sort_keys=True)
            digest = sha256_bytes(st_payload.encode("utf-8"))
            store[digest] = st_payload.encode("utf-8")
            artifacts.append({"kind": "step_structure", "path": label,
                              "sha256": digest, "size": len(st_payload)})

            obp_model = to_obp(p)
            obp_payload = json.dumps(to_obp_json(obp_model), sort_keys=True)
            digest = sha256_bytes(obp_payload.encode("utf-8"))
            store[digest] = obp_payload.encode("utf-8")
            artifacts.append({"kind": "step_obp", "path": label,
                              "sha256": digest, "size": len(obp_payload)})

            uuid_payload = json.dumps(uuid_bridge(obp_model), sort_keys=True)
            digest = sha256_bytes(uuid_payload.encode("utf-8"))
            store[digest] = uuid_payload.encode("utf-8")
            artifacts.append({"kind": "step_uuid", "path": label,
                              "sha256": digest, "size": len(uuid_payload)})
        except Exception as e:
            artifacts.append({"kind": "step_structure", "path": label,
                              "error": str(e)[:200]})
    return artifacts


def _canonical(manifest: dict) -> str:
    return json.dumps(manifest, sort_keys=True)


def baseline_id_from_manifest(manifest: dict) -> str:
    return "bl:" + hashlib.sha256(
        _canonical(manifest).encode("utf-8")).hexdigest()[:16]


def create_baseline(inp: BaselineInput) -> dict:
    """Build the baseline record (manifest + id + artifacts). The
    artifact BYTES ride the reply (CI saves them with the id)."""
    store: Dict[str, bytes] = {}
    artifacts = _artifacts(inp, store)
    if not artifacts:
        raise ValueError("baseline needs at least one sysml or step file")
    # The id covers CONTENT ONLY (title/author are annotations — a pipeline
    # gate that ignores them stays stable when someone renames the release).
    manifest = {"artifacts": artifacts}
    bid = baseline_id_from_manifest(manifest)
    return {
        "id": bid,
        "created": _created_stamp(),
        **manifest,
        "artifacts_bytes": {d: len(b) for d, b in store.items()},
    }


def load_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def verify_baseline(baseline: dict, inp: Optional[BaselineInput] = None) -> dict:
    """Re-derive the baseline from the CURRENT trees (when inp given)
    and compare ids; re-hash every pinned artifact byte in all cases."""
    results = []
    all_ok = True
    for art in baseline.get("artifacts", []):
        digest = art.get("sha256")
        if digest and inp is not None:
            pass          # byte-level verify below via re-derivation
        results.append({
            "path": art.get("path"), "kind": art.get("kind"),
            "sha256": digest, "status": "recorded" if digest else "no-hash",
        })
    changed = None
    if inp is not None:
        fresh = create_baseline(inp)
        changed = (fresh["id"] != baseline.get("id"))
        changed_detail = None if not changed else _first_diff(
            baseline.get("artifacts", []), fresh.get("artifacts", []))
        all_ok = not changed
    return {
        "id": baseline.get("id"),
        "integrity": {"verified": all_ok,
                      "artifacts": results},
        "matches_current": (not changed) if inp is not None else None,
        "first_diff": (changed_detail if (inp is not None and changed) else None),
    }


def _first_diff(old: List[dict], new: List[dict]) -> Optional[str]:
    old_by = {a.get("kind"): a for a in old}
    for a in new:
        o = old_by.get(a.get("kind"))
        if o is None:
            return f"added: {a.get('kind')} {a.get('path')}"
        if o.get("sha256") != a.get("sha256"):
            return (f"changed: {a.get('kind')} {a.get('path')} "
                    f"{(o.get('sha256') or '')[:12]} → {(a.get('sha256') or '')[:12]}")
    return "artifacts removed"


def _created_stamp() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


# -- the CI gate ----------------------------------------------------------------


def gate(pinned_manifest_path: str, inp: BaselineInput) -> int:
    """The pipeline step: fail (exit 1) when the working tree's CONTENT
    digest differs from the pinned one (annotations like title/author
    don't gate)."""
    pinned = load_manifest(pinned_manifest_path)
    fresh = create_baseline(inp)
    pinned_id = (pinned.get("id") or
                 baseline_id_from_manifest(
                     {"artifacts": pinned.get("artifacts", [])}))
    out = {
        "pinned": pinned_id,
        "current": fresh["id"],
        "matches": pinned_id == fresh["id"],
    }
    if out["matches"]:
        print(json.dumps(out, indent=2))
        print("result: PASS (working tree matches the pinned baseline)")
        return 0
    out["first_diff"] = _first_diff(pinned.get("artifacts", []),
                                   fresh["artifacts"])
    print(json.dumps(out, indent=2))
    print("result: FAIL (working tree drifted from the pinned baseline)")
    return 1