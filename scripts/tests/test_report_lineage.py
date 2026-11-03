#!/usr/bin/env python3
"""Offline execution-column lineage and codegen-gateway regressions."""

from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT, EVALUATION_TOOLS, load_runtime

import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


REPORT = SOURCE_ROOT / "skills/report-codegen"
sys.path.insert(0, str(SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"))
sys.path.insert(0, str(SOURCE_ROOT / "skills/pipeline-forge-guide/scripts"))
sys.path.insert(0, str(REPORT / "scripts"))

from build_report_codegen_plan import build_plan
from code_unit_contract import confirm_code_unit_plan
from report_contract import validate_execution_contract
from scaffold_report_project import scaffold
from verify_generic_report_runtime_semantics import build_plan as fixture_plan
from verify_multi_code_unit_delivery import structured_facts


def simple_plan(columns, steps, output_columns, extra_sources=None):
    contract = {"version": 1, "sources": {"source": {"kind": "injected", "columns": columns}}, "steps": steps,
                "outputs": {"result": {"input": steps[-1]["id"], "columns": output_columns}},
                "writes": {"result": {"kind": "clickhouse", "table": "fixture.result", "mode": "append"}}}
    contract["sources"].update(extra_sources or {})
    outputs = [{"target_name": "result", "physical_table": "fixture.result", "final_columns": output_columns}]
    return contract, outputs


def validate(plan):
    return validate_execution_contract(*plan)




class ColumnLineage(unittest.TestCase):
    def assert_blocked(self, plan, path_fragment):
        before = copy.deepcopy(plan)
        result = validate(plan)
        self.assertEqual("failed", result["status"], result)
        self.assertTrue(any(path_fragment in item["path"] for item in result["errors"]), result)
        self.assertEqual(before, plan)

    def test_filter_column_must_exist(self):
        plan = fixture_plan("standard_report")
        plan["execution_contract"]["steps"][0]["conditions"][0]["column"] = "unknown_period"
        self.assert_blocked((plan["execution_contract"], plan["outputs"]), "conditions[0].column")

    def test_derive_operand_must_exist(self):
        plan = fixture_plan("standard_report")
        plan["execution_contract"]["steps"][1]["columns"]["revenue"]["operands"][0]["column"] = "unknown_amount"
        self.assert_blocked((plan["execution_contract"], plan["outputs"]), "operands[0].column")

    def test_copy_and_coalesce_columns_must_exist(self):
        for expression in ({"op": "copy", "column": "missing"}, {"op": "coalesce", "columns": ["id", "missing"]}):
            with self.subTest(expression=expression):
                self.assert_blocked(simple_plan(["id"], [{"id": "derived", "op": "derive", "input": "source",
                    "columns": {"value": expression}}], ["value"]), ".columns.value")

    def test_join_key_must_exist_on_both_sides(self):
        for side in ("left", "right"):
            with self.subTest(side=side):
                left, right = (["id"], ["other"]) if side == "right" else (["other"], ["id"])
                self.assert_blocked(simple_plan(left, [{"id": "joined", "op": "join", "left": "source", "right": "right", "on": ["id"]}],
                    ["id"], {"right": {"kind": "injected", "columns": right}}), ".on")

    def test_aggregate_input_and_group_columns_must_exist(self):
        for group, column in ((["missing"], "value"), (["id"], "missing")):
            with self.subTest(group=group):
                self.assert_blocked(simple_plan(["id", "value"], [{"id": "grouped", "op": "aggregate", "input": "source",
                    "group_by": group, "aggregations": {"total": {"column": column, "agg": "sum"}}}], ["id", "total"]), "steps[0]")

    def test_projection_and_deduplication_columns_must_exist(self):
        for op in ("select", "project", "deduplicate"):
            with self.subTest(op=op):
                step = {"id": "selected", "op": op, "input": "source"}
                step["subset" if op == "deduplicate" else "columns"] = ["missing"]
                self.assert_blocked(simple_plan(["id"], [step], ["id"]), "steps[0]")

    def test_rename_requires_old_columns_and_detects_collisions(self):
        for mapping in ({"missing": "other"}, {"id": "value"}):
            with self.subTest(mapping=mapping):
                self.assert_blocked(simple_plan(["id", "value"], [{"id": "renamed", "op": "rename", "input": "source", "columns": mapping}],
                    ["value"]), ".columns")

    def test_aggregate_drops_unselected_source_columns(self):
        self.assert_blocked(simple_plan(["id", "value", "unused"], [
            {"id": "grouped", "op": "aggregate", "input": "source", "group_by": ["id"],
             "aggregations": {"total": {"column": "value", "agg": "sum"}}},
            {"id": "selected", "op": "project", "input": "grouped", "columns": ["unused"]}], ["unused"]), "steps[1].columns")

    def test_output_cannot_claim_a_column_missing_from_its_input(self):
        self.assert_blocked(simple_plan(["id", "value"], [{"id": "selected", "op": "project", "input": "source", "columns": ["id"]}],
            ["id", "value"]), "outputs.result.columns")

    def test_source_and_projection_duplicate_columns_are_rejected(self):
        for columns, projection in ((["id", "id"], ["id"]), (["id"], ["id", "id"])):
            with self.subTest(columns=columns):
                self.assert_blocked(simple_plan(columns, [{"id": "selected", "op": "project", "input": "source", "columns": projection}],
                    ["id"]), ".columns")

    def test_derived_columns_are_available_in_insertion_order(self):
        plan = simple_plan(["value"], [{"id": "derived", "op": "derive", "input": "source", "columns": {
            "first": {"op": "copy", "column": "value"}, "second": {"op": "copy", "column": "first"}}}], ["second"])
        self.assertEqual("passed", validate(plan)["status"])
        plan[0]["steps"][0]["columns"] = {"second": {"op": "copy", "column": "first"}, "first": {"op": "copy", "column": "value"}}
        self.assert_blocked(plan, ".columns.second.column")

    def test_output_columns_cannot_repeat_a_name(self):
        plan = simple_plan(["id"], [{"id": "selected", "op": "project", "input": "source", "columns": ["id"]}], ["id", "id"])
        self.assert_blocked(plan, "outputs.result.columns")

    def test_malformed_output_columns_retain_validation_errors(self):
        for columns in (1, "id", {"id": True}):
            with self.subTest(columns=columns):
                plan = simple_plan(["id"], [{"id": "selected", "op": "project", "input": "source", "columns": ["id"]}], ["id"])
                plan[0]["outputs"]["result"]["columns"] = columns
                self.assert_blocked(plan, "outputs.result.columns")

    def test_overwriting_an_existing_derived_column_keeps_it_available(self):
        plan = simple_plan(["value"], [{"id": "derived", "op": "derive", "input": "source", "columns": {
            "value": {"op": "add", "operands": [{"column": "value"}, {"value": 1}]}}}], ["value"])
        self.assertEqual("passed", validate(plan)["status"])

    def test_union_keeps_columns_from_all_inputs(self):
        plan = simple_plan(["id", "left_value"], [{"id": "combined", "op": "union", "inputs": ["source", "right"]}],
            ["id", "left_value", "right_value"], {"right": {"kind": "injected", "columns": ["id", "right_value"]}})
        self.assertEqual("passed", validate(plan)["status"])

    def test_grouped_and_global_count_without_a_column_remain_valid(self):
        for group in ([], ["id"]):
            with self.subTest(group=group):
                plan = simple_plan(["id", "value"], [{"id": "grouped", "op": "aggregate", "input": "source", "group_by": group,
                    "aggregations": {"rows": {"agg": "count"}}}], group + ["rows"])
                self.assertEqual("passed", validate(plan)["status"])

    def test_rename_swap_and_exact_field_case_are_preserved(self):
        plan = simple_plan(["A", "b"], [{"id": "renamed", "op": "rename", "input": "source", "columns": {"A": "b", "b": "A"}}], ["b", "A"])
        self.assertEqual("passed", validate(plan)["status"])
        plan[0]["steps"][0]["columns"] = {"a": "b"}
        self.assert_blocked(plan, ".columns")

    def test_literals_and_parameter_values_are_not_column_references(self):
        plan = simple_plan(["id"], [{"id": "derived", "op": "derive", "input": "source", "columns": {
            "literal": {"op": "literal", "value": "missing_column"},
            "time": {"op": "literal", "value_from": "time_range.period"},
            "tag": {"op": "concat", "operands": [{"column": "id"}, {"value_from": "params.suffix"}]}}}], ["literal", "time", "tag"])
        self.assertEqual("passed", validate(plan)["status"])

    def test_unknown_frame_retains_structural_error_without_inventing_columns(self):
        result = validate(simple_plan(["id"], [{"id": "selected", "op": "project", "input": "missing_frame", "columns": ["missing_column"]}], ["missing_column"]))
        self.assertEqual("failed", result["status"])
        self.assertIn("unknown_step_input", {item["code"] for item in result["errors"]})
        self.assertNotIn("unknown_input_column", {item["code"] for item in result["errors"]})

    def test_exact_spaces_and_unicode_field_names_are_preserved(self):
        plan = simple_plan([" value ", "业务 字段"], [{"id": "selected", "op": "project", "source": "source",
            "columns": ["业务 字段", " value "]}], ["业务 字段", " value "])
        self.assertEqual("passed", validate(plan)["status"])

    def test_only_projection_operations_accept_the_source_input_alias(self):
        self.assertEqual("passed", validate(simple_plan(["id"], [{"id": "selected", "op": "select", "source": "source", "columns": ["id"]}], ["id"]))["status"])
        result = validate(simple_plan(["id"], [{"id": "filtered", "op": "filter", "source": "source",
            "conditions": [{"column": "id", "operator": "eq", "value": 1}]}], ["id"]))
        self.assertEqual("failed", result["status"])

    def test_unused_literal_operands_do_not_create_field_dependencies(self):
        plan = simple_plan(["id"], [{"id": "derived", "op": "derive", "input": "source", "columns": {
            "constant": {"op": "literal", "value": 1, "operands": [{"column": "unused"}]}}}], ["constant"])
        self.assertEqual("passed", validate(plan)["status"])


class JoinAndRuntimeParity(unittest.TestCase):
    def test_join_column_inference_matches_the_trusted_runtime(self):
        runtime = load_runtime(SOURCE_ROOT)
        cases = [(["id", "value"], ["id", "value"], {"on": ["id"]}),
                 (["a"], ["b", "a"], {"left_on": ["a"], "right_on": ["b"]}),
                 (["a", "b"], ["a", "b"], {"left_on": ["a", "b"], "right_on": ["b", "a"]}),
                 (["id", "value"], ["id", "value"], {"on": ["id"], "suffixes": [None, "_right"]}),
                 (["id", "value"], ["id", "value"], {"on": ["id"], "suffixes": ["_left", "_right"]})]
        for left, right, keys in cases:
            with self.subTest(keys=keys):
                step = dict(id="joined", op="join", left="source", right="right", **keys)
                frames = {"source": pd.DataFrame([{name: 1 for name in left}]), "right": pd.DataFrame([{name: 1 for name in right}])}
                actual = runtime._run_step(frames, step, {}, {})
                plan = simple_plan(left, [step], list(actual.columns), {"right": {"kind": "injected", "columns": right}})
                self.assertEqual("passed", validate(plan)["status"], validate(plan))
                plan[0]["outputs"]["result"]["columns"] = ["missing_output"]
                plan[1][0]["final_columns"] = ["missing_output"]
                self.assertEqual("failed", validate(plan)["status"])

    def test_invalid_join_suffixes_and_result_collisions_are_rejected(self):
        for suffixes, left in ((["only"], ["id", "value"]), ([None, None], ["id", "value"]),
                               (["_x", "_y"], ["id", "value", "value_x"])):
            with self.subTest(suffixes=suffixes):
                plan = simple_plan(left, [{"id": "joined", "op": "join", "left": "source", "right": "right", "on": ["id"], "suffixes": suffixes}],
                    ["id"], {"right": {"kind": "injected", "columns": ["id", "value"]}})
                self.assertEqual("failed", validate(plan)["status"])

    def test_complete_fixture_preserves_runtime_values_and_column_order(self):
        runtime = load_runtime(SOURCE_ROOT)
        plan = fixture_plan("standard_report")
        before = copy.deepcopy(plan)
        frames = {"orders": pd.DataFrame([
            {"store_code": "S1", "period": "P01", "amount": 10, "quantity": 2, "status": "valid"},
            {"store_code": "S2", "period": "P01", "amount": 5, "quantity": 3, "status": "valid"}]),
            "stores": pd.DataFrame([{"store_code": "S1", "region": "East"}, {"store_code": "S2", "region": "East"}])}
        self.assertEqual("passed", validate_execution_contract(plan["execution_contract"], plan["outputs"])["status"])
        output = runtime.execute_contract(frames, {"period": "P01"}, {}, plan["execution_contract"])["region_sales"]
        self.assertEqual(["region", "period", "revenue", "store_count", "avg_revenue"], list(output.columns))
        self.assertEqual([["East", "P01", 35, 2, 17.5]], output.values.tolist())
        self.assertEqual(before, plan)


class CodegenGateway(unittest.TestCase):
    def facts(self):
        facts = structured_facts()
        confirm_code_unit_plan(facts, {"units": [
            {"code_unit_id": "daily_unit", "covered_waterlines": ["daily"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
            {"code_unit_id": "period_unit", "covered_waterlines": ["period"], "codegen_route": "report-codegen", "component_kind": "standard_report"}]}, timestamp="2026-10-30T00:00:00+00:00")
        return facts

    def test_invalid_field_blocks_only_the_affected_codegen_plan(self):
        facts = self.facts()
        facts["code_units"][0]["execution_contract"]["steps"][0]["conditions"][0]["column"] = "unknown_period"
        before = copy.deepcopy(facts)
        bad = build_plan(facts, "daily_unit")
        good = build_plan(facts, "period_unit")
        self.assertFalse(bad["summary"]["ready_for_codegen"])
        self.assertEqual("failed", bad["execution_validation"]["status"])
        self.assertTrue(good["summary"]["ready_for_codegen"])
        self.assertEqual(before, facts)

    def test_scaffold_refuses_an_invalid_execution_plan(self):
        import json
        facts = self.facts()
        facts["code_units"][0]["execution_contract"]["steps"][0]["conditions"][0]["column"] = "unknown_period"
        plan = build_plan(facts, "daily_unit")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises((ValueError, RuntimeError, SystemExit)):
                scaffold(path, root / "project")


class EvaluationBaseline(unittest.TestCase):
    def driver(self):
        return EVALUATION_TOOLS / "evaluate_report_samples.py"

    def test_changed_or_escaping_corpus_members_are_rejected(self):
        spec = importlib.util.spec_from_file_location("round6_evaluation_driver", self.driver())
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "corpus"
            root.mkdir()
            path = root / "sample.json"
            path.write_bytes(b"fixture")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(path, module.checked_file(root, "sample.json", digest))
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                module.checked_file(root, "sample.json", digest)
            outside = root.parent / "outside.json"
            outside.write_bytes(b"fixture")
            with self.assertRaises(ValueError):
                module.checked_file(root, "../outside.json", digest)
            with patch.object(sys, "argv", [str(self.driver()), "--corpus", str(root), "--out", str(root / "results")]):
                with self.assertRaisesRegex(ValueError, "outside the frozen corpus"):
                    module.main()

    def test_document_corpus_replays_without_promoting_business_approval(self):
        import json
        from verify_docx_bundle_multidoc import make_docx, make_xlsx
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / "corpus"
            corpus.mkdir()
            source = make_xlsx(root / "source.xlsx", [["位置", "数据表名", "数据表", "取数范围", "字段"],
                ["HBase", "source label", "fixture.source", "declared range", "id,value"]])
            fields = make_xlsx(root / "fields.xlsx", [["字段key", "字段名称", "来源字段", "计算逻辑"],
                ["id", "identifier", "id", "unverified rule"], ["value", "value label", "value", "unverified rule"]])
            path = corpus / "input.docx"
            make_docx(path, "Deidentified structural fixture", [source, fields], [[
                ["Description", "Data Storage", "Database", "Table Name"], ["output", "ClickHouse", "fixture", "output"]]])
            expected = {"sources": [{"location": "fixture.source", "storage": "hbase", "identity_status": "confirmed"}],
                        "targets": [{"location": "fixture.output", "storage": "clickhouse"}],
                        "field_keys": ["id", "value"], "source_fields": ["id", "value"]}
            oracle = corpus / "expected.json"
            oracle.write_text(json.dumps(expected), encoding="utf-8")
            manifest = {"version": 1, "business_formula_gold_status": "not_human_approved", "cases": [{"id": "candidate",
                "input": "input.docx", "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "expected": "expected.json", "expected_sha256": hashlib.sha256(oracle.read_bytes()).hexdigest(),
                "oracle_status": "document_structure_verified", "human_business_approved": False}]}
            (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "evaluation"
            result = subprocess.run([sys.executable, "-B", str(self.driver()), "--corpus", str(corpus), "--out", str(output),
                "--source-root", str(SOURCE_ROOT)], capture_output=True, text=True, encoding="utf-8", check=False)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            report = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", report["status"])
            self.assertFalse(report["cases"][0]["human_business_approved"])
            self.assertEqual("not_human_approved", report["business_formula_gold_status"])
