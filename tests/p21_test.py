# -*- coding: utf-8 -*-
"""P21 parser tests: synthetic edge cases + real NIST fixtures."""
import json
import os

import pytest

from stepper.p21 import (
    Binary, ComplexEntity, Enum, P21File, Ref, SimpleEntity, Typed,
    UNSET, DERIVED, parse_p21, load_p21,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "nist")

DEMO = r"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('demo','second line'),'2;1');
FILE_NAME('demo.step','2026-10-05T00:00:00',('Jon'),('NIST'),
  'spike','stepper','');
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF { 1 0 10303 442 7 1 4 }'));
ENDSEC;
ANCHOR;
<6db46031-4fab-4838-824b-91cea43922e4>=#10;
<3c9773de-5015-4c05-86b4-0e35a5bfd96f>=#7934;
ENDSEC;
DATA;
#10=PRODUCT_DEFINITION('',' ',#12,#28);
#11=PRODUCT_DEFINITION_SHAPE(' ',' ',#10);
#12=PRODUCT_DEFINITION_FORMATION('',' ',#13);
#13=PRODUCT('','manifold',#15,$,$);
#15=PRODUCT_DEFINITION_CONTEXT('3d shape',#28,'design');
#28=APPLICATION_CONTEXT('core data for automotive mechanical design processes');
#100=(NPLUS_INTEGER_VECTOR() BINUNIT() DIMENSIONAL_EXPONENTS() NAMED_UNIT($,$) SI_UNIT(.MILLI.,.METRE.));
#101=CYLINDRICITY_TOLERANCE(0.05,#200);
#102=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));
#200=AXIS2_PLACEMENT_3D('',#201,#202,$);
#201=DIRECTION('',(0.,0.,1.));
#202=CARTESIAN_POINT('',(0.,0.,0.));
#203=DRAUGHTING_MODEL('it''s escaped');
ENDSEC;
END-ISO-10303-21;
"""


class TestTokens:
    def test_refs_and_enums(self):
        p = parse_p21(DEMO)
        assert p.instances["101"].args == [0.05, Ref(200)]
        assert p.instances["100"].parts[4].args == [Enum(".MILLI."), Enum(".METRE.")]

    def test_unset_derived(self):
        p = parse_p21(DEMO)
        assert p.instances["13"].args[3] is UNSET
        from stepper.p21 import DERIVED
        assert p.instances["102"].parts[1].args == [DERIVED]

    def test_string_escape(self):
        p = parse_p21(DEMO)
        assert p.instances["203"].args[0] == "it's escaped"

    def test_complex_entity_types(self):
        p = parse_p21(DEMO)
        c = p.instances["100"]
        assert isinstance(c, ComplexEntity)
        assert c.types() == ["NPLUS_INTEGER_VECTOR", "BINUNIT",
                             "DIMENSIONAL_EXPONENTS", "NAMED_UNIT", "SI_UNIT"]
        assert c.get("SI_UNIT").args == [".MILLI.", ".METRE."]

    def test_anchors(self):
        p = parse_p21(DEMO)
        assert p.anchors["6db46031-4fab-4838-824b-91cea43922e4"] == "#10"

    def test_file_schema(self):
        p = parse_p21(DEMO)
        assert "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF" in p.schema_names[0]

    def test_not_p21_raises(self):
        with pytest.raises(SyntaxError):
            parse_p21("let x = 1;")


class TestRealFiles:
    """Real CAD exports (NIST public test data, vendored)."""

    @pytest.mark.parametrize("fname", [
        "nist_ctc_01_asme1_ap242-e1.stp",
        "nist_ctc_03_asme1_ap242-e2.stp",
        "nist_ftc_11_asme1_ap242-e3.stp",
        "nist_stc_09_asme1_ap242-e4.stp",
        "nist_ctc_01_asme1_rd.stp",
    ])
    def test_nist_files_parse(self, fname):
        p = load_p21(os.path.join(FIXTURES, fname))
        assert len(p.instances) > 100
        schema = p.schema_names
        assert schema, "FILE_SCHEMA missing"
        if "ap242" in fname:
            assert "AP242" in schema[0]
        assert p.entity_types()  # histogram built

    def test_ctc01_ap242_counts(self):
        p = load_p21(os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        # From NIST's own file: 4297 simple + 53 complex (probed).
        assert len(p.instances) == 4297 + 53

    def test_histogram_counts_match(self):
        p = load_p21(os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        hist = p.entity_types()
        # complex entities contribute to each of their member types:
        # sum == simple_count + total_complex_member_count
        simple_n = len([i for i in p.instances.values()
                        if not isinstance(i, ComplexEntity)])
        complex_members = sum(len(i.types()) for i in p.instances.values()
                              if isinstance(i, ComplexEntity))
        assert sum(hist.values()) == simple_n + complex_members


class TestInstanceModel:
    def test_all_nist_refs_resolve(self):
        """Phase A gate: no dangling refs in any vendored NIST file."""
        for fname in sorted(os.listdir(FIXTURES)):
            if not fname.endswith(".stp"):
                continue
            p = load_p21(os.path.join(FIXTURES, fname))
            refs = set(p.instances.keys())
            for eid, inst in p.instances.items():
                members = []
                if isinstance(inst, ComplexEntity):
                    for part in inst.parts:
                        members.extend(part.args)
                else:
                    members.extend(inst.args)
                for a in members:
                    if isinstance(a, Ref):
                        assert str(int(a)) in refs, \
                            f"{fname}: #{eid} references missing #{int(a)}"