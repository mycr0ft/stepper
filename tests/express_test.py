# -*- coding: utf-8 -*-
"""EXPRESS reader tests: tiny synthetic + the real AP242 Ed.4 MIM longform
(downloaded to the CI cache / fetched on demand; skipped when absent)."""
import os

import pytest

from stepper.express import ExpressSchema, parse_express, load_express

SCHEMA_ENV = "STEPPER_AP242_EXP"
SCHEMA_PATH = os.environ.get(SCHEMA_ENV, "")

MINI = """
SCHEMA mini;
  TYPE plane_angle_measure = REAL; END_TYPE;
  ENTITY root;
  END_ENTITY;
  ENTITY cartesian_point
    SUBTYPE OF (point);
    coordinates : LIST[1:3] OF length_measure;
  END_ENTITY;
  ENTITY point;
  END_ENTITY;
  ENTITY advanced
    SUBTYPE OF (shape_representation, other_thing);
    SELF\\representation.items : SET [1:?] OF items_select;
  END_ENTITY;
  ENTITY shape_representation
    SUBTYPE OF (representation);
  END_ENTITY;
  ENTITY representation
    END_ENTITY;
  ENTITY other_thing;
  END_ENTITY;
END_SCHEMA;
"""


class TestMiniSchema:
    def test_counts(self):
        s = parse_express(MINI)
        assert len(s.entities) == 7

    def test_subtype_edges(self):
        s = parse_express(MINI)
        assert s.get("cartesian_point").supertypes == ["point"]
        assert s.get("advanced").supertypes == ["shape_representation", "other_thing"]
        assert s.get("shape_representation").supertypes == ["representation"]

    def test_chain_walk(self):
        s = parse_express(MINI)
        got = set(s.get("advanced").all_supertypes_graph(s))
        assert got == {"shape_representation", "other_thing", "representation"}

    def test_redeclarations(self):
        s = parse_express(MINI)
        assert s.get("advanced").redeclarations == ["representation.items"]

    def test_attributes(self):
        s = parse_express(MINI)
        assert s.get("cartesian_point").attributes[0][0] == "coordinates"

    def test_roots(self):
        s = parse_express(MINI)
        assert "root" in s.roots() and "point" in s.roots() \
            and "representation" in s.roots() and "other_thing" in s.roots()


@pytest.mark.skipif(not SCHEMA_PATH or not os.path.exists(SCHEMA_PATH),
                    reason=f"set {SCHEMA_ENV} to an ap242 mim_lf.exp to run")
class TestAp242Longform:
    """Full-scale schema test against the real AP242 Ed.4 MIM longform.

    Download:
    https://standards.iso.org/iso/ts/10303/-442/ed-7/tech/express/mim_lf.exp
    (2.5 MB, 54,756 lines; 2,407 entities).
    """

    @classmethod
    def setup_class(cls):
        cls.schema = load_express(SCHEMA_PATH)

    def test_entity_count(self):
        # exactly 2,407 in ed-7 (probed 2026-10-05)
        assert len(self.schema.entities) == 2407

    def test_supertype_edges(self):
        n, with_sup = self.schema.subtype_counts()
        assert n == 2407
        assert with_sup > 2000


class TestCheckEngine:
    def test_advisory_default_passes_unknown(self, tmp_path):
        from stepper.check import check_file
        from stepper.express import parse_express
        schema = parse_express(MINI)
        src = tmp_path / "m.stp"
        src.write_text("""ISO-10303-21;
HEADER;
FILE_NAME('m.stp','','','','','','');
FILE_SCHEMA(('MINI'));
ENDSEC;
DATA;
#1=AN_UNSCHEMAED_ENTITY('x');
ENDSEC;
END-ISO-10303-21;
""")
        r = check_file(str(src), schema=schema, semantic="advisory")
        assert r.exit_code == 0
        assert any(f.code == "UNKNOWN_ENTITY" for f in r.findings)

    def test_parse_failure_blocks(self, tmp_path):
        from stepper.check import check_file
        src = tmp_path / "bad.stp"
        src.write_text("not a p21 file\n")
        r = check_file(str(src), semantic="off")
        assert r.exit_code == 1
        assert r.parse_failures