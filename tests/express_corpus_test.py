"""STEPmod EXPRESS corpus: every vendored schema must parse.

~317 .exp schemas from the SourceForge STEP Module Repository project
(SMRL module snapshots, 2004-2006 era: CC3D ed.2, PDM, AP203 E2 GDT,
TS parts 1050-1052/1130/1131 + the TS parts bundled in the CC3D zip)
plus the standalone resource schemas. All parse clean.

Provenance: tests/fixtures/express/stepmod/README.md.
"""
import glob
import os

import pytest

from stepper.express import load_express

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), "fixtures", "express", "stepmod")


def _all_schemas():
    return sorted(glob.glob(os.path.join(FIXTURE_ROOT, "**", "*.exp"), recursive=True))


ALL = _all_schemas()


def _entities(schema):
    ents = schema.entities
    return ents() if callable(ents) else ents


def test_corpus_present():
    assert len(ALL) >= 300, f"corpus missing: only {len(ALL)} schemas"


def test_corpus_subdirs_complete():
    counts = {
        sub: len(glob.glob(os.path.join(FIXTURE_ROOT, sub, "*.exp")))
        for sub in ("modules", "resources", "ts")
    }
    assert counts["modules"] == 129, counts
    assert counts["ts"] == 142, counts
    assert counts["resources"] >= 40, counts


@pytest.mark.parametrize("path", ALL)
def test_schema_parses(path):
    """No exception parsing; entity map is a dict (may be empty for
    USE-FROM-only modules like Document_management_arm)."""
    ents = _entities(load_express(path))
    assert isinstance(ents, dict)


def test_no_half_state_schemas():
    """Schemas that declare entities must yield well-formed named entries."""
    bad = []
    for path in ALL:
        ents = _entities(load_express(path))
        for name in ents:
            if not name:
                bad.append(path)
    assert not bad, bad


def test_total_entity_count():
    total = 0
    empty = 0
    for path in ALL:
        ents = _entities(load_express(path))
        total += len(ents)
        if not ents:
            empty += 1
    assert total >= 5528, f"entity total suspiciously low: {total}"
    assert empty <= len(ALL) // 3, f"too many empty schemas: {empty}/{len(ALL)}"