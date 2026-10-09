"""Baseline gate (Phase C close-out): pin → verify → CI gate.

The PLM released-configuration discipline, CLI-driven so pipelines
don't need a running pyoslc: identical content → identical id (the
pin holds), any content change → new id (the gate fires).
"""
import json
import os

import pytest

from stepper.baselines import (
    BaselineInput, baseline_id_from_manifest, create_baseline, gate,
    verify_baseline,
)

NIST = os.path.join(os.path.dirname(__file__), "fixtures", "nist")
CTC = os.path.join(NIST, "nist_ctc_01_asme1_ap242-e1.stp")
FTC11 = os.path.join(NIST, "nist_ftc_11_asme1_ap242-e3.stp")


def _inp(step_files=(CTC,), title="SRR-1", author="jf") -> BaselineInput:
    return BaselineInput(step_files=list(step_files),
                         title=title, author=author)


class TestCreate:
    def test_id_is_content_addressed(self):
        b1 = create_baseline(_inp())
        b2 = create_baseline(_inp())
        assert b1["id"] == b2["id"]
        assert b1["id"].startswith("bl:")

    def test_annotations_do_not_shift_the_id(self):
        """title/author are annotations — a pipeline gate must not fire
        when someone renames the release."""
        b1 = create_baseline(_inp(title="SRR-1", author="jf"))
        b2 = create_baseline(_inp(title="renamed review", author="xx"))
        assert b1["id"] == b2["id"]

    def test_content_change_shifts_the_id(self):
        ids = {create_baseline(_inp(files))["id"]
               for files in [(CTC,), (FTC11,), (CTC, FTC11)]}
        assert len(ids) == 3

    def test_manifest_shape(self):
        b = create_baseline(_inp())
        kinds = [a["kind"] for a in b["artifacts"]]
        # sources + the three derived payloads
        assert kinds.count("step") == 1
        assert "step_structure" in kinds
        assert "step_obp" in kinds
        assert "step_uuid" in kinds

    def test_obp_payload_inside_manifest(self):
        b = create_baseline(_inp())
        obp = next(a for a in b["artifacts"] if a["kind"] == "step_obp")
        assert obp["sha256"] and obp["size"] > 0

    def test_uuid_payload_deterministic(self):
        b1 = create_baseline(_inp())
        b2 = create_baseline(_inp())
        u1 = next(a for a in b1["artifacts"] if a["kind"] == "step_uuid")
        u2 = next(a for a in b2["artifacts"] if a["kind"] == "step_uuid")
        assert u1["sha256"] == u2["sha256"]


class TestGate:
    def test_gate_passes_on_same_content(self):
        manifest_path = os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".hermes", "nope")
        manifest_path = "/tmp/bl_gate_test.json"
        create_baseline(_inp())      # warm the derived payload cache paths
        b = create_baseline(_inp())
        with open(manifest_path, "w") as fh:
            json.dump({k: v for k, v in b.items() if k != "artifacts_bytes"}, fh)
        try:
            assert gate(manifest_path, _inp()) == 0
        finally:
            os.unlink(manifest_path)

    def test_gate_fails_on_drift(self):
        b = create_baseline(_inp((CTC,)))
        manifest_path = "/tmp/bl_gate_test2.json"
        with open(manifest_path, "w") as fh:
            json.dump({k: v for k, v in b.items() if k != "artifacts_bytes"}, fh)
        try:
            drift = BaselineInput(step_files=[FTC11])
            assert gate(manifest_path, drift) == 1
        finally:
            os.unlink(manifest_path)

    def test_gate_output_pinpoints_first_diff(self, capsys):
        b = create_baseline(_inp((CTC,)))
        manifest_path = "/tmp/bl_gate_test3.json"
        with open(manifest_path, "w") as fh:
            json.dump({k: v for k, v in b.items() if k != "artifacts_bytes"}, fh)
        try:
            drift = BaselineInput(step_files=[FTC11])
            gate(manifest_path, drift)
            out = capsys.readouterr().out
            assert "changed: step" in out
        finally:
            os.unlink(manifest_path)


class TestVerify:
    def test_verify_matches_when_same(self):
        b = create_baseline(_inp())
        res = verify_baseline(b, _inp())
        assert res["matches_current"] is True

    def test_verify_catches_drift(self):
        b = create_baseline(_inp((CTC,)))
        res = verify_baseline(b, _inp((FTC11,)))
        assert res["matches_current"] is False
        assert "changed: step" in (res["first_diff"] or "")

    def test_manifest_round_trip(self, tmp_path):
        """The pinned manifest is plain JSON — save/reload keeps ids."""
        b = create_baseline(_inp())
        p = tmp_path / "bl.json"
        p.write_text(json.dumps({k: v for k, v in b.items()
                                 if k != "artifacts_bytes"}))
        loaded = json.loads(p.read_text())
        assert baseline_id_from_manifest(
            {"artifacts": loaded["artifacts"]}) == b["id"]