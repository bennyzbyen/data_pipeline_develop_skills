#!/usr/bin/env python3
"""Verify fail-closed behavior for synthetic technical, COT, and report contracts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TECHNICAL_SCRIPTS = REPOSITORY_ROOT / "skills" / "data-doc-to-dev-md" / "scripts"
COT_SCRIPTS = REPOSITORY_ROOT / "skills" / "data-sync-codegen" / "scripts"
REPORT_SCRIPTS = REPOSITORY_ROOT / "skills" / "report-codegen" / "scripts"


def run_cli(arguments: Iterable[object], expected_exit_codes: set[int]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, *(str(argument) for argument in arguments)]
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in expected_exit_codes:
        raise AssertionError(
            f"unexpected exit code {result.returncode}, expected {sorted(expected_exit_codes)}\n"
            f"command: {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"expected a JSON object: {path}")
    return payload


def technical_contract_case(root: Path) -> Dict[str, Any]:
    facts_path = root / "technical" / "structured_facts.json"
    validation_path = root / "technical" / "validation.json"
    write_json(
        facts_path,
        {
            "codegen_contract": {
                "contract_version": 2,
                "project_type": "report",
                "component_kind": "standard_report",
                "ready_for_codegen": True,
                "blockers": [],
                "open_questions": [],
                "conflicts": [
                    {
                        "code": "RULE_OPERATOR_CONFLICT",
                        "kind": "rule_operator_conflict",
                        "target": "fixture.output",
                        "field": "metric_value",
                        "first_value": "value >= 10",
                        "second_value": "value > 10",
                        "status": "unresolved",
                    }
                ],
                "runtime_contract": {
                    "python_min": "3.8",
                    "entrypoint": "plugin_main.py",
                    "result_protocol": {"method": "put", "body_key": "metrics"},
                    "environment_connection_matrix": {"qa": {"connection_mode": "managed"}},
                    "safe_log_policy": {"log_credentials": False, "log_parameter_values": False},
                },
                "write_contracts": [
                    {
                        "target": "fixture.output",
                        "ordered_columns": ["metric_value"],
                        "column_types": ["Int64"],
                        "write_mode": "append",
                        "empty_output_policy": "skip",
                        "status": "confirmed",
                    }
                ],
            }
        },
    )
    run_cli(
        [
            TECHNICAL_SCRIPTS / "validate_technical_contract.py",
            "--facts",
            facts_path,
            "--json-out",
            validation_path,
        ],
        {1},
    )
    validation = load_json(validation_path)
    error_codes = {item.get("code") for item in validation.get("errors", [])}
    assert validation.get("status") == "failed", validation
    assert "RULE_OPERATOR_CONFLICT" in error_codes, validation
    return {
        "case": "conflicting_technical_contract_rejected",
        "status": "passed",
        "validator_status": validation["status"],
        "error_code": "RULE_OPERATOR_CONFLICT",
    }


def cot_facts(ready_for_codegen: bool) -> Dict[str, Any]:
    blockers = [] if ready_for_codegen else ["[TC-CG-XF00001] rowkey/runtime evidence conflicts"]
    return {
        "codegen_contract": {
            "contract_version": 2,
            "project_type": "data-sync",
            "component_kind": "cot_table_sync",
            "ready_for_codegen": ready_for_codegen,
            "blockers": blockers,
            "runtime_contract": {},
            "write_contracts": [],
        },
        "cot_report_tables": [
            {
                "business_desc": "synthetic fixture table",
                "report_type": "截P报表",
                "source_range": "2026P01~",
                "source_hbase_table": "l2_fixture.fixture_report_p",
                "clickhouse_table": "cot_fixture.fixture_report_p",
            }
        ],
        "field_dictionaries": [
            {
                "inferred_data_utilization": "fixture_report_p",
                "first_fields": ["id", "inksaa_last_modified_timestamp", "period", "code", "amount"],
            }
        ],
        "target_mappings": [
            {
                "data_utilization": "fixture_report_p",
                "catalog": "fixture_report_p",
                "hbase_target": "hbase_fixture_report_p",
                "clickhouse_target": "clickhouse_fixture_report_p",
            }
        ],
        "schedules": [
            {
                "data_utilization": "fixture_report_p",
                "task_name": "incr_sync_hbase_and_clickhouse",
                "schedule": "daily",
            }
        ],
    }


def assert_cot_runtime_blocked(project_dir: Path, table_name: str) -> None:
    params_path = project_dir / "blocked_runtime_params.json"
    write_json(params_path, {"source_table": table_name})
    result = run_cli([project_dir / "plugin_main.py", params_path], {1})
    combined = f"{result.stdout}\n{result.stderr}"
    assert "runtime is disabled" in combined, combined


def cot_contract_cases(root: Path) -> list[Dict[str, Any]]:
    cot_root = root / "cot"
    blocked_facts_path = cot_root / "blocked_facts.json"
    polluted_ready_facts = cot_facts(True)
    polluted_ready_facts["codegen_contract"].update(
        {
            "blockers": ["[TC-CG-XF00001] rowkey/runtime evidence conflicts"],
            "conflicts": [
                {
                    "code": "EVIDENCE_CONFLICT",
                    "kind": "rowkey_runtime_conflict",
                    "target": "fixture_report_p",
                    "field": "rowkey_rule_columns",
                    "status": "unresolved",
                }
            ],
            "validation_result": {
                "status": "failed",
                "errors": [
                    {
                        "code": "EVIDENCE_CONFLICT",
                        "path": "conflicts[0]",
                        "message": "Conflicting rowkey/runtime evidence must be resolved.",
                    }
                ],
            },
        }
    )
    write_json(blocked_facts_path, polluted_ready_facts)

    rejected_target = cot_root / "rejected_project"
    run_cli(
        [
            COT_SCRIPTS / "scaffold_cot_sync_project.py",
            "--structured-facts",
            blocked_facts_path,
            "--output-dir",
            rejected_target,
        ],
        {1},
    )
    assert not rejected_target.exists(), "blocked COT generation left an output directory"

    safe_target = cot_root / "safe_project"
    run_cli(
        [
            COT_SCRIPTS / "scaffold_cot_sync_project.py",
            "--structured-facts",
            blocked_facts_path,
            "--output-dir",
            safe_target,
            "--allow-blocked-scaffold",
        ],
        {0},
    )
    marker = load_json(safe_target / "SAFE_SCAFFOLD.json")
    manifest = load_json(safe_target / "cot_sync_manifest.json")
    assert marker.get("status") == "SAFE_SCAFFOLD" and marker.get("runtime_enabled") is False, marker
    assert manifest.get("artifact_status", {}).get("status") == "SAFE_SCAFFOLD", manifest
    assert manifest["tables"] and all(table.get("runtime_enabled") is False for table in manifest["tables"]), manifest
    assert all("safe_scaffold_runtime_disabled" in table.get("contract_issues", []) for table in manifest["tables"]), manifest

    safe_validation_path = cot_root / "safe_validation.json"
    run_cli(
        [
            COT_SCRIPTS / "verify_cot_manifest_semantics.py",
            "--project-dir",
            safe_target,
            "--json-out",
            safe_validation_path,
        ],
        {1},
    )
    safe_validation = load_json(safe_validation_path)
    assert safe_validation.get("artifact_status") == "SAFE_SCAFFOLD", safe_validation
    assert safe_validation.get("runtime_enabled") is False, safe_validation
    assert safe_validation.get("deployment_status") == "review_required", safe_validation
    assert_cot_runtime_blocked(safe_target, "fixture_report_p")

    ready_facts_path = cot_root / "ready_facts.json"
    ready_target = cot_root / "ready_with_allow_project"
    write_json(ready_facts_path, cot_facts(True))
    run_cli(
        [
            COT_SCRIPTS / "scaffold_cot_sync_project.py",
            "--structured-facts",
            ready_facts_path,
            "--output-dir",
            ready_target,
            "--allow-blocked-scaffold",
        ],
        {0},
    )
    ready_manifest = load_json(ready_target / "cot_sync_manifest.json")
    assert not (ready_target / "SAFE_SCAFFOLD.json").exists(), "ready COT contract was incorrectly downgraded"
    assert all(table.get("runtime_enabled") is True for table in ready_manifest["tables"]), ready_manifest

    tampered_target = cot_root / "tampered_project"
    shutil.copytree(ready_target, tampered_target)
    tampered_manifest_path = tampered_target / "cot_sync_manifest.json"
    tampered_manifest = load_json(tampered_manifest_path)
    tampered_manifest["tables"][0]["rowkey_rule_columns"] = ["missing_rowkey_column"]
    tampered_manifest["tables"][0]["runtime_enabled"] = False
    write_json(tampered_manifest_path, tampered_manifest)
    tampered_validation_path = cot_root / "tampered_validation.json"
    run_cli(
        [
            COT_SCRIPTS / "verify_cot_manifest_semantics.py",
            "--project-dir",
            tampered_target,
            "--json-out",
            tampered_validation_path,
        ],
        {1},
    )
    tampered_validation = load_json(tampered_validation_path)
    tampered_codes = {item.get("code") for item in tampered_validation.get("errors", [])}
    assert {"runtime_manifest_mismatch", "rowkey_columns_mismatch"}.issubset(tampered_codes), tampered_validation

    return [
        {
            "case": "polluted_ready_cot_contract_rejected_without_artifacts",
            "status": "passed",
            "output_created": False,
        },
        {
            "case": "cot_safe_scaffold_explicit_and_runtime_disabled",
            "status": "passed",
            "artifact_status": safe_validation["artifact_status"],
            "runtime_enabled": safe_validation["runtime_enabled"],
        },
        {
            "case": "cot_rowkey_runtime_tampering_rejected",
            "status": "passed",
            "error_codes": sorted(tampered_codes),
        },
        {
            "case": "ready_cot_contract_not_downgraded_by_allow_flag",
            "status": "passed",
            "runtime_enabled": True,
        },
    ]


def load_valid_report_plan() -> Dict[str, Any]:
    sys.path.insert(0, str(REPORT_SCRIPTS))
    try:
        from verify_generic_report_runtime_semantics import build_plan

        return build_plan("standard_report")
    finally:
        sys.path.remove(str(REPORT_SCRIPTS))


def assert_report_runtime_blocked(project_dir: Path) -> None:
    command = (
        "import sys; "
        f"sys.path.insert(0, {str(project_dir)!r}); "
        "import plugin_main; plugin_main.main({})"
    )
    result = run_cli(["-c", command], {1})
    combined = f"{result.stdout}\n{result.stderr}"
    assert "SAFE_SCAFFOLD runtime is disabled" in combined, combined


def report_contract_cases(root: Path) -> list[Dict[str, Any]]:
    report_root = root / "report"
    valid_plan = load_valid_report_plan()
    invalid_plan = json.loads(json.dumps(valid_plan))
    invalid_plan["execution_contract"]["outputs"]["region_sales"]["columns"] = ["region"]
    invalid_plan["execution_contract"]["writes"]["region_sales"]["table"] = "qa.wrong_output"
    invalid_plan_path = report_root / "invalid_plan.json"
    write_json(invalid_plan_path, invalid_plan)

    rejected_target = report_root / "rejected_project"
    run_cli(
        [
            REPORT_SCRIPTS / "scaffold_report_project.py",
            "--plan",
            invalid_plan_path,
            "--target",
            rejected_target,
        ],
        {1},
    )
    assert not rejected_target.exists(), "invalid report generation left an output directory"

    safe_target = report_root / "safe_project"
    run_cli(
        [
            REPORT_SCRIPTS / "scaffold_report_project.py",
            "--plan",
            invalid_plan_path,
            "--target",
            safe_target,
            "--allow-blocked-scaffold",
        ],
        {0},
    )
    marker = load_json(safe_target / "SAFE_SCAFFOLD.json")
    assert marker.get("status") == "SAFE_SCAFFOLD" and marker.get("runtime_enabled") is False, marker
    safe_validation_path = report_root / "safe_validation.json"
    run_cli(
        [
            REPORT_SCRIPTS / "verify_report_plan_semantics.py",
            "--project-dir",
            safe_target,
            "--json-out",
            safe_validation_path,
        ],
        {1},
    )
    safe_validation = load_json(safe_validation_path)
    safe_codes = {item.get("code") for item in safe_validation.get("errors", [])}
    assert safe_validation.get("artifact_status") == "SAFE_SCAFFOLD", safe_validation
    assert safe_validation.get("runtime_enabled") is False, safe_validation
    assert "execution_output_columns_mismatch" in safe_codes, safe_validation
    assert "execution_write_table_mismatch" in safe_codes, safe_validation
    assert_report_runtime_blocked(safe_target)

    valid_plan_path = report_root / "valid_plan.json"
    ready_target = report_root / "ready_with_allow_project"
    write_json(valid_plan_path, valid_plan)
    run_cli(
        [
            REPORT_SCRIPTS / "scaffold_report_project.py",
            "--plan",
            valid_plan_path,
            "--target",
            ready_target,
            "--allow-blocked-scaffold",
        ],
        {0},
    )
    assert not (ready_target / "SAFE_SCAFFOLD.json").exists(), "ready report contract was incorrectly downgraded"
    ready_validation_path = report_root / "ready_validation.json"
    run_cli(
        [
            REPORT_SCRIPTS / "verify_report_plan_semantics.py",
            "--project-dir",
            ready_target,
            "--json-out",
            ready_validation_path,
        ],
        {0},
    )
    ready_validation = load_json(ready_validation_path)
    assert ready_validation.get("artifact_status") == "GENERATED", ready_validation
    assert ready_validation.get("runtime_enabled") is True, ready_validation

    return [
        {
            "case": "invalid_report_output_write_contract_rejected_without_artifacts",
            "status": "passed",
            "output_created": False,
        },
        {
            "case": "report_safe_scaffold_explicit_and_runtime_disabled",
            "status": "passed",
            "artifact_status": safe_validation["artifact_status"],
            "error_codes": sorted(safe_codes),
        },
        {
            "case": "ready_report_contract_not_downgraded_by_allow_flag",
            "status": "passed",
            "runtime_enabled": True,
        },
    ]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="negative_contract_safety_") as temp_dir:
        root = Path(temp_dir)
        cases = [technical_contract_case(root), *cot_contract_cases(root), *report_contract_cases(root)]
    print(
        json.dumps(
            {
                "status": "passed",
                "external_connection_count": 0,
                "case_count": len(cases),
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
