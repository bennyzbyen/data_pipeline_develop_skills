#!/usr/bin/env python3
"""Evidence conversion mutations and complex arithmetic on trusted offline templates."""
from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT, EVALUATION_TOOLS, load_runtime

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORT = SOURCE_ROOT / "skills/report-codegen"
sys.path[:0] = [str(ROOT / "skills/report-codegen/scripts"), str(SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts")]
sys.path.insert(0, str(EVALUATION_TOOLS))
from requirement_conversion import evidence_digest, validate_conversion
import report_sample_workflow as workflow
from evaluate_report_samples import checked_file


def fixture(grouped=False):
    fields = [{"target_field": name, "field_name": name, "source_field": name if name != "result" else "",
               "source_desc": "document", "source_table": "", "field_type": "",
               "calculation_logic": "amount / target; zero or missing target returns null" if name == "result" else "copy"}
              for name in ("amount", "target", "result")]
    expression = {"op": "divide", "operands": [{"column": "amount"}, {"column": "target"}]}
    steps = [{"id": "calculated", "input": "input", "op": "derive", "columns": {"result": expression}},
             {"id": "projected", "input": "calculated", "op": "project", "columns": ["result"]}]
    columns = ["amount", "target"]
    output = ["result"]
    data = [{"amount": 9, "target": 3}, {"amount": 1, "target": 0}, {"amount": 5, "target": None}]
    rows = [[3.0], [None], [None]]
    if grouped:
        columns = ["store", "day", "status", "amount"]
        output = ["store", "result"]
        conditions = [{"column": "day", "operator": "ge", "value_from": "params.start"},
                      {"column": "day", "operator": "lt", "value_from": "params.end"},
                      {"column": "status", "operator": "not_in", "value": ["cancelled", "rejected"]}]
        steps = [{"id": "filtered", "input": "input", "op": "filter", "conditions": conditions},
                 {"id": "total", "input": "filtered", "op": "aggregate", "group_by": ["store"],
                  "aggregations": {"result": {"column": "amount", "agg": "sum"}}},
                 {"id": "projected", "input": "total", "op": "project", "columns": output}]
        data = [{"store": "A", "day": "2024-01-01", "status": "ok", "amount": 2},
                {"store": "A", "day": "2024-01-31", "status": "ok", "amount": 3}]
        rows = [["A", 5]]
        fields[0]["target_field"] = fields[0]["field_name"] = "store"
        fields[2]["calculation_logic"] = "sum amount by store in [start,end), excluding cancelled and rejected"
    contract = {"version": 1, "sources": {"input": {"kind": "injected", "columns": columns}}, "steps": steps,
                "outputs": {"offline_result": {"input": "projected", "columns": output}},
                "writes": {"offline_result": {"kind": "clickhouse", "table": "fixture.result", "mode": "append"}}}
    params = {"current_date": "2024-02-01", "start": "2024-01-01", "end": "2024-02-01"}
    reference = {"document_sha256": ["a" * 64], "business_approved": False, "full_report_ready": False,
                 "evidence": {field["target_field"]: evidence_digest(field) for field in fields},
                 "rules": [{"id": "RULE-total", "target_field": "result", "outcome": "fragment"}],
                 "pending_ids": ["BUSINESS_APPROVAL", "UPSTREAM_BINDING"], "output_fields": output,
                 "fixture_inputs": {"source_data": {"input": data}, "params": params},
                 "contract_checks": [{"path": ["sources", "input", "columns"], "equals": columns},
                                     {"path": ["outputs", "offline_result", "columns"], "equals": output}]}
    for index, step in enumerate(steps):
        for key, value in step.items():
            if key not in {"id", "input"}:
                reference["contract_checks"].append({"path": ["steps", index, key],
                    "unordered_equals" if key == "conditions" else "equals": copy.deepcopy(value)})
    candidate = {"version": 1, "kind": "document_rule_candidate", "fixture_only": True,
                 "candidate_origin": "assistant_session_candidate", "document_sha256": ["a" * 64],
                 "business_approved": False, "full_report_ready": False,
                 "bindings": [{"target_field": name, "evidence_sha256": digest} for name, digest in reference["evidence"].items()],
                 "rules": copy.deepcopy(reference["rules"]), "pending_ids": list(reference["pending_ids"]),
                 "output_fields": list(output), "execution_contract": contract,
                 "source_data": copy.deepcopy(reference["fixture_inputs"]["source_data"]), "params": dict(params)}
    oracle = {"columns": output, "rows": rows, "write_events": [{"table": "fixture.result", "rows": len(rows), "columns": output}]}
    return fields, candidate, reference, oracle


def pending_fixture():
    fields, candidate, reference, _ = fixture()
    reference["rules"][0]["outcome"] = "pending"
    reference.update(output_fields=[], contract_checks=[], pending_spec={"input_field": "amount", "round_digits": 2,
        "tiers": [{"min": 20, "min_inclusive": True}, {"min": 10, "min_inclusive": True, "max": 20, "max_inclusive": False}]})
    reference.pop("fixture_inputs")
    for key in ("execution_contract", "source_data", "params"):
        candidate.pop(key)
    candidate.update(output_fields=[], rules=copy.deepcopy(reference["rules"]), pending_spec=copy.deepcopy(reference["pending_spec"]))
    return fields, candidate, reference


class ConversionAudit(unittest.TestCase):
    def rejected(self, fields, candidate, reference, message):
        before = copy.deepcopy((fields, candidate, reference))
        result = validate_conversion(fields, candidate, reference)
        self.assertEqual("failed", result["status"], result)
        self.assertTrue(any(message in error for error in result["errors"]), result)
        self.assertEqual(before, (fields, candidate, reference))

    def test_valid_fragment_keeps_dependencies_and_never_approves_report(self):
        fields, candidate, reference, _ = fixture()
        before = copy.deepcopy((fields, candidate, reference))
        result = validate_conversion(fields, candidate, reference)
        self.assertEqual("passed", result["status"], result)
        self.assertFalse(result["business_approved"])
        self.assertFalse(result["full_report_ready"])
        self.assertEqual(before, (fields, candidate, reference))

    def test_actual_field_logic_or_identity_changes_are_detected(self):
        for key in ("calculation_logic", "source_field", "field_name", "source_table", "field_type"):
            with self.subTest(key=key):
                fields, candidate, reference, _ = fixture()
                fields[0][key] = "different evidence"
                self.rejected(fields, candidate, reference, "extracted field evidence")

    def test_layout_whitespace_does_not_change_evidence_identity(self):
        fields, candidate, reference, _ = fixture()
        fields[-1]["calculation_logic"] = fields[-1]["calculation_logic"].replace(" / ", "\n/\t")
        self.assertEqual("passed", validate_conversion(fields, candidate, reference)["status"])

    def test_wrong_document_or_binding_is_rejected(self):
        for key in ("document", "binding", "duplicate"):
            with self.subTest(key=key):
                fields, candidate, reference, _ = fixture()
                if key == "document":
                    candidate["document_sha256"] = ["b" * 64]
                elif key == "binding":
                    candidate["bindings"][0]["evidence_sha256"] = "b" * 64
                else:
                    candidate["bindings"].append(candidate["bindings"][0].copy())
                self.rejected(fields, candidate, reference, "evidence")

    def test_invented_readiness_defaults_or_rule_outcomes_are_rejected(self):
        for key, value, message in (("business_approved", True, "cannot approve"), ("full_report_ready", True, "cannot approve"),
                                    ("default_value", 0, "undeclared"), ("rules", [], "rule targets")):
            with self.subTest(key=key):
                fields, candidate, reference, _ = fixture()
                candidate[key] = value
                self.rejected(fields, candidate, reference, message)

    def test_pending_dependencies_cannot_be_dropped_or_duplicated(self):
        for duplicate in (False, True):
            fields, candidate, reference, _ = fixture()
            if duplicate:
                candidate["pending_ids"].append(candidate["pending_ids"][0])
            else:
                candidate["pending_ids"].pop()
            self.rejected(fields, candidate, reference, "every pending")

    def test_swapped_division_or_invented_null_fill_is_rejected(self):
        for change in ("swap", "fill"):
            fields, candidate, reference, _ = fixture()
            expression = candidate["execution_contract"]["steps"][0]["columns"]["result"]
            if change == "swap":
                expression["operands"].reverse()
            else:
                expression["fill_value"] = 0
            self.rejected(fields, candidate, reference, "steps.0.columns")

    def test_changed_fixture_rows_or_params_cannot_make_a_candidate_pass(self):
        for key in ("source_data", "params"):
            fields, candidate, reference, _ = fixture()
            candidate[key] = {}
            self.rejected(fields, candidate, reference, "fixture inputs")

    def test_boolean_is_not_a_numeric_literal_and_malformed_input_fails(self):
        fields, candidate, reference, _ = fixture()
        candidate["source_data"]["input"][1]["target"] = False
        self.rejected(fields, candidate, reference, "fixture inputs")
        for malformed in (None, [], {"bindings": None}):
            self.assertEqual("failed", validate_conversion(fields, malformed, reference)["status"])

    def test_extra_step_or_unaudited_property_is_rejected(self):
        for extra in (False, True):
            fields, candidate, reference, _ = fixture()
            if extra:
                candidate["execution_contract"]["steps"].append({"id": "hidden", "op": "project", "input": "projected", "columns": ["result"]})
                message = "step count"
            else:
                candidate["execution_contract"]["steps"][0]["default"] = 0
                message = "unaudited"
            self.rejected(fields, candidate, reference, message)

    def test_missing_filter_or_wrong_boundary_rejected_even_when_sample_rows_match(self):
        for change in ("drop", "boundary"):
            fields, candidate, reference, _ = fixture(grouped=True)
            conditions = candidate["execution_contract"]["steps"][0]["conditions"]
            if change == "drop":
                conditions.pop()
            else:
                conditions[1]["operator"] = "le"
            self.rejected(fields, candidate, reference, "conditions")

    def test_condition_order_can_change_without_changing_meaning(self):
        fields, candidate, reference, _ = fixture(grouped=True)
        candidate["execution_contract"]["steps"][0]["conditions"].reverse()
        self.assertEqual("passed", validate_conversion(fields, candidate, reference)["status"])

    def test_filters_or_derived_steps_cannot_be_bypassed_by_routing(self):
        for skip in ("filter", "output"):
            fields, candidate, reference, _ = fixture(grouped=True)
            if skip == "filter":
                candidate["execution_contract"]["steps"][1]["input"] = "input"
            else:
                candidate["execution_contract"]["outputs"]["offline_result"]["input"] = "total"
            self.rejected(fields, candidate, reference, "bypasses")

    def test_consistent_step_renaming_keeps_the_same_rule_chain(self):
        fields, candidate, reference, _ = fixture()
        candidate["execution_contract"]["steps"][0]["id"] = "renamed_step"
        candidate["execution_contract"]["steps"][1]["input"] = "renamed_step"
        self.assertEqual("passed", validate_conversion(fields, candidate, reference)["status"])

    def test_sum_count_and_distinct_count_are_not_interchangeable(self):
        for aggregation in ("count", "nunique"):
            fields, candidate, reference, _ = fixture(grouped=True)
            candidate["execution_contract"]["steps"][1]["aggregations"]["result"]["agg"] = aggregation
            self.rejected(fields, candidate, reference, "aggregations")

    def test_pending_rounding_and_tier_boundaries_are_preserved(self):
        for change in ("round", "tier", "execute"):
            fields, candidate, reference = pending_fixture()
            if change == "round":
                candidate["pending_spec"]["round_digits"] = 0
            elif change == "tier":
                candidate["pending_spec"]["tiers"][1]["max_inclusive"] = True
            else:
                candidate["execution_contract"] = {}
            self.rejected(fields, candidate, reference, "pending")

    def test_rule_fixture_without_an_audit_cannot_be_normalized(self):
        fields, candidate, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "requires a passed"):
            workflow.fixture_facts(fields, candidate)

    def test_pending_rule_never_reaches_plan_scaffold_or_execution(self):
        fields, candidate, reference = pending_fixture()
        with tempfile.TemporaryDirectory() as temporary, patch("build_report_codegen_plan.build_plan") as plan, \
                patch("scaffold_report_project.scaffold") as scaffold, patch.object(workflow, "execute_generated") as execute:
            result = workflow.evaluate_workflow(fields, candidate, None, Path(temporary), "# Pending", reference)
            self.assertEqual("pending", result["status"], result)
            self.assertEqual({"conversion_audit"}, set(result["stage_seconds"]))
            self.assertFalse((Path(temporary) / "evaluation_handoff").exists())
            plan.assert_not_called()
            scaffold.assert_not_called()
            execute.assert_not_called()

    def test_invalid_conversion_stops_before_plan_and_missing_reference_fails(self):
        fields, candidate, reference, oracle = fixture()
        candidate["pending_ids"] = []
        for frozen in (reference, None):
            with tempfile.TemporaryDirectory() as temporary, patch("build_report_codegen_plan.build_plan") as plan:
                result = workflow.evaluate_workflow(fields, candidate, oracle, Path(temporary), "# Fixture", frozen)
                self.assertEqual("failed", result["status"], result)
                self.assertEqual("conversion_audit", result["failed_stage"])
                plan.assert_not_called()

    def test_fragment_replays_plan_generated_code_and_fake_write_payload(self):
        for grouped in (False, True):
            fields, candidate, reference, oracle = fixture(grouped)
            before = copy.deepcopy((fields, candidate, reference, oracle))
            with tempfile.TemporaryDirectory() as temporary:
                result = workflow.evaluate_workflow(fields, candidate, oracle, Path(temporary), "# Fixture", reference)
                self.assertEqual("passed", result["status"], result)
                self.assertTrue(result["checks"]["fake_write_rows"])
                self.assertFalse(result["business_approved"])
            self.assertEqual(before, (fields, candidate, reference, oracle))

    def test_pending_corpus_is_counted_separately_and_original_handoff_stays_blocked(self):
        from verify_docx_bundle_multidoc import make_docx, make_xlsx

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / "corpus"
            corpus.mkdir()
            field = {"target_field": "result", "field_name": "Average", "source_field": "", "source_desc": "",
                     "source_table": "", "field_type": "", "calculation_logic": "Round total / periods; version pending"}
            book = make_xlsx(root / "fields.xlsx", [["字段key", "字段名称", "计算逻辑"], ["result", "Average", field["calculation_logic"]]])
            path = corpus / "input.docx"
            make_docx(path, "Synthetic pending rule", [book], [])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            reference = {"document_sha256": [digest], "business_approved": False, "full_report_ready": False,
                         "evidence": {"result": evidence_digest(field)}, "rules": [{"id": "R1", "target_field": "result", "outcome": "pending"}],
                         "pending_ids": ["VERSION", "ROUNDING", "BUSINESS_APPROVAL"], "output_fields": [],
                         "contract_checks": [], "pending_spec": {"round_digits": 2, "version_selection": "pending"}}
            candidate = {key: copy.deepcopy(reference[key]) for key in ("document_sha256", "business_approved", "full_report_ready", "rules", "pending_ids", "output_fields", "pending_spec")}
            candidate.update(version=1, kind="document_rule_candidate", fixture_only=True, candidate_origin="assistant_session_candidate",
                             bindings=[{"target_field": "result", "evidence_sha256": evidence_digest(field)}])
            expected = {"sources": [], "targets": [], "fields": [field], "document_ready_for_codegen": False, "conversion": reference}
            case = {"id": "pending", "inputs": [{"path": "input.docx", "sha256": digest}],
                    "expected": "expected.json", "workflow": "candidate.json", "expected_document_outcome": "blocked"}
            for name, value, hash_key in (("expected.json", expected, "expected_sha256"), ("candidate.json", candidate, "workflow_sha256")):
                workflow.write_json(corpus / name, value)
                case[hash_key] = hashlib.sha256((corpus / name).read_bytes()).hexdigest()
            manifest = {"version": 2, "cases": [case]}
            self.assertEqual(0, workflow.evaluate_corpus(manifest, corpus, root / "out", checked_file))
            report = json.loads((root / "out/evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(1, report["workflow_evaluated"])
            self.assertEqual(1, report["workflow_pending"])
            self.assertEqual(1, report["workflow_not_executed"])
            self.assertEqual(0, report["workflow_executed"])
            self.assertEqual(0, report["workflow_passed"])
            self.assertTrue(report["cases"][0]["checks"]["original_handoff_unchanged"])
            self.assertTrue(report["cases"][0]["document_gate"]["blocked"])
            self.assertFalse((root / "out/pending/project").exists())
            # A valid hash must not let an oracle bind to a different document.
            expected["conversion"]["document_sha256"] = ["b" * 64]
            workflow.write_json(corpus / "expected.json", expected)
            case["expected_sha256"] = hashlib.sha256((corpus / "expected.json").read_bytes()).hexdigest()
            self.assertEqual(1, workflow.evaluate_corpus(manifest, corpus, root / "wrong_doc", checked_file))
            failure = json.loads((root / "wrong_doc/evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(1, failure["integrity_failures"])




class ComplexArithmetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = load_runtime(SOURCE_ROOT)

    def divide(self, numerator, denominator, fill=None, size=2):
        expression = {"op": "divide", "operands": [{"value": numerator}, {"value": denominator}]}
        if fill is not None:
            expression["fill_value"] = fill
        return self.runtime._expression(pd.DataFrame(index=range(size)), expression, {}, {})

    def test_literal_or_runtime_scalar_division_with_fill(self):
        self.assertEqual(2.5, self.divide(5, 2, fill=0))
        expression = {"op": "divide", "operands": [{"value_from": "params.a"}, {"value_from": "params.b"}], "fill_value": -1}
        self.assertEqual(2.5, self.runtime._expression(pd.DataFrame(index=[0]), expression, {}, {"a": 5, "b": 2}))

    def test_scalar_zero_or_missing_denominator_returns_missing(self):
        for denominator in (0, None, float("nan"), pd.NA):
            with self.subTest(denominator=repr(denominator)):
                self.assertTrue(pd.isna(self.divide(5, denominator)))

    def test_explicit_fill_handles_scalar_missing_results(self):
        for numerator, denominator in ((5, 0), (5, None), (5, pd.NA), (None, 2)):
            with self.subTest(pair=(repr(numerator), repr(denominator))):
                self.assertEqual(-1, self.divide(numerator, denominator, fill=-1))

    def test_series_with_scalar_missing_denominator_preserves_index_and_nulls(self):
        df = pd.DataFrame({"n": [1.0, None, -3.0]}, index=[4, 8, 12])
        for denominator in (0, None, pd.NA):
            with self.subTest(denominator=repr(denominator)):
                result = self.runtime._expression(df, {"op": "divide", "operands": [{"column": "n"}, {"value": denominator}]}, {}, {})
                self.assertEqual(list(df.index), list(result.index))
                self.assertTrue(result.isna().all())

    def test_vector_zero_null_and_negative_operands_and_empty_input(self):
        df = pd.DataFrame({"n": [4.0, None, -3.0, 1.0], "d": [2.0, 2.0, -2.0, 0.0]}, index=[2, 4, 6, 8])
        expression = {"op": "divide", "operands": [{"column": "n"}, {"column": "d"}]}
        original = df.copy(deep=True)
        result = self.runtime._expression(df, expression, {}, {})
        pd.testing.assert_series_equal(result, pd.Series([2.0, None, 1.5, None], index=df.index), check_names=False, check_dtype=False)
        empty = self.runtime._expression(df.iloc[:0], expression, {}, {})
        self.assertEqual(0, len(empty))
        pd.testing.assert_frame_equal(df, original)

    def test_existing_arithmetic_precedence_is_explicit_step_order(self):
        frames = {"input": pd.DataFrame({"n": [10, 20], "d": [2, 4], "discount": [1, 2]})}
        step = {"id": "derived", "op": "derive", "input": "input", "columns": {
            "net": {"op": "subtract", "operands": [{"column": "n"}, {"column": "discount"}]},
            "rate": {"op": "divide", "operands": [{"column": "net"}, {"column": "d"}]}}}
        actual = self.runtime._run_step(frames, step, {}, {})
        self.assertEqual([4.5, 4.5], actual["rate"].tolist())
        self.assertEqual([10, 20], frames["input"]["n"].tolist())
