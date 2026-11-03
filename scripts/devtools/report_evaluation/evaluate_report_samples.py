#!/usr/bin/env python3
"""Replay frozen deidentified document oracles and optional offline workflows."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time


def checked_file(root: Path, name: str, expected_hash: str) -> Path:
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("corpus member escapes its root") from exc
    if Path(name).is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("invalid corpus member or SHA256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("corpus input/oracle changed; review and freeze a new baseline")
    return path


def schema_replay(fields):
    return {"version": 1, "sources": {"document_schema": {"kind": "injected", "columns": list(fields)}},
            "steps": [{"id": "projected", "op": "project", "input": "document_schema", "columns": list(fields)}],
            "outputs": {"result": {"input": "projected", "columns": list(fields)}},
            "writes": {"result": {"kind": "clickhouse", "table": "fixture.schema_replay", "mode": "append"}}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    corpus, output = args.corpus.resolve(), args.out.resolve()
    if output == corpus or corpus in output.parents:
        raise ValueError("output must be outside the frozen corpus")
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") not in {1, 2} or not isinstance(manifest.get("cases"), list) or not manifest["cases"]:
        raise ValueError("unsupported or empty corpus manifest")
    ids = [case.get("id", "") for case in manifest["cases"]]
    if len(set(ids)) != len(ids) or not all(re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in ids):
        raise ValueError("case IDs must be unique safe names")
    source_root = args.source_root.resolve()
    sys.path.insert(0, str(source_root / "skills/report-codegen/scripts"))
    sys.path.insert(0, str(source_root / "skills/data-doc-to-dev-md/scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if manifest["version"] == 2:
        from report_sample_workflow import evaluate_corpus
        return evaluate_corpus(manifest, corpus, output, checked_file)
    from extract_docx_bundle import build_parser, run
    from report_contract import validate_execution_contract
    from source_reference import storage_kind

    output.mkdir(parents=True, exist_ok=True)
    results = []
    for case in manifest["cases"]:
        path = checked_file(corpus, case["input"], case["input_sha256"])
        oracle_path = checked_file(corpus, case["expected"], case["expected_sha256"])
        expected = json.loads(oracle_path.read_text(encoding="utf-8"))
        case_output = output / ("extracted_" + case["id"])
        arguments = build_parser().parse_args(["--input", str(path), "--out", str(case_output), "--project-name", case["id"]])
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            status = run(arguments)
        if status != 0:
            raise ValueError("document extraction failed")
        facts = json.loads((case_output / "dev_doc/structured_facts.json").read_text(encoding="utf-8"))
        fields = [field for mapping in facts.get("report_field_mappings", []) for field in mapping.get("fields", [])]
        source_contracts = facts["codegen_contract"].get("source_contracts", [])
        checks = {
            "source_inventory": sorted((row["storage"].lower(), row["table_or_path"]) for row in facts["report_sources"])
                == sorted((row["storage"], row["location"]) for row in expected["sources"]),
            "source_identity_status": sorted((row["exact_location"], row["location_status"]) for row in source_contracts)
                == sorted((row["location"], row["identity_status"]) for row in expected["sources"]),
            "physical_targets": sorted({(storage_kind(row["storage"]), row["table"]) for row in facts["report_physical_targets"]})
                == sorted({(row["storage"], row["location"]) for row in expected["targets"]}),
            "field_order": [row["target_field"] for row in fields] == expected["field_keys"],
            "source_field_text": [row.get("source_field", "") for row in fields] == expected["source_fields"],
            "unapproved_business_logic_not_marked_complete": facts["codegen_contract"]["ready_for_codegen"] is False,
        }
        contract = schema_replay(expected["field_keys"])
        plan_outputs = [{"target_name": "result", "physical_table": "fixture.schema_replay", "final_columns": expected["field_keys"]}]
        valid = validate_execution_contract(contract, plan_outputs)
        checks["declared_schema_replay"] = valid["status"] == "passed"
        contract["sources"]["document_schema"]["columns"] = expected["field_keys"][1:]
        invalid = validate_execution_contract(contract, plan_outputs)
        checks["missing_field_mutation_rejected"] = invalid["status"] == "failed"
        results.append({"id": case["id"], "checks": checks, "passed": all(checks.values()),
                        "extraction_seconds": time.perf_counter() - started,
                        "input_sha256": case["input_sha256"], "expected_sha256": case["expected_sha256"],
                        "oracle_status": case.get("oracle_status", "unreviewed"),
                        "human_business_approved": case.get("human_business_approved") is True,
                        "negative_mutation_errors": invalid["errors"]})
        checked_file(corpus, case["input"], case["input_sha256"])
        checked_file(corpus, case["expected"], case["expected_sha256"])
    report = {"status": "passed" if all(case["passed"] for case in results) else "failed",
              "case_count": len(results), "passed_cases": sum(case["passed"] for case in results),
              "false_allows": sum(not case["checks"]["missing_field_mutation_rejected"] for case in results),
              "false_blocks": sum(not case["checks"]["declared_schema_replay"] for case in results),
              "structural_check_failures": sum(sum(not ok for name, ok in case["checks"].items()
                                                     if name not in {"declared_schema_replay", "missing_field_mutation_rejected"}) for case in results),
              "business_formula_gold_status": manifest.get("business_formula_gold_status", "unreviewed"),
              "scope": manifest.get("scope", []), "excluded_scope": manifest.get("excluded_scope", []),
              "notes": ["Document structure oracles are frozen independently of extractor output.",
                        "Schema replay and its missing-field mutation are derived tests, not business-value goldens.",
                        "No model workflow, database, production job or deployment is executed."],
              "cases": results}
    (output / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "case_count", "passed_cases", "false_allows", "false_blocks", "structural_check_failures", "business_formula_gold_status")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
