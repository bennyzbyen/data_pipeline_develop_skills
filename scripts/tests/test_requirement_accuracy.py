#!/usr/bin/env python3
"""Offline positive, negative and ambiguous cases for requirement accuracy."""

from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

DOC_SCRIPTS = SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"
sys.path.insert(0, str(DOC_SCRIPTS))

from docx_bundle_facts import (
    _detect_field_rule_conflicts, _map_report_field_dictionaries,
    _match_report_targets_to_physical_tables, hbase_targets_from_paragraphs,
    report_targets_from_paragraphs,
)
from docx_bundle_ooxml import Paragraph
from technical_contract import build_contract_v2, source_location, validate_contract
from verify_docx_bundle_multidoc import make_docx, make_xlsx
from verify_technical_contract_regression import complete_facts

BASE = {"project_type": "report", "component_kind": "standard_report", "ready_for_codegen": True, "blockers": []}


def bind(declared, locations, *, logical=False, pending=False):
    facts = {"report_targets": [{"target_name": "clickhouse_orders"}] if logical else [],
             "report_physical_targets": [{"table": name, "table_name": name.rsplit(".", 1)[-1],
                                           "database": name.split(".")[0]} for name in locations],
             "report_field_mappings": [], "inferences": []}
    _match_report_targets_to_physical_tables(facts)
    _map_report_field_dictionaries(facts, [{"csv": "fields.csv", "declared_table": declared,
                                           "requires_confirmation": pending,
                                           "fields": [{"target_field": "id", "source_field": "id"}]}])
    return facts, facts["report_field_mappings"][0]


class TargetBinding(unittest.TestCase):
    def test_qualified_name_wins_in_both_orders(self):
        for names in (["qa.orders", "prod.orders"], ["prod.orders", "qa.orders"]):
            with self.subTest(names=names):
                _, item = bind("prod.orders", names)
                self.assertEqual("prod.orders", item.get("inferred_physical_table"))
                self.assertFalse(item["requires_confirmation"])

    def test_missing_qualified_name_never_falls_back_to_another_database(self):
        _, item = bind("missing.orders", ["qa.orders", "prod.orders"])
        self.assertTrue(item["requires_confirmation"])
        self.assertFalse(item.get("inferred_physical_table"))

    def test_short_name_ambiguity_is_not_confirmed(self):
        for logical in (False, True):
            with self.subTest(logical=logical):
                facts, item = bind("orders", ["qa.orders", "prod.orders"], logical=logical)
                self.assertTrue(item["requires_confirmation"])
                self.assertFalse(item.get("inferred_physical_table"))
                if logical:
                    self.assertTrue(facts["report_targets"][0]["requires_confirmation"])

    def test_unique_logical_alias_and_duplicate_evidence_remain_valid(self):
        for names, logical in ((["fixture.orders"], False), (["fixture.orders"], True),
                               (["fixture.orders", "fixture.orders"], False)):
            with self.subTest(names=names, logical=logical):
                _, item = bind("orders", names, logical=logical)
                self.assertEqual("fixture.orders", item.get("inferred_physical_table"))
                self.assertFalse(item["requires_confirmation"])

    def test_order_only_and_previously_pending_bindings_stay_pending(self):
        for declared, pending in (("", False), ("fixture.orders", True)):
            with self.subTest(declared=declared):
                _, item = bind(declared, ["fixture.orders"], pending=pending)
                self.assertTrue(item["requires_confirmation"])

    def test_physical_table_prefix_is_not_removed_as_a_logical_alias(self):
        _, item = bind("orders", ["fixture.clickhouse_orders"])
        self.assertTrue(item["requires_confirmation"])
        self.assertFalse(item.get("inferred_physical_table"))

    def test_rule_conflicts_respect_database_and_real_disagreement(self):
        for target, expression, count in (("prod.orders", "value * 3", 0),
                                          ("qa.orders", "value * 3", 1),
                                          ("qa.orders", "value * 2", 0)):
            with self.subTest(target=target, expression=expression):
                facts = {"conflicts": [], "report_field_mappings": [
                    {"inferred_physical_table": "qa.orders", "fields": [{"target_field": "amount", "calculation_logic": "value * 2"}]},
                    {"inferred_physical_table": target, "fields": [{"target_field": "amount", "calculation_logic": expression}]},
                ]}
                _detect_field_rule_conflicts(facts)
                self.assertEqual(count, len(facts["conflicts"]))

    def test_waterline_evidence_does_not_mix_same_named_database_targets(self):
        from code_unit_evidence import _target_records
        facts = {"report_targets": [], "report_physical_targets": [], "report_field_mappings": []}
        for database in ("qa", "prod"):
            facts["report_targets"].append({"target_name": database + "_orders", "physical_table": database + ".orders"})
            facts["report_field_mappings"].append({"inferred_target_name": "orders", "inferred_physical_table": database + ".orders",
                                                   "fields": [{"target_field": database + "_id"}]})
        records = _target_records(facts)
        self.assertEqual(["qa_id"], [field["target_field"] for mapping in records[0]["field_mappings"] for field in mapping["fields"]])
        self.assertEqual(["prod_id"], [field["target_field"] for mapping in records[1]["field_mappings"] for field in mapping["fields"]])

    def test_report_unit_target_filter_respects_its_write_namespace(self):
        sys.path.insert(0, str(SOURCE_ROOT / "skills/report-codegen/scripts"))
        from build_report_codegen_plan import _contract_output_names, _matches_selected_target
        names = _contract_output_names({"outputs": {"orders": {}}, "writes": {"orders": {"table": "prod.orders"}}}, None)
        self.assertIn("prod.orders", names)
        self.assertFalse(_matches_selected_target({"table": "qa.orders", "target_name": "orders"}, names))
        self.assertTrue(_matches_selected_target({"table": "prod.orders", "target_name": "orders"}, names))


class ParagraphRoles(unittest.TestCase):
    def test_source_sections_and_versions_are_not_targets(self):
        for paragraphs in (
            [Paragraph("Heading2", "Data Source"), Paragraph("", "ClickHouse"), Paragraph("", "fixture.source")],
            [Paragraph("", "ClickHouse version"), Paragraph("", "23.8.1")],
            [Paragraph("Heading2", "示例"), Paragraph("", "ClickHouse"), Paragraph("", "fixture.example")],
            [Paragraph("", "ClickHouse"), Paragraph("CodeBlock", "fixture.example")],
        ):
            with self.subTest(paragraphs=[p.text for p in paragraphs]):
                self.assertEqual([], report_targets_from_paragraphs(paragraphs))

    def test_target_sections_and_legacy_flat_layout_remain_supported(self):
        for prefix in ([], [Paragraph("Heading2", "Data Target")]):
            paragraphs = prefix + [Paragraph("", "ClickHouse"), Paragraph("", "fixture.output"), Paragraph("", "Output table")]
            self.assertEqual(["fixture.output"], [item["table"] for item in report_targets_from_paragraphs(paragraphs)])

    def test_context_resets_at_document_and_section_boundaries(self):
        paragraphs = [Paragraph("Heading2", "Data Source", 1, "source.docx"),
                      Paragraph("", "ClickHouse", 2, "target.docx"),
                      Paragraph("", "fixture.output", 2, "target.docx")]
        self.assertEqual(["fixture.output"], [item["table"] for item in report_targets_from_paragraphs(paragraphs)])
        paragraphs = [Paragraph("Heading2", "Data Target", 1, "one.docx"),
                      Paragraph("Heading2", "Data Source", 2, "two.docx"),
                      Paragraph("", "HBase", 2, "two.docx"),
                      Paragraph("", "fixture.source", 2, "two.docx")]
        self.assertEqual([], hbase_targets_from_paragraphs(paragraphs))

    def test_code_examples_do_not_change_the_surrounding_target_section(self):
        paragraphs = [Paragraph("Heading2", "Data Target"), Paragraph("CodeBlock", "Data Source"),
                      Paragraph("", "ClickHouse"), Paragraph("", "fixture.output")]
        self.assertEqual(["fixture.output"], [item["table"] for item in report_targets_from_paragraphs(paragraphs)])


class ContractReferences(unittest.TestCase):
    def test_explicit_source_location_wins_description(self):
        self.assertEqual(("fixture.orders", "confirmed"),
                         source_location({"description": "daily_orders", "table_or_path": "fixture.orders"}))

    def test_conflicting_explicit_locations_block_codegen(self):
        facts = complete_facts()
        facts["report_sources"][0].update(physical_table="qa.source", table_or_path="prod.source")
        contract = build_contract_v2(facts, BASE)
        self.assertFalse(contract["ready_for_codegen"])
        self.assertIn("SOURCE_LOCATION_CONFLICT", {item["code"] for item in contract["validation_result"]["errors"]})

    def test_undeclared_source_and_unselected_column_block_codegen(self):
        for key, value, code in (("source_table", "fixture.undeclared", "FIELD_SOURCE_UNDECLARED"),
                                 ("source_field", "unselected", "FIELD_SOURCE_COLUMN_UNDECLARED")):
            with self.subTest(key=key):
                facts = complete_facts()
                facts["report_field_mappings"][0]["fields"][0][key] = value
                contract = build_contract_v2(facts, BASE)
                self.assertFalse(contract["ready_for_codegen"])
                self.assertIn(code, {item["code"] for item in contract["validation_result"]["errors"]})

    def test_valid_constants_and_declared_multisource_expressions_remain_valid(self):
        for expression in ("42", "source.value * lookup.factor"):
            with self.subTest(expression=expression):
                facts = complete_facts()
                facts["report_field_mappings"][0]["fields"][0].update(source_table="", source_field="", calculation_logic=expression)
                facts["report_sources"].append({"storage": "injected", "table_or_path": "lookup", "fields": ["factor"], "range": "injected"})
                contract = build_contract_v2(facts, BASE)
                self.assertTrue(contract["ready_for_codegen"], contract["validation_result"])

    def test_unknown_column_inventory_is_not_a_nonexistent_field_claim(self):
        facts = complete_facts()
        facts["report_sources"][0]["fields"] = []
        contract = build_contract_v2(facts, BASE)
        self.assertEqual([], contract["validation_result"]["errors"])
        self.assertIn("FIELD_SOURCE_COLUMNS_UNVERIFIED", {item["code"] for item in contract["validation_result"]["warnings"]})

    def test_legacy_and_deployment_only_gaps_keep_existing_semantics(self):
        self.assertEqual("passed", validate_contract({"contract_version": 1})["status"])
        facts = complete_facts()
        facts["report_sources"][0]["range"] = ""
        contract = build_contract_v2(facts, BASE)
        self.assertTrue(contract["ready_for_codegen"])
        self.assertEqual("review_required", contract["validation_result"]["deployment_status"])

    def test_duplicate_identical_source_evidence_does_not_create_ambiguity(self):
        facts = complete_facts()
        duplicate = copy.deepcopy(facts["report_sources"][0])
        duplicate["source_doc_name"] = "supplement.docx"
        facts["report_sources"].append(duplicate)
        contract = build_contract_v2(facts, BASE)
        self.assertTrue(contract["ready_for_codegen"], contract["validation_result"])

    def test_bad_reference_blocks_only_its_confirmed_code_unit(self):
        sys.path.insert(0, str(SOURCE_ROOT / "skills/pipeline-forge-guide/scripts"))
        from verify_multi_code_unit_delivery import structured_facts
        from code_unit_contract import confirm_code_unit_plan
        facts = structured_facts()
        for index, source_field in enumerate(("amount", "unselected")):
            facts["report_field_mappings"][index]["fields"][0].update(
                source_table="orders", source_field=source_field)
        facts["codegen_contract"] = build_contract_v2(facts, facts["codegen_contract"])
        confirm_code_unit_plan(facts, {"units": [
            {"code_unit_id": "daily_unit", "covered_waterlines": ["daily"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
            {"code_unit_id": "period_unit", "covered_waterlines": ["period"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
        ]}, timestamp="2026-10-29T00:00:00+00:00")
        units = {unit["code_unit_id"]: unit for unit in facts["code_units"]}
        self.assertTrue(units["daily_unit"]["readiness"]["ready_for_codegen"])
        self.assertFalse(units["period_unit"]["readiness"]["ready_for_codegen"])
        self.assertTrue(any("unselected" in item for item in units["period_unit"]["blockers"]))


class ExtractionHandoff(unittest.TestCase):
    def test_cross_database_docx_maps_declared_target_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fields = make_xlsx(root / "fields.xlsx", [
                ["数据表：prod.orders", "", "", "", "", ""],
                ["字段key", "字段名称", "数据源位置", "数据表", "来源字段", "计算逻辑"],
                ["id", "编号", "HBase", "fixture.source", "id", "copy"],
            ])
            targets = [["Description", "Data Storage", "Database", "Table Name"],
                       ["QA", "ClickHouse", "qa", "orders"], ["PROD", "ClickHouse", "prod", "orders"]]
            docx = root / "requirement.docx"
            make_docx(docx, "Synthetic cross-database binding", [fields], [targets])
            completed = subprocess.run([sys.executable, "-B", str(DOC_SCRIPTS / "extract_docx_bundle.py"),
                                        "--docx", str(docx), "--out", str(root / "delivery")],
                                       capture_output=True, text=True, encoding="utf-8", check=False)
            self.assertEqual(0, completed.returncode, completed.stderr)
            facts = json.loads((root / "delivery/dev_doc/structured_facts.json").read_text(encoding="utf-8"))
            mapping = facts["report_field_mappings"][0]
            self.assertEqual("prod.orders", mapping["inferred_physical_table"])
            self.assertFalse(mapping["requires_confirmation"])
            self.assertEqual("prod.orders", facts["codegen_contract"]["field_contracts"][0]["target"])
            # Exercise the legacy plan gateway without bypassing v3 confirmation.
            # The separate unit test above covers confirmed v3 scope isolation.
            legacy = copy.deepcopy(facts)
            for key in ("project_contract", "code_unit_plan", "code_units"):
                legacy.pop(key, None)
            legacy_path = root / "legacy.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            script = SOURCE_ROOT / "skills/report-codegen/scripts/build_report_codegen_plan.py"
            planned = subprocess.run([sys.executable, "-B", str(script), "--facts", str(legacy_path),
                                      "--out", str(root / "plan")], capture_output=True, text=True,
                                     encoding="utf-8", check=False)
            self.assertEqual(0, planned.returncode, planned.stderr)
            plan = json.loads((root / "plan/report_codegen_plan.json").read_text(encoding="utf-8"))
            self.assertEqual("prod.orders", plan["outputs"][0]["physical_table"])
