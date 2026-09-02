#!/usr/bin/env python3
"""Exercise synthetic technical-design-to-codegen routes without external services."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOC_SCRIPTS = REPOSITORY_ROOT / "skills" / "data-doc-to-dev-md" / "scripts"
SYNC_SCRIPTS = REPOSITORY_ROOT / "skills" / "data-sync-codegen" / "scripts"
REPORT_SCRIPTS = REPOSITORY_ROOT / "skills" / "report-codegen" / "scripts"


def run_python(arguments: Iterable[object], expected_codes: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, *(str(argument) for argument in arguments)]
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    allowed = expected_codes or {0}
    if completed.returncode not in allowed:
        raise AssertionError(
            f"command returned {completed.returncode}, expected {sorted(allowed)}: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def write_design_package(root: Path, facts: dict[str, Any], blocked: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    requirement_docx = root / "synthetic_requirement.docx"
    title = "Synthetic PipelineForge requirement for deterministic offline validation"
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{html.escape(title)}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(requirement_docx, "w") as docx:
        docx.writestr("word/document.xml", document_xml)
    run_python(
        [
            DOC_SCRIPTS / "extract_docx_bundle.py",
            "--docx",
            requirement_docx,
            "--out",
            root,
            "--project-name",
            "Synthetic PipelineForge E2E",
        ]
    )

    dev_doc = root / "dev_doc"
    extracted_facts_path = dev_doc / "structured_facts.json"
    extracted_facts = json.loads(extracted_facts_path.read_text(encoding="utf-8"))
    # These fixtures intentionally exercise the legacy single-contract route.
    # Do not mix it with a v3 proposal inferred from the title-only DOCX. The
    # separate technical-contract regression covers explicit v3 confirmation.
    assert facts["codegen_contract"]["contract_version"] == 1
    for key in ("project_contract", "code_unit_plan", "code_units"):
        extracted_facts.pop(key, None)
    extracted_facts.update(facts)
    extracted_facts_path.write_text(json.dumps(extracted_facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    technical_design_path = dev_doc / "technical_design.md"
    technical_design_path.write_text(
        technical_design_path.read_text(encoding="utf-8")
        + "\n## Synthetic Confirmation Overlay\n\n"
        + "Fixture-only contracts below are confirmed solely for deterministic offline validation.\n",
        encoding="utf-8",
    )
    questions = (
        "# Questions\n\n## Blocking Code Generation\n\n- [TC-CG-901] Confirm the synthetic rowkey contract.\n"
        if blocked
        else "# Questions\n\n## Blocking Code Generation\n\n- None.\n"
    )
    (dev_doc / "questions.md").write_text(questions, encoding="utf-8")
    assert {path.name for path in dev_doc.iterdir()} == {
        "technical_design.md",
        "structured_facts.json",
        "questions.md",
    }
    return dev_doc


def cot_table(table_name: str, fields: list[str], with_period: bool) -> dict[str, list[dict[str, Any]]]:
    return {
        "cot_report_tables": [
            {
                "business_desc": "synthetic table",
                "report_type": "截P报表" if with_period else "执行报表",
                "source_range": "fixture range",
                "source_hbase_table": f"fixture_hbase.{table_name}",
                "clickhouse_table": f"fixture_clickhouse.{table_name}",
            }
        ],
        "field_dictionaries": [
            {"inferred_data_utilization": table_name, "first_fields": fields}
        ],
        "target_mappings": [
            {
                "data_utilization": table_name,
                "catalog": table_name,
                "hbase_target": f"hbase_{table_name}",
                "clickhouse_target": f"clickhouse_{table_name}",
            }
        ],
        "schedules": [
            {
                "data_utilization": table_name,
                "task_name": "fixture_sync",
                "schedule": "synthetic daily",
            }
        ],
    }


def cot_facts(ready: bool = True) -> dict[str, Any]:
    with_period = cot_table(
        "ic_detail_gb_p",
        ["id", "inksaa_last_modified_timestamp", "period", "code", "amount"],
        True,
    )
    without_period = cot_table(
        "rpt_exe_visit_frequency_by_people",
        ["id", "inksaa_last_modified_timestamp", "store_code", "amount"],
        False,
    )
    for key in without_period:
        with_period[key].extend(without_period[key])
    return {
        "codegen_contract": {
            "contract_version": 1,
            "project_type": "data-sync",
            "component_kind": "cot_table_sync",
            "ready_for_codegen": ready,
            "blockers": [] if ready else ["[TC-CG-901] synthetic rowkey remains unconfirmed"],
        },
        **with_period,
    }


def load_report_seed_plan() -> dict[str, Any]:
    module_path = REPORT_SCRIPTS / "verify_generic_report_runtime_semantics.py"
    module_name = "pipelineforge_generic_report_seed"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load report regression module: {module_path}")
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(REPORT_SCRIPTS))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build_plan("standard_report")
    finally:
        sys.path[:] = original_path


def report_facts() -> dict[str, Any]:
    seed = load_report_seed_plan()
    sources: list[dict[str, Any]] = []
    for storage, items in seed["sources"].items():
        for item in items:
            sources.append(
                {
                    "storage": storage,
                    "table_or_path": item.get("table_or_path", ""),
                    "fields": item.get("fields", []),
                    "range": "synthetic period",
                }
            )
    outputs = seed["outputs"]
    return {
        "report_sources": sources,
        "report_physical_targets": seed["physical_targets"],
        "report_targets": [
            {
                "target_name": output["target_name"],
                "description": output["target_description"],
                "storage": output["storage"],
            }
            for output in outputs
        ],
        "report_field_mappings": [
            {
                "inferred_target_name": output["target_name"],
                "inferred_physical_table": output["physical_table"],
                "fields": output["field_rules"],
            }
            for output in outputs
        ],
        "report_schedules": [{"schedule": "synthetic daily"}],
        "codegen_contract": {
            "contract_version": 1,
            "project_type": "report",
            "component_kind": "standard_report",
            "ready_for_codegen": True,
            "blockers": [],
        },
        "report_execution_contract": seed["execution_contract"],
    }


def run_cot_success(root: Path) -> dict[str, Any]:
    dev_doc = write_design_package(root / "cot_success", cot_facts())
    facts = dev_doc / "structured_facts.json"
    project = root / "cot_success" / "project"
    commands = [
        [DOC_SCRIPTS / "validate_technical_contract.py", "--facts", facts],
        [SYNC_SCRIPTS / "scaffold_cot_sync_project.py", "--structured-facts", facts, "--output-dir", project, "--project-name", "synthetic_cot"],
        ["-m", "compileall", "-q", project],
        [SYNC_SCRIPTS / "verify_cot_manifest_semantics.py", "--project-dir", project],
        [SYNC_SCRIPTS / "verify_codegen_observability.py", "--project-dir", project],
        [SYNC_SCRIPTS / "verify_cot_runtime_semantics.py", "--project-dir", project],
    ]
    for command in commands:
        run_python(command)
    manifest = json.loads((project / "cot_sync_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["tables"]) == 2, manifest
    assert all(table["runtime_enabled"] for table in manifest["tables"]), manifest
    return {
        "case": "cot_sync_success",
        "status": "passed",
        "docx_extraction": "passed",
        "table_count": 2,
        "check_count": len(commands) + 1,
    }


def run_report_success(root: Path) -> dict[str, Any]:
    dev_doc = write_design_package(root / "report_success", report_facts())
    facts = dev_doc / "structured_facts.json"
    plan_dir = root / "report_success" / "plan"
    project = root / "report_success" / "project"
    plan = plan_dir / "report_codegen_plan.json"
    commands = [
        [DOC_SCRIPTS / "validate_technical_contract.py", "--facts", facts],
        [REPORT_SCRIPTS / "build_report_codegen_plan.py", "--facts", facts, "--out", plan_dir],
        [REPORT_SCRIPTS / "scaffold_report_project.py", "--plan", plan, "--target", project],
        ["-m", "compileall", "-q", project],
        [REPORT_SCRIPTS / "verify_report_plan_semantics.py", "--project-dir", project],
        [REPORT_SCRIPTS / "verify_codegen_observability.py", "--project-dir", project],
        [REPORT_SCRIPTS / "verify_generic_report_runtime_semantics.py", "--component-kind", "standard_report"],
    ]
    for command in commands:
        run_python(command)
    built_plan = json.loads(plan.read_text(encoding="utf-8"))
    assert built_plan["summary"]["ready_for_codegen"] is True, built_plan["summary"]
    assert built_plan["execution_validation"]["status"] == "passed", built_plan["execution_validation"]
    return {
        "case": "generic_report_success",
        "status": "passed",
        "docx_extraction": "passed",
        "output_count": 1,
        "check_count": len(commands) + 1,
    }


def run_blocked_contract(root: Path) -> dict[str, Any]:
    dev_doc = write_design_package(root / "blocked", cot_facts(ready=False), blocked=True)
    facts = dev_doc / "structured_facts.json"
    rejected_project = root / "blocked" / "rejected_project"
    rejected = run_python(
        [SYNC_SCRIPTS / "scaffold_cot_sync_project.py", "--structured-facts", facts, "--output-dir", rejected_project],
        expected_codes={1},
    )
    assert "blocks full scaffolding" in rejected.stderr, rejected.stderr
    assert not rejected_project.exists(), rejected_project

    safe_project = root / "blocked" / "safe_project"
    run_python([DOC_SCRIPTS / "validate_technical_contract.py", "--facts", facts])
    run_python(
        [
            SYNC_SCRIPTS / "scaffold_cot_sync_project.py",
            "--structured-facts",
            facts,
            "--output-dir",
            safe_project,
            "--allow-blocked-scaffold",
        ]
    )
    manifest = json.loads((safe_project / "cot_sync_manifest.json").read_text(encoding="utf-8"))
    assert manifest["codegen_contract"]["ready_for_codegen"] is False, manifest["codegen_contract"]
    assert manifest["codegen_contract"]["blockers"], manifest["codegen_contract"]
    return {
        "case": "blocked_contract",
        "status": "passed",
        "docx_extraction": "passed",
        "full_codegen_exit_code": rejected.returncode,
        "safe_scaffold_status": "SAFE_SCAFFOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pipelineforge_e2e_") as temp_dir:
        root = Path(temp_dir)
        cases = [run_cot_success(root), run_report_success(root), run_blocked_contract(root)]
    print(
        json.dumps(
            {
                "status": "passed",
                "case_count": len(cases),
                "cases": cases,
                "handoff_file_count_per_case": 3,
                "external_service_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
