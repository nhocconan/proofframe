"""Export the seed's schemas and clearly labeled synthetic fixtures; no APIs."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from jsonschema import Draft202012Validator
from proofframe_contracts.models import Contract, VerificationReport, RepairPlan, RepairReceipt, fingerprint
from proofframe_contracts.policy import evaluate, validate_plan, validate_receipt
from tests.factories import fixture, repair_fixture, change


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export() -> None:
    models = {"contract": Contract, "report": VerificationReport,
              "repair-plan": RepairPlan, "repair-receipt": RepairReceipt}
    for name, model in models.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)
        write(ROOT / "schemas" / f"{name}.schema.json", schema)
    for profile in ("film", "brand", "educational"):
        contract, report = fixture(status="FAIL", profile=profile)
        original = contract.assertions[0]
        if profile == "brand":
            original = change(original, source_pointer="/brand/approved_copy",
                              predicate="matches_exact_approved_copy", expected="Approved demo slogan v1")
        elif profile == "educational":
            original = change(original, source_pointer="/lesson/illustrated_example",
                              predicate="narration_matches_visible_count",
                              expected="Show two apples while narration says two apples")
        contract = change(contract, assertions=(original,))
        report = change(report, contract_sha256=fingerprint(contract))
        evaluate(contract, report)
        for name, value in (("contract", contract), ("report", report)):
            Draft202012Validator(models[name].model_json_schema()).validate(value.model_dump(mode="json"))
            write(ROOT / "examples" / profile / f"{name}.json", value.model_dump(mode="json"))
    contract, report, plan, receipt = repair_fixture()
    validate_plan(contract, report, plan)
    validate_receipt(contract, report, plan, receipt, current_assets=report.assets)
    for name, value in (("contract", contract), ("report", report),
                        ("repair-plan", plan), ("repair-receipt", receipt)):
        Draft202012Validator(models[name].model_json_schema()).validate(value.model_dump(mode="json"))
        write(ROOT / "examples" / "repair_roundtrip" / f"{name}.json", value.model_dump(mode="json"))
    print("Validated 4 JSON Schemas and 10 synthetic example documents; no model or media evaluation.")


if __name__ == "__main__":
    export()
