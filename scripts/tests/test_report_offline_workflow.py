#!/usr/bin/env python3
"""Offline corpus accuracy, integrity and generated write-payload regressions."""
from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT, EVALUATION_TOOLS

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE_ROOT / "skills/report-codegen/scripts"))
sys.path.insert(0, str(SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"))
module_path = EVALUATION_TOOLS / "report_sample_workflow.py"
spec = importlib.util.spec_from_file_location("round7_workflow_driver", module_path)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def fixture(transport="insert_df"):
    fields = [{"target_field": "identifier", "source_field": "id"}, {"target_field": "renamed", "source_field": "value"}]
    columns = ["identifier", "renamed"]
    contract = {"version": 1, "sources": {"source": {"kind": "injected", "columns": ["id", "value"]}},
                "steps": [{"id": "mapped", "op": "derive", "input": "source", "columns": {
                    "identifier": {"op": "copy", "column": "id"}, "renamed": {"op": "copy", "column": "value"}}},
                          {"id": "projected", "op": "project", "input": "mapped", "columns": columns}],
                "outputs": {"offline_result": {"input": "projected", "columns": columns}},
                "writes": {"offline_result": {"kind": "clickhouse", "table": "fixture.result", "mode": "append", "transport": transport}}}
    specification = {"version": 1, "kind": "document_declared_direct_copy", "fixture_only": True,
                     "bindings": copy.deepcopy(fields), "execution_contract": contract, "params": {"current_date": "2026-01-02"},
                     "source_data": {"source": [{"id": "A", "value": "1"}, {"id": None, "value": "two"}]}}
    oracle = {"columns": columns, "rows": [["A", "1"], [None, "two"]],
              "write_events": [{"table": "fixture.result", "rows": 2, "columns": columns}]}
    return fields, specification, oracle


def make_corpus(root):
    from verify_docx_bundle_multidoc import make_docx, make_xlsx

    corpus = root / "corpus"
    corpus.mkdir()
    sources = make_xlsx(root / "sources.xlsx", [["位置", "数据表名", "数据表", "取数范围", "字段"],
        ["HBase", "source label", "fixture.source", "fixture range", "id,value"]])
    dictionary = make_xlsx(root / "fields.xlsx", [["字段key", "字段名称", "来源字段"], ["identifier", "identifier", "id"], ["renamed", "value", "value"]])
    path = corpus / "input.docx"
    make_docx(path, "Synthetic offline corpus", [sources, dictionary], [])
    fields, specification, oracle = fixture()
    expected = {"sources": [{"storage": "hbase", "location": "fixture.source", "identity_status": "confirmed"}], "targets": [],
                "fields": [dict(row, source_desc="", source_table="", calculation_logic="", field_type="") for row in fields],
                "document_ready_for_codegen": False, "offline_output": oracle}
    paths = {}
    for name, value in [("expected", expected), ("workflow", specification)]:
        member = corpus / (name + ".json")
        member.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = member
    case = {"id": "valid", "inputs": [{"path": "input.docx", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
            "expected": "expected.json", "expected_sha256": hashlib.sha256(paths["expected"].read_bytes()).hexdigest(),
            "workflow": "workflow.json", "workflow_sha256": hashlib.sha256(paths["workflow"].read_bytes()).hexdigest(),
            "expected_document_outcome": "blocked", "human_business_approved": False}
    manifest = {"version": 2, "business_formula_gold_status": "not_human_approved", "cases": [case]}
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return corpus, manifest


class GeneratedPayload(unittest.TestCase):
    def test_legacy_v1_writes_keep_ordered_columns_and_values_for_both_transports(self):
        for transport in ("insert_df", "insert_file"):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as temporary:
                fields, specification, oracle = fixture(transport)
                before = copy.deepcopy((fields, specification, oracle))
                result = workflow.evaluate_workflow(fields, specification, oracle, Path(temporary), "# Fixture")
                self.assertEqual("passed", result["status"], result)
                self.assertTrue(result["checks"]["fake_write_rows"])
                self.assertEqual(before, (fields, specification, oracle))

    def test_valid_column_wrong_value_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fields, specification, oracle = fixture()
            specification["execution_contract"]["steps"][0]["columns"]["renamed"]["column"] = "id"
            result = workflow.evaluate_workflow(fields, specification, oracle, Path(temporary), "# Fixture")
            self.assertEqual("failed", result["status"])
            self.assertEqual("execute_and_compare", result["failed_stage"])
            self.assertFalse(result["checks"]["output_rows"])

    def test_file_wire_replay_preserves_quoted_multiline_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            fields, specification, oracle = fixture("insert_file")
            value = 'comma, newline\n"quoted"'
            specification["source_data"]["source"][0]["value"] = value
            oracle["rows"][0][1] = value
            result = workflow.evaluate_workflow(fields, specification, oracle, Path(temporary), "# Fixture")
            self.assertEqual("passed", result["status"], result)

    def test_v2_cannot_silently_use_v1_missing_write_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            fields, specification, oracle = fixture()
            specification["execution_contract"]["version"] = 2
            result = workflow.evaluate_workflow(fields, specification, oracle, Path(temporary), "# Fixture")
            self.assertEqual("failed", result["status"])
            self.assertEqual("execute_and_compare", result["failed_stage"])
            self.assertIn("ordered target columns", result["error"])

    def test_wrong_extracted_binding_cannot_be_repaired_from_the_oracle(self):
        fields, specification, _ = fixture()
        fields[0]["source_field"] = "value"
        with self.assertRaisesRegex(ValueError, "differs from extracted"):
            workflow.fixture_facts(fields, specification)

    def test_fixture_refuses_live_sources_or_destructive_writes(self):
        for path, value in (("kind", "hbase"), ("mode", "replace_where")):
            with self.subTest(path=path):
                fields, specification, _ = fixture()
                if path == "kind":
                    specification["execution_contract"]["sources"]["source"][path] = value
                else:
                    specification["execution_contract"]["writes"]["offline_result"][path] = value
                with self.assertRaisesRegex(ValueError, "injected sources"):
                    workflow.fixture_facts(fields, specification)

    def test_generated_modules_do_not_leak_between_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            for index, value in enumerate(("first", "second")):
                fields, specification, oracle = fixture()
                specification["source_data"]["source"][0]["value"] = value
                oracle["rows"][0][1] = value
                if index:
                    fields[1]["source_field"] = "alternate_value"
                    specification["bindings"][1]["source_field"] = "alternate_value"
                    specification["execution_contract"]["sources"]["source"]["columns"][1] = "alternate_value"
                    specification["execution_contract"]["steps"][0]["columns"]["renamed"]["column"] = "alternate_value"
                    for row in specification["source_data"]["source"]:
                        row["alternate_value"] = row.pop("value")
                result = workflow.evaluate_workflow(fields, specification, oracle, Path(temporary) / str(index), "# Fixture")
                self.assertEqual("passed", result["status"], result)

    def test_generated_connection_attempt_is_blocked_before_socket_use(self):
        for method, call in (("create_connection", "socket.create_connection(('offline.invalid', 1))"),
                             ("getaddrinfo", "socket.getaddrinfo('offline.invalid', 1)")):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                (project / "data_utils").mkdir()
                (project / "data_utils/__init__.py").touch()
                (project / "data_utils/data_source.py").write_text(
                    "import socket\nclass DataSource:\n def __init__(self, params): pass\n def run(self): " + call + "\n", encoding="utf-8")
                for filename, classname in (("data_process", "DataProcess"), ("data_storage", "DataStorage")):
                    (project / "data_utils" / (filename + ".py")).write_text("class " + classname + ": pass\n", encoding="utf-8")
                with patch.object(socket, method) as network:
                    with self.assertRaisesRegex(RuntimeError, "network is disabled"):
                        workflow.execute_generated(project, fixture()[1])
                    network.assert_not_called()


class CorpusEvaluation(unittest.TestCase):
    def run_corpus(self, corpus, output):
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(EVALUATION_TOOLS / "evaluate_report_samples.py"),
                                 "--corpus", str(corpus), "--out", str(output), "--source-root", str(SOURCE_ROOT)],
                                capture_output=True, text=True, encoding="utf-8", timeout=90)
        return result, json.loads((output / "evaluation.json").read_text(encoding="utf-8"))

    def test_document_handoff_plan_project_and_fake_write_are_replayed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus, _ = make_corpus(root)
            result, report = self.run_corpus(corpus, root / "out")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, report["workflow_passed"])
            self.assertTrue(report["cases"][0]["checks"]["original_handoff_unchanged"])
            self.assertFalse(report["cases"][0]["human_business_approved"])
            self.assertEqual("not_human_approved", report["business_formula_gold_status"])

    def test_bad_hash_is_reported_without_losing_later_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus, manifest = make_corpus(root)
            bad = copy.deepcopy(manifest["cases"][0])
            bad.update(id="bad", expected_sha256="0" * 64)
            manifest["cases"].insert(0, bad)
            (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result, report = self.run_corpus(corpus, root / "out")
            self.assertEqual(1, result.returncode)
            self.assertEqual("integrity", report["cases"][0]["failed_stage"])
            self.assertTrue(report["cases"][1]["passed"])

    def test_structural_mutations_are_counted_and_never_replaced_by_expected_fields(self):
        facts = {"report_sources": [], "report_physical_targets": [], "codegen_contract": {"ready_for_codegen": False},
                 "report_field_mappings": [{"fields": [{"target_field": "id", "source_field": "wrong"}, {"target_field": "extra"}]}]}
        expected = {"sources": [], "targets": [], "document_ready_for_codegen": False,
                    "fields": [{"target_field": "id", "source_field": "correct"}, {"target_field": "missing"}]}
        before = copy.deepcopy(facts)
        checks, differences, fields = workflow.structure_checks(facts, expected)
        self.assertFalse(checks["ordered_field_records"])
        self.assertEqual(1, differences["missing_fields"])
        self.assertEqual(1, differences["unexpected_fields"])
        self.assertEqual(1, differences["wrong_field_records"])
        self.assertEqual("wrong", fields[0]["source_field"])
        self.assertEqual(before, facts)
