"""SMRL v12 corpus (official ISO zip) — delta suite on top of the v11 corpus.

Two tiers:

1. **Vendored (runs everywhere, incl. CI)** — `tests/fixtures/express/uuid/`
   carries the v12 -400 chain + uuid identity schemas; the delta pins
   (normative edition, UUID family shapes, v11→v12 growth) run
   against those.

2. **Local mirror (env-gated)** — the full 1,297-module parse-all runs
   only when ~/proj/third_party/smrlv12 exists (kept out of the repo:
   70 MB, mirrors upstream). Locally it runs; in CI it self-skips.
"""
import os

import pytest

from stepper.express import load_express

V12_TREE = os.path.join(os.path.expanduser("~"), "proj", "third_party", "smrlv12",
                        "data", "modules")
UUID_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "express", "uuid")
V12_CONCAT = os.path.join(UUID_FIXTURES,
                          "reference_schema_for_sysml_mapping_v12_concatenated.exp")
V11_S400_LF = os.path.join(os.path.dirname(__file__), "fixtures", "express", "smrlv11",
                           "modules", "reference_schema_for_sysml_mapping", "arm_lf.exp")


def _schema_entities(path):
    schema = load_express(path)
    ents = schema.entities
    return ents() if callable(ents) else ents


def _uuid_fixture(name):
    return os.path.join(UUID_FIXTURES, name)


# -- tier 1: vendored fixtures (CI-safe) --------------------------------------


def test_uuid_fixtures_vendored():
    for name in ("uuid_attribute_schema.exp",
                 "universally_unique_identification_assignment_arm.exp",
                 "universally_unique_identification_assignment_mim.exp",
                 "reference_schema_for_sysml_mapping_v12_concatenated.exp"):
        assert os.path.exists(_uuid_fixture(name)), name


def test_v400_arm_is_normative_edition():
    """N11378 (Supersedes N11008) — unchanged from v11 (header quoted in the concat)."""
    t = open(V12_CONCAT, errors="replace").read()
    assert "N11378" in t
    assert "Supersedes ISO TC184/SC4/WG12 N11008" in t


def test_v400_concatenated_carries_uuid_identity_family():
    """The v12 additions the Vee join maps onto."""
    ents = _schema_entities(V12_CONCAT)
    for name in ("Uuid_attribute", "V5_uuid_attribute", "Hash_based_v5_uuid_attribute",
                 "Uuid_attribute_with_approximate_location", "Uuid_context",
                 "Uuid_relationship", "Uuid_provenance"):
        assert name in ents, name


def test_uuid_attribute_shape():
    ents = _schema_entities(V12_CONCAT)
    uuid_attr = ents["Uuid_attribute"]
    names = {a[0] for a in uuid_attr.explicit_attrs}
    assert {"identifier", "identified_item"} <= names


def test_uuid_relationship_shape():
    ents = _schema_entities(V12_CONCAT)
    rel = ents["Uuid_relationship"]
    names = {a[0] for a in rel.explicit_attrs}
    assert {"identifier", "uuid_1", "uuid_2", "role"} <= names


def test_uuid_resource_schema_vendored():
    """The normative identity schema (ISO 10303-41 ed8 support resource, N11569)."""
    ents = _schema_entities(_uuid_fixture("uuid_attribute_schema.exp"))
    names = set(ents)
    for expect in ("uuid_attribute", "v5_uuid_attribute", "hash_based_v5_uuid_attribute",
                   "uuid_context", "uuid_provenance", "uuid_relationship"):
        assert expect in names, expect


def test_v12_concatenated_vendored_and_parses():
    ents = _schema_entities(V12_CONCAT)
    assert len(ents) >= 2440, len(ents)
    assert "Hash_based_v5_uuid_attribute" in ents


def test_v12_v400_longform_newer_than_v11():
    v12 = _schema_entities(V12_CONCAT)
    v11 = _schema_entities(V11_S400_LF)
    assert len(v12) > len(v11)          # v11: 2431 → v12: 2446
    for grown in ("Uuid_attribute", "Uuid_context", "Uuid_provenance"):
        assert grown in v12 and grown not in v11


def test_ts1028_module_vendored():
    """v12's new TS 10303-1028 (N11523) — binds uuid items into the MIM."""
    t = open(_uuid_fixture("universally_unique_identification_assignment_arm.exp"),
             errors="replace").read()
    assert "N11523" in t
    assert "uuid" in t.lower()


# -- tier 2: local mirror (env-gated; self-skips in CI) ------------------------


@pytest.mark.skipif(not os.path.isdir(V12_TREE),
                    reason="smrlv12 local mirror absent (fixture-only run)")
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