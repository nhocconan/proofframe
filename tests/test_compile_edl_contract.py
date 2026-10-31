import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from proofframe_contracts.models import Contract

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "compile_edl_contract", Path(__file__).parents[1] / "scripts" / "compile_edl_contract.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
compile_edl = _mod.compile_edl

EDL = [
    {"shot": "C01_S01", "take": 1, "start": 2.0, "dur": 4.0, "line": None},
    {"shot": "C01_S02", "take": 1, "start": 0.3, "dur": 4.83,
     "line": "Đài của hội trường người ta."},
    {"shot": "C01_S03", "take": 2, "start": 0.3, "dur": 3.95,
     "line": "Ba mua trong lô đó, bỏ kho tới giờ."},
]


def _contract():
    return compile_edl(EDL, asset_id="cut", contract_id="c", tenant_id="t",
                       profile_revision="test")


def test_compiles_only_spoken_lines_with_cumulative_scopes():
    contract = _contract()
    rows = contract["assertions"]
    assert [r["assertion_id"] for r in rows] == ["dlg-c01-s02", "dlg-c01-s03"]
    assert rows[0]["scope"] == {"start_ms": 4000, "end_ms": 8830}
    assert rows[1]["scope"] == {"start_ms": 8830, "end_ms": 12780}
    assert rows[0]["expected"] == "Đài của hội trường người ta."
    obs = rows[0]["observation"]
    assert obs["kind"] == "dialogue" and obs["double_transcription"] is True
    assert obs["language_bias"] == ["Vietnamese"]


def test_compiled_contract_validates_against_model_and_schema():
    contract = _contract()
    Contract.model_validate(contract)
    schema = json.loads((Path(__file__).parents[1] / "schemas/contract.schema.json").read_text())
    Draft202012Validator(schema).validate(contract)


def test_empty_edl_yields_no_assertions():
    assert compile_edl([], asset_id="a", contract_id="c", tenant_id="t",
                       profile_revision="x")["assertions"] == []
