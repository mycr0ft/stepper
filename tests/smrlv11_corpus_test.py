"""SMRL v11 EXPRESS corpus (expresslang/smrlv11) — the current-edition library.

1,326 schemas from expresslang/smrlv11 (ELF-annotated import of
standards.iso.org/iso/10303/smrl/v11/tech/smrlv11.zip): 590 modules
(arm/mim shortforms; longforms + concatenations for the -239/-442/-400
SysML-mapping chain), 135 resource schemas.

Phase C significance: reference_schema_for_sysml_mapping IS
ISO/TS 10303-400:2025 (the SysML-mapping ARM) — acquired here as the
bridge cornerstone. 105,311 entities corpus-wide, all parse clean.
"""
import glob
import os

import pytest

from stepper.express import load_express

V11_ROOT = os.path.join(os.path.dirname(__file__), "fixtures", "express", "smrlv11")


def _all():
    return sorted(glob.glob(os.path.join(V11_ROOT, "**", "*.exp"), recursive=True))


V11 = _all()


def _entities(schema):
    ents = schema.entities
    return ents() if callable(ents) else ents


def test_v11_corpus_present():
    assert len(V11) >= 1300, f"SMRL v11 corpus missing: {len(V11)}"


def test_sysml_mapping_module_present():
    """ISO/TS 10303-400:2025 — the Phase C bridge cornerstone."""
    arm = os.path.join(V11_ROOT, "modules", "reference_schema_for_sysml_mapping", "arm.exp")
    arm_lf = os.path.join(V11_ROOT, "modules", "reference_schema_for_sysml_mapping", "arm_lf.exp")
    assert os.path.exists(arm) and os.path.exists(arm_lf)
    s = load_express(arm_lf)
    ents = _entities(s)
    # the longform concatenates the whole -239/-442 domain
    assert len(ents) >= 2400, len(ents)


def test_ap242_ed4_modules_parse():
    m = os.path.join(V11_ROOT, "modules", "ap242_managed_model_based_3d_engineering")
    for f in ("arm.exp", "mim.exp", "arm_lf.exp"):
        ents = _entities(load_express(os.path.join(m, f)))
        assert isinstance(ents, dict)


@pytest.mark.parametrize("path", V11)
def test_v11_schema_parses(path):
    ents = _entities(load_express(path))
    assert isinstance(ents, dict)
