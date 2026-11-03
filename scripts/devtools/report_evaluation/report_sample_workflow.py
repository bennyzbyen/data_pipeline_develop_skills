"""Offline document evaluation with explicit, isolated normalization fixtures."""
from __future__ import annotations

from collections import Counter
import contextlib
import copy
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def structure_checks(facts, expected):
    from source_reference import storage_kind

    fields = [field for mapping in facts.get("report_field_mappings", []) for field in mapping.get("fields", [])]
    keys = ("target_field", "source_field", "source_desc", "source_table", "calculation_logic", "field_type")
    def compared(field):
        return {key: field.get(key, "") if key == "target_field" else " ".join(field.get(key, "").split()) for key in keys}
    actual_fields = [compared(field) for field in fields]
    expected_fields = [compared(field) for field in expected["fields"]]
    explicit_sources = [(index, row) for index, row in enumerate(facts["report_sources"], 1)
                        if row.get("source_kind") != "inferred_from_field_mapping"]
    explicit_ids = {f"source_{index:03d}" for index, _ in explicit_sources}
    actual_sources = Counter((storage_kind(row["storage"]), row["table_or_path"]) for _, row in explicit_sources)
    expected_sources = Counter((row["storage"], row["location"]) for row in expected["sources"])
    actual_targets = {(storage_kind(row["storage"]), row["table"]) for row in facts["report_physical_targets"]}
    expected_targets = {(row["storage"], row["location"]) for row in expected["targets"]}
    actual_names = Counter(field["target_field"] for field in fields)
    expected_names = Counter(field["target_field"] for field in expected["fields"])
    by_name = {field["target_field"]: field for field in expected_fields}
    checks = {
        "source_inventory": actual_sources == expected_sources,
        "source_identity_status": sorted((row["exact_location"], row["location_status"]) for row in facts["codegen_contract"].get("source_contracts", []) if row["id"] in explicit_ids)
            == sorted((row["location"], row["identity_status"]) for row in expected["sources"]),
        "physical_targets": actual_targets == expected_targets,
        "ordered_field_records": actual_fields == expected_fields,
        "document_readiness": facts["codegen_contract"]["ready_for_codegen"] is expected["document_ready_for_codegen"],
    }
    differences = {"missing_sources": sum((expected_sources - actual_sources).values()),
                   "unexpected_sources": sum((actual_sources - expected_sources).values()),
                   "missing_targets": len(expected_targets - actual_targets), "unexpected_targets": len(actual_targets - expected_targets),
                   "missing_fields": sum((expected_names - actual_names).values()),
                   "unexpected_fields": sum((actual_names - expected_names).values()),
                   "wrong_field_records": sum(field != by_name[field["target_field"]] for field in actual_fields if field["target_field"] in by_name),
                   "field_order_errors": int([row["target_field"] for row in fields] != [row["target_field"] for row in expected["fields"]])}
    return checks, differences, fields


def document_gate(facts):
    """Exercise the real planner gate without promoting the document's readiness."""
    from build_report_codegen_plan import build_plan

    try:
        plan = build_plan(facts)
    except ValueError as exc:
        if str(exc).startswith("code_unit_plan is "):
            return {"blocked": True, "stage": "code_unit_selection", "reason": str(exc)}
        raise
    return {"blocked": plan["summary"]["ready_for_codegen"] is False, "stage": "plan_readiness",
            "reason": "document plan readiness"}


def fixture_facts(fields, specification, conversion=None):
    """Select declared mappings; never replace extraction with expected answers."""
    by_name = {field["target_field"]: field for field in fields}
    selected = []
    kind = specification.get("kind")
    if kind == "document_rule_candidate":
        if not conversion or conversion["status"] != "passed":
            raise ValueError("rule fixture requires a passed evidence conversion audit")
        selected = [copy.deepcopy(by_name[name]) for name in specification["output_fields"]]
    else:
        for binding in specification["bindings"]:
            field = by_name.get(binding["target_field"])
            if field is None or field.get("source_field") != binding["source_field"]:
                raise ValueError("normalized binding differs from extracted source-field evidence")
            selected.append(copy.deepcopy(field))
    contract = specification["execution_contract"]
    if (specification.get("version") != 1 or kind not in {"document_declared_direct_copy", "document_rule_candidate"}
            or specification.get("fixture_only") is not True or not selected
            or any(source.get("kind") != "injected" for source in contract["sources"].values())
            or any(write.get("mode") != "append" or write.get("table") != "fixture.result" for write in contract["writes"].values())):
        raise ValueError("offline fixtures require injected sources and append-only fixture.result writes")
    return {"evaluation_fixture_only": True, "normalization_kind": specification["kind"],
            "report_sources": [{"storage": "injected", "table_or_path": name, "fields": source["columns"]}
                               for name, source in contract["sources"].items()],
            "report_targets": [{"target_name": "offline_result", "storage": "clickhouse"}],
            "report_physical_targets": [{"table": "fixture.result", "storage": "clickhouse"}],
            "report_field_mappings": [{"inferred_target_name": "offline_result", "inferred_physical_table": "fixture.result", "fields": selected}],
            "report_execution_contract": copy.deepcopy(contract),
            "codegen_contract": {"contract_version": 1, "project_type": "report", "component_kind": "standard_report",
                                 "ready_for_codegen": True, "blockers": []}}


def reject_network(*args, **kwargs):
    raise RuntimeError("network is disabled during offline sample evaluation")


class FakeWriter:
    def __init__(self):
        self.events = []
        self.payloads = []

    def command(self, sql):
        raise AssertionError("offline fixtures must not issue SQL commands")

    def insert_df(self, table, frame):
        self.events.append({"table": table, "rows": len(frame), "columns": list(frame.columns)})
        self.payloads.append(frame.copy())


def execute_generated(project, specification, timings=None):
    timings = timings if timings is not None else {}
    started = time.perf_counter()
    import pandas as pd
    timings["dependency_import"] = time.perf_counter() - started

    prefixes = ("common_utils", "data_utils", "gateway", "params_configs", "hbase", "fs")
    saved = {name: module for name, module in sys.modules.items() if name.split(".")[0] in prefixes}
    for name in saved:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(project))
    writer = FakeWriter()
    def insert_file(client, table, file_path, column_names, database, settings):
        rows = [[None if value == "\\N" else value for value in row] for row in csv.reader(io.StringIO(Path(file_path).read_text(encoding="utf-8")))]
        client.insert_df(database + "." + table if database else table, pd.DataFrame(rows, columns=column_names))
    try:
        with contextlib.ExitStack() as guards:
            for owner, method in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                                  (socket, "create_connection"), (socket, "getaddrinfo"), (socket, "gethostbyname")):
                guards.enter_context(patch.object(owner, method, reject_network))
            started = time.perf_counter()
            DataSource = importlib.import_module("data_utils.data_source").DataSource
            DataProcess = importlib.import_module("data_utils.data_process").DataProcess
            DataStorage = importlib.import_module("data_utils.data_storage").DataStorage
            timings["project_import"] = time.perf_counter() - started
            started = time.perf_counter()
            params = dict(specification.get("params") or {}, clickhouse_client=writer, clickhouse_insert_file=insert_file,
                          source_data={name: pd.DataFrame(rows, columns=specification["execution_contract"]["sources"][name]["columns"])
                                       for name, rows in specification["source_data"].items()})
            timings["input_build"] = time.perf_counter() - started
            started = time.perf_counter()
            source_data, time_range = DataSource(params).run()
            timings["source"] = time.perf_counter() - started
            started = time.perf_counter()
            outputs = DataProcess(source_data, time_range, params).run()
            timings["process"] = time.perf_counter() - started
            started = time.perf_counter()
            metrics = DataStorage(outputs, time_range, params).run()
            timings["storage"] = time.perf_counter() - started
        started = time.perf_counter()
        result = outputs["offline_result"]
        actual = {"columns": list(result.columns), "rows": result.astype(object).where(pd.notna(result), None).values.tolist(),
                  "write_events": writer.events,
                  "written_rows": [frame.astype(object).where(pd.notna(frame), None).values.tolist() for frame in writer.payloads]}
        timings["result_capture"] = time.perf_counter() - started
        return actual, metrics
    finally:
        sys.path.remove(str(project))
        for name in list(sys.modules):
            if name.split(".")[0] in prefixes:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def evaluate_workflow(fields, specification, expected_output, directory, source_design, expected_conversion=None):
    from build_report_codegen_plan import build_plan
    from scaffold_report_project import scaffold
    from verify_codegen_observability import verify
    from verify_generated_safety import verify as verify_safety
    from verify_report_plan_semantics import validate_project

    stages = {}
    stage = "conversion_audit" if expected_conversion is not None or specification.get("kind") == "document_rule_candidate" else "normalization"
    started = time.perf_counter()
    conversion = None
    execution_seconds = {}
    try:
        if stage == "conversion_audit":
            from requirement_conversion import validate_conversion

            if expected_conversion is None:
                raise ValueError("rule fixture requires an independent frozen conversion reference")
            conversion = validate_conversion(fields, specification, expected_conversion)
            write_json(directory / "conversion_audit.json", conversion)
            stages[stage] = time.perf_counter() - started
            if conversion["status"] == "failed":
                raise ValueError("; ".join(conversion["errors"]))
            if conversion["status"] == "pending":
                return {"status": "pending", "stage_seconds": stages, "conversion": conversion, "business_approved": False}
            stage, started = "normalization", time.perf_counter()
        facts = fixture_facts(fields, specification, conversion)
        handoff = directory / "evaluation_handoff"
        write_json(handoff / "structured_facts.json", facts)
        (handoff / "technical_design.md").write_text(source_design + "\n\n## Offline Evaluation Fixture\n\nSelected document mappings on synthetic rows; this handoff does not approve the full business report.\n", encoding="utf-8")
        (handoff / "questions.md").write_text("# Evaluation Scope\n\nThe fixture is complete for local replay. Original business approval remains pending in the unmodified document handoff.\n", encoding="utf-8")
        stages[stage] = time.perf_counter() - started
        stage, started = "plan", time.perf_counter()
        plan = build_plan(facts)
        if plan["summary"]["ready_for_codegen"] is not True:
            raise ValueError("normalized fixture plan was blocked")
        plan_path = directory / "report_codegen_plan.json"
        write_json(plan_path, plan)
        stages[stage] = time.perf_counter() - started
        stage, started = "scaffold", time.perf_counter()
        project = directory / "project"
        scaffold(plan_path, project)
        stages[stage] = time.perf_counter() - started
        stage, started = "compile_and_validate", time.perf_counter()
        for path in project.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        validation = validate_project(project)
        observability = verify(project)
        safety = verify_safety(project)
        if any(check["status"] != "passed" for check in (validation, observability, safety)):
            raise ValueError("generated fixture failed project, observability or safety checks")
        stages[stage] = time.perf_counter() - started
        stage, started = "execute_and_compare", time.perf_counter()
        actual, metrics = execute_generated(project, specification, execution_seconds)
        write_json(directory / "actual_output.json", actual)
        checks = {"output_columns": actual["columns"] == expected_output["columns"],
                  "output_rows": actual["rows"] == expected_output["rows"],
                  "fake_write_rows": actual["written_rows"] == [expected_output["rows"]],
                  "fake_write_events": actual["write_events"] == expected_output["write_events"]}
        stages[stage] = time.perf_counter() - started
        return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "stage_seconds": stages,
                "failed_stage": None if all(checks.values()) else stage, "metrics": metrics,
                "normalization": specification["kind"] + " on synthetic rows", "business_approved": False,
                "conversion": conversion, "execution_seconds": execution_seconds}
    except Exception as exc:
        stages[stage] = time.perf_counter() - started
        return {"status": "failed", "failed_stage": stage, "error_type": type(exc).__name__, "error": str(exc),
                "stage_seconds": stages, "conversion": conversion, "execution_seconds": execution_seconds}


def evaluate_corpus(manifest, corpus, output, checked_file):
    from extract_docx_bundle import build_parser, run

    output.mkdir(parents=True, exist_ok=True)
    results = []
    for case in manifest["cases"]:
        started = time.perf_counter()
        result = {"id": case["id"], "passed": False, "human_business_approved": case.get("human_business_approved") is True,
                  "origin_sha256": case.get("origin_sha256"), "variant": case.get("variant"), "stage_seconds": {}}
        stage = "integrity"
        try:
            members = [(item["path"], item["sha256"]) for item in case["inputs"]]
            members.append((case["expected"], case["expected_sha256"]))
            if case.get("workflow"):
                members.append((case["workflow"], case["workflow_sha256"]))
            paths = [checked_file(corpus, name, digest) for name, digest in members]
            expected = json.loads(paths[len(case["inputs"])].read_text(encoding="utf-8"))
            if "conversion" in expected and expected["conversion"]["document_sha256"] != [item["sha256"] for item in case["inputs"]]:
                raise ValueError("conversion reference belongs to different input documents")
            directory = output / case["id"]
            stage, timer = "extract", time.perf_counter()
            arguments = build_parser().parse_args(["--input", *map(str, paths[:len(case["inputs"])]), "--out", str(directory / "document"), "--project-name", case["id"]])
            with contextlib.redirect_stdout(io.StringIO()):
                if run(arguments) != 0:
                    raise ValueError("document extraction failed")
            result["stage_seconds"][stage] = time.perf_counter() - timer
            handoff = directory / "document/dev_doc"
            facts_path = handoff / "structured_facts.json"
            facts_hash = hashlib.sha256(facts_path.read_bytes()).hexdigest()
            facts = json.loads(facts_path.read_text(encoding="utf-8"))
            original = fingerprint(facts)
            stage, timer = "structure_and_gate", time.perf_counter()
            checks, differences, fields = structure_checks(facts, expected)
            gate = document_gate(facts)
            checks["document_generation_gate"] = gate["blocked"] is (case["expected_document_outcome"] == "blocked")
            result.update(checks=checks, differences=differences, document_gate=gate)
            result["stage_seconds"][stage] = time.perf_counter() - timer
            if case.get("workflow") and all(checks.values()):
                specification = json.loads(paths[-1].read_text(encoding="utf-8"))
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result["workflow"] = evaluate_workflow(fields, specification, expected.get("offline_output"), directory,
                                                           (handoff / "technical_design.md").read_text(encoding="utf-8"), expected.get("conversion"))
            checks["original_handoff_unchanged"] = fingerprint(facts) == original and hashlib.sha256(facts_path.read_bytes()).hexdigest() == facts_hash
            for name, digest in members:
                checked_file(corpus, name, digest)
            result["passed"] = all(checks.values()) and (not case.get("workflow") or result.get("workflow", {}).get("status") in {"passed", "pending"})
        except Exception as exc:
            result.update(failed_stage=stage, error_type=type(exc).__name__, error=str(exc))
        result["elapsed_seconds"] = time.perf_counter() - started
        results.append(result)
    workflows = [case.get("workflow", {}) for case in results if case.get("workflow")]
    metric_names = ("missing_sources", "unexpected_sources", "missing_targets", "unexpected_targets", "missing_fields", "unexpected_fields", "wrong_field_records", "field_order_errors")
    report = {"version": 2, "status": "passed" if all(case["passed"] for case in results) else "failed",
              "case_count": len(results), "passed_cases": sum(case["passed"] for case in results),
              "unique_origin_documents": len({case["origin_sha256"] for case in results if case.get("origin_sha256")}),
              "workflow_requested": sum(bool(case.get("workflow")) for case in manifest["cases"]),
              "workflow_evaluated": len(workflows),
              "workflow_executed": sum("execute_and_compare" in case.get("stage_seconds", {}) for case in workflows),
              "workflow_passed": sum(case.get("status") == "passed" for case in workflows),
              "workflow_pending": sum(case.get("status") == "pending" for case in workflows),
              "conversion_checked": sum(case.get("conversion") is not None for case in workflows),
              "conversion_failures": sum(case.get("failed_stage") == "conversion_audit" for case in workflows),
              "false_allows": sum(case.get("document_gate", {}).get("blocked") is False and manifest["cases"][index]["expected_document_outcome"] == "blocked" for index, case in enumerate(results)),
              "false_blocks": sum(case.get("workflow", {}).get("failed_stage") in {"plan", "scaffold"} for case in results),
              "runtime_output_failures": sum(case.get("failed_stage") == "execute_and_compare" for case in workflows),
              "integrity_failures": sum(case.get("failed_stage") == "integrity" for case in results),
              "workflow_not_executed": sum(bool(case.get("workflow")) for case in manifest["cases"])
                  - sum("execute_and_compare" in case.get("stage_seconds", {}) for case in workflows),
              "differences": {name: sum(case.get("differences", {}).get(name, 0) for case in results) for name in metric_names},
              "business_formula_gold_status": manifest.get("business_formula_gold_status", "unreviewed"),
              "scope": manifest.get("scope", []), "excluded_scope": manifest.get("excluded_scope", []),
              "notes": ["One extraction per case feeds document checks and the normalized fixture workflow.",
                        "Prose whitespace is normalized for comparison; ordered field identifiers remain exact. Raw oracles retain source layout.",
                        "Source inventory checks cover explicit tables; inferred sources remain observed evidence, not independently approved inventory.",
                        "Direct-copy normalization is explicit fixture input. Rule candidates record their origin and require a frozen conversion reference.",
                        "A pending result passes preservation checks without planning, generating or running the unresolved rule; fragment passes never approve a full report.",
                        "Only generated trusted templates run with injected rows, fake writes and blocked socket connections."],
              "cases": results}
    write_json(output / "evaluation.json", report)
    print(json.dumps({key: report[key] for key in ("status", "case_count", "passed_cases", "unique_origin_documents", "workflow_executed", "workflow_passed", "false_allows", "false_blocks")}))
    return 0 if report["status"] == "passed" else 1
