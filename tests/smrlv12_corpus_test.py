"""SMRL v12 corpus (official ISO zip) — delta suite on top of the v11 corpus.

Mirrors the official https://standards.iso.org/iso/10303/smrl/v12/
tech/smrlv12.zip (kept at ~/proj/third_party/smrlv12, git-inited).
Focus: the -400 SysML-mapping chain, whose v12 concatenated longform
adds the UUID identity family (Uuid_attribute / Uuid_context /
Uuid_relationship / Uuid_provenance) — the standards-track identity
carrier Phase C mappers onto sysmlpy's stable ids.
"""
import os
import re
import zipfile

import pytest

from stepper.express import load_express

V12_ZIP = "/tmp/smrlv12.zip"
V12_TREE = os.path.join(os.path.expanduser("~"), "proj", "third_party", "smrlv12",
                        "data", "modules")

S400 = os.path.join(V12_TREE, "reference_schema_for_sysml_mapping")


def _schema_entities(path):
    schema = load_express(path)
    ents = schema.entities
    return ents() if callable(ents) else ents


def test_v12_tree_present():
    assert os.path.isdir(V12_TREE), "smrlv12 missing at ~/proj/third_party (re-extract the official zip)"


def test_v400_arm_is_normative_edition():
    """N11378 (Supersedes N11008) — unchanged from v11."""
    t = open(os.path.join(S400, "arm.exp"), errors="replace").read()
    assert "N11378" in t
    assert "Supersedes ISO TC184/SC4/WG12 N11008" in t


def test_v400_concatenated_carries_uuid_identity_family():
    """The v12 additions the Vee join maps onto."""
    ents = _schema_entities(os.path.join(S400, "arm_concatenated.exp"))
    for name in ("Uuid_attribute", "V5_uuid_attribute", "Hash_based_v5_uuid_attribute",
                 "Uuid_attribute_with_approximate_location", "Uuid_context",
                 "Uuid_relationship", "Uuid_provenance"):
        assert name in ents, name


def test_uuid_attribute_shape():
    ents = _schema_entities(os.path.join(S400, "arm_concatenated.exp"))
    uuid_attr = ents["Uuid_attribute"]
    names = {a[0] for a in uuid_attr.explicit_attrs}
    assert {"identifier", "identified_item"} <= names


def test_uuid_relationship_shape():
    ents = _schema_entities(os.path.join(S400, "arm_concatenated.exp"))
    rel = ents["Uuid_relationship"]
    names = {a[0] for a in rel.explicit_attrs}
    assert {"identifier", "uuid_1", "uuid_2", "role"} <= names


def test_v12_module_delta_vs_v11():
    """v12 adds TS 10303-1028 universally_unique_identification_assignment (N11523)."""
    arm = os.path.join(V12_TREE, "universally_unique_identification_assignment", "arm.exp")
    t = open(arm, errors="replace").read()
    assert "N11523" in t
    assert "uuid" in t.lower()


UUID_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "express", "uuid")


def test_uuid_resource_schema_vendored():
    """The normative identity schema (ISO 10303-41 ed8 support resource, N11569)."""
    p = os.path.join(UUID_FIXTURES, "uuid_attribute_schema.exp")
    ents = _schema_entities(p)
    names = set(ents)
    for expect in ("uuid_attribute", "v5_uuid_attribute", "hash_based_v5_uuid_attribute",
                   "uuid_context", "uuid_provenance", "uuid_relationship"):
        assert expect in names, expect


def test_v12_concatenated_vendored_and_parses():
    p = os.path.join(UUID_FIXTURES,
                     "reference_schema_for_sysml_mapping_v12_concatenated.exp")
    ents = _schema_entities(p)
    assert len(ents) >= 2440, len(ents)
    assert "Hash_based_v5_uuid_attribute" in ents


def test_v12_v400_longform_newer_than_v11():
    v12 = _schema_entities(os.path.join(S400, "arm_lf.exp"))
    v11 = _schema_entities(os.path.join(
        os.path.dirname(__file__), "fixtures", "express", "smrlv11", "modules",
        "reference_schema_for_sysml_mapping", "arm_lf.exp"))
    assert len(v12) > len(v11)          # v11: 2431 → v12: 2446
    for grown in ("Uuid_attribute", "Uuid_context", "Uuid_provenance"):
        assert grown in v12 and grown not in v11


def test_v12_schemas_all_parse():
    """The whole v12 module tree parses through stepper's reader."""
    bad = []
    total = 0
    count = 0
    for root, dirs, files in os.walk(V12_TREE):
        for f in files:
            if f.endswith(".exp"):
                p = os.path.join(root, f)
                try:
                    ents = _schema_entities(p)
                    total += len(ents)
                    count += 1
                except Exception as exc:
                    bad.append((os.path.relpath(p, V12_TREE), str(exc)[:80]))
    assert count >= 1290, count
    assert not bad, bad[:6]
    assert total > 100000, total