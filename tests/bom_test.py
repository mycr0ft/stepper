"""Phase C item 2: AP242 MIM → ISO/TS 10303-3001 OBP mapping.

Every mapping in stepper.bom.MIM_TO_OBP_EXACT is verified against the
real -3001 class inventory (fixture vendored from
ap238.org/smrl/data/business_object_models/) and exercised against
the NIST AP242 fixtures.
"""
import json
import os

import pytest

from stepper.bom import MIM_TO_OBP_EXACT, OBPModel, to_obp, to_obp_json, bom_schema
from stepper.express import load_express

BOM = os.path.join(os.path.dirname(__file__), "fixtures", "express", "bom_3001.exp")
NIST = os.path.join(os.path.dirname(__file__), "fixtures", "nist")
CTC = os.path.join(NIST, "nist_ctc_01_asme1_ap242-e1.stp")
FTC = os.path.join(NIST, "nist_ftc_09_asme1_ap242-e1.stp")


@pytest.fixture(scope="module")
def ctc():
    return to_obp(CTC, file_label="ctc01.stp")


@pytest.fixture(scope="module")
def ftc():
    return to_obp(FTC, file_label="ftc09.stp")


class TestMappingTable:
    def test_bom_fixture_present(self):
        assert os.path.exists(BOM)

    def test_every_mapped_target_is_a_bom_entity(self):
        bom = load_express(BOM)
        missing = {t for t in set(MIM_TO_OBP_EXACT.values())
                   if t not in bom.entities}
        assert not missing, f"mapping targets absent from -3001 BOM: {missing}"

    def test_core_mapping_rows(self):
        assert MIM_TO_OBP_EXACT["PRODUCT"] == "Part"
        assert MIM_TO_OBP_EXACT["PRODUCT_DEFINITION_FORMATION"] == "PartVersion"
        assert MIM_TO_OBP_EXACT["PRODUCT_DEFINITION"] == "IndividualPartView"
        assert MIM_TO_OBP_EXACT["NEXT_ASSEMBLY_USAGE_OCCURRENCE"] == "NextAssemblyViewUsage"


class TestToOBP:
    def test_ctc_map_counts(self, ctc):
        classes = {n.obp_class for n in ctc.nodes.values()}
        assert "Part" in classes
        assert "PartVersion" in classes
        assert "IndividualPartView" in classes

    def test_provenance_is_step_ref(self, ctc):
        part = ctc.of_class("Part")[0]
        assert part.step_ref.startswith("#")
        int(part.step_ref[1:])  # numeric

    def test_obp_id_format(self, ctc):
        for oid in ctc.nodes:
            assert oid.startswith("obp:")

    def test_part_chain(self, ctc):
        """Part ← PartVersion ← IndividualPartView → ExternalGeometricModel."""
        version = ctc.of_class("PartVersion")[0]
        assert version.obp_refs and version.obp_refs[0].startswith("obp:Part#")
        view = ctc.of_class("IndividualPartView")[0]
        assert any(r.startswith("obp:PartVersion#") for r in view.obp_refs)
        assert any("GeometricModel" in r for r in view.obp_refs), view.obp_refs

    def test_names_survive_mapping(self, ctc):
        part = ctc.of_class("Part")[0]
        assert part.name == "NIST Test Case 1"

    def test_ftc_four_parts(self, ftc):
        assert len(ftc.of_class("Part")) == 4
        assert len(ftc.of_class("IndividualPartView")) == 4

    def test_ftc_shape_kinds_split(self, ftc):
        kinds = {n.obp_class for n in ftc.nodes.values()}
        assert "ExternalAdvancedBrepShapeRepresentation" in kinds
        assert "ExternalManifoldSurfaceShapeRepresentation" in kinds
        assert "ExternalGeometricallyBoundedWireframeShapeRepresentation" in kinds

    def test_report_shape(self, ctc):
        rep = ctc.report
        assert rep["mapped_total"] == len(ctc.nodes)
        assert rep["instances_total"] > rep["mapped_total"]  # geometry atoms stay unmapped
        assert isinstance(rep["unmapped_top"], dict)

    def test_unmapped_are_not_obp_classes(self, ctc):
        """Cartesian points/edges etc. legitimately stay out — OBP abstracts geometry."""
        classes = {n.obp_class for n in ctc.nodes.values()}
        assert "CARTESIAN_POINT" not in classes


class TestToOBPJson:
    def test_json_payload_shape(self, ctc):
        payload = to_obp_json(ctc)
        assert payload["obm"] == "iso-ts-10303-3001"
        assert payload["file"] == "ctc01.stp"
        assert len(payload["nodes"]) == len(ctc.nodes)
        json.dumps(payload)  # serializable

    def test_json_node_fields(self, ctc):
        payload = to_obp_json(ctc)
        part = next(n for n in payload["nodes"] if n["@type"] == "Part")
        assert part["name"] == "NIST Test Case 1"
        assert part["step_ref"].startswith("#")
        assert isinstance(part["obp_refs"], list)

    def test_all_nist_files_map(self):
        files = sorted(f for f in os.listdir(NIST) if f.endswith(".stp"))
        total_nodes = 0
        for f in files:
            m = to_obp(os.path.join(NIST, f))
            assert m.nodes, f
            total_nodes += len(m.nodes)
        assert total_nodes >= 80