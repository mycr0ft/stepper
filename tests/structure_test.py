# -*- coding: utf-8 -*-
"""Stepper structure (P1) tests: extraction + OSLC emission.

Pinned against real NIST AP242 files (probed 2026-10-05):
- CTC-01 (e1): 1 product, 1 PD, 1 SDR; shape rep counts present.
- STC-09 (e4): 2 products, PRODUCT_DEFINITION_FORMATION present.
- FTC-09 (e1, 4 products): 4 PDs + 4 shape reps of DIFFERENT kinds
  (SHAPE_REPRESENTATION / ADVANCED_BREP / MANIFOLD_SURFACE /
  GEOMETRICALLY_BOUNDED_WIREFRAME) — the multi-part case.
- Emitted Turtle parses with rdflib against pyoslc's OSLC_SYSML ns.
"""
import json
import os

import pytest
from stepper.p21 import load_p21
from stepper.structure import (
    OSLC_CORE, OSLC_SYSML, DCTERMS, ProductStructure,
    extract_structure, to_oslc_jsonld, to_oslc_turtle, structure_file,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "nist")

rdflib = pytest.importorskip("rdflib")


def _struct(fname):
    return extract_structure(os.path.join(FIXTURES, fname),
                             file_label=fname)


class TestExtraction:
    def test_ctc01_single_part(self):
        s = _struct("nist_ctc_01_asme1_ap242-e1.stp")
        assert len(s.of_kind("product")) == 1
        assert s.of_kind("product")[0].name == "NIST Test Case 1"
        pds = s.of_kind("product_definition")
        assert len(pds) >= 1
        # every PD resolves to the product
        prods = {p.ref for p in s.of_kind("product")}
        assert all(pd.product_ref in prods for pd in pds
                   if pd.product_ref)
        assert s.of_kind("shape_rep"), "SDR-linked shape reps expected"

    def test_stc09_formation_chain(self):
        s = _struct("nist_stc_09_asme1_ap242-e4.stp")
        assert len(s.of_kind("product")) == 2
        # PDs resolve formation -> product
        resolved = [pd for pd in s.of_kind("product_definition")
                    if pd.product_ref]
        assert resolved, "e4 file must resolve at least one PD->product"

    def test_ftc09_four_products(self):
        s = _struct("nist_ftc_09_asme1_ap242-e1.stp")
        assert len(s.of_kind("product")) == 4
        assert len(s.of_kind("product_definition")) >= 4
        reps = s.of_kind("shape_rep")
        kinds = {r.shape_kind for r in reps}
        assert {"ADVANCED_BREP_SHAPE_REPRESENTATION",
                "MANIFOLD_SURFACE_SHAPE_REPRESENTATION",
                "GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION"
                } <= kinds

    def test_pmi_summary(self):
        s = _struct("nist_stc_09_asme1_ap242-e4.stp")
        pmi = s.of_kind("pmi_summary")
        assert pmi and pmi[0].pmi.get("SHAPE_ASPECT", 0) > 100

    def test_schema_carried(self):
        s = _struct("nist_ctc_01_asme1_ap242-e1.stp")
        assert "AP242" in s.schema


class TestOslcJsonld:
    def test_graph_shape(self):
        s, jsonld, _ = structure_file(
            os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        assert "@context" in jsonld and "@graph" in jsonld
        # namespace agreement with pyoslc (the contract)
        assert jsonld["@context"]["sysml"] == OSLC_SYSML
        assert jsonld["@context"]["oslc"] == OSLC_CORE
        ids = [r["@id"] for r in jsonld["@graph"]]
        assert len(ids) == len(set(ids)), "duplicate @ids"

    def test_pd_links_product(self):
        s, jsonld, _ = structure_file(
            os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        graph = jsonld["@graph"]
        pd = next(r for r in graph
                  if "/product_definition/" in r["@id"]
                  and r.get("sysml:part"))
        assert pd["sysml:part"], "PD must link its product"


class TestOslcTurtle:
    def test_parses_in_rdflib(self):
        s, _, turtle = structure_file(
            os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        from rdflib import Graph
        g = Graph().parse(data=turtle, format="turtle")
        assert len(g) > 0

    def test_ns_matches_pyoslc_vocab(self):
        from rdflib import Graph, Namespace
        s, _, turtle = structure_file(
            os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        g = Graph().parse(data=turtle, format="turtle")
        # sysml:part predicate parses with pyoslc's namespace
        SY = Namespace(OSLC_SYSML)
        assert list(g.objects(predicate=SY.part)), "sysml:part triples"

    def test_jsonld_matches_turtle(self):
        """Both emitters derive from one structure: same resource ids."""
        s, jsonld, turtle = structure_file(
            os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp"))
        from rdflib import Graph, Namespace
        g = Graph().parse(data=turtle, format="turtle")
        ttl_ids = {str(u) for u in g.subjects()}
        jld_ids = {r["@id"].rstrip("/") for r in jsonld["@graph"]}
        assert ttl_ids == jld_ids


class TestCli:
    def test_structure_jsonld(self, capsys):
        from stepper.cli import main
        rc = main(["structure",
                   os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp")])
        assert rc == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["@graph"]

    def test_structure_turtle(self, capsys):
        from stepper.cli import main
        rc = main(["structure", "--format", "turtle",
                   os.path.join(FIXTURES, "nist_ctc_01_asme1_ap242-e1.stp")])
        assert rc == 0
        out = capsys.readouterr().out
        assert "@prefix" in out and "oslc:Resource" in out