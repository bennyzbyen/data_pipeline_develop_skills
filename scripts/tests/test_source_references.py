#!/usr/bin/env python3
"""Offline source-reference, extraction-completeness and lookup-cost regressions."""

from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT

import copy
import csv
import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path, PureWindowsPath


DOC = SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"
sys.path.insert(0, str(SOURCE_ROOT / "skills/pipeline-forge-guide/scripts"))
sys.path.insert(0, str(DOC))

from code_unit_contract import confirm_code_unit_plan, validate_code_unit_contract
from docx_bundle_contract import build_question_groups_v2
from docx_bundle_facts import _infer_sources_from_field_mappings, build_structured_facts
from docx_bundle_ooxml import Paragraph
from requirement_bundle_inputs import extract_document_to_dirs
from requirement_bundle_markdown import parse_markdown_evidence
from revise_confirmed_contract import fingerprint, revise
from technical_contract import build_contract_v2, build_source_contracts, validate_field_source_references
from verify_docx_bundle_multidoc import make_docx, make_xlsx
from verify_multi_code_unit_delivery import structured_facts
from verify_technical_contract_regression import complete_facts


BASE = {"contract_version": 1, "project_type": "report", "component_kind": "standard_report",
        "ready_for_codegen": True, "blockers": []}


def reference_contract(sources=None, table="fixture.source", column="value"):
    return {"source_contracts": sources if sources is not None else [
        {"id": "s1", "exact_location": "fixture.source", "logical_name": "current",
         "required_columns": ["business_date", "value"]}],
        "field_contracts": [{"target": "fixture.output", "target_field": "value",
                             "physical_source_table": table, "physical_source_field": column}]}


def codes(result):
    return {item["code"] for item in result}


def confirmed_units(facts):
    return confirm_code_unit_plan(facts, {"units": [
        {"code_unit_id": "daily_unit", "covered_waterlines": ["daily"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
        {"code_unit_id": "period_unit", "covered_waterlines": ["period"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
    ]}, timestamp="2026-10-30T00:00:00+00:00")


class SourceReferences(unittest.TestCase):
    def test_quoted_simple_identifiers_are_checked_against_inventory(self):
        for table, column in (("`fixture`.`source`", "`value`"), ('"fixture"."source"', '"value"'),
                              ("[fixture].[source]", "[value]")):
            with self.subTest(table=table):
                self.assertEqual(([], []), validate_field_source_references(reference_contract(table=table, column=column)))

    def test_quoted_undeclared_tables_and_columns_block_codegen(self):
        for key, value, expected in (("source_table", "`fixture`.`missing`", "FIELD_SOURCE_UNDECLARED"),
                                     ("source_field", "`missing`", "FIELD_SOURCE_COLUMN_UNDECLARED")):
            with self.subTest(key=key):
                facts = complete_facts()
                facts["report_field_mappings"][0]["fields"][1][key] = value
                result = build_contract_v2(facts, BASE)
                self.assertFalse(result["ready_for_codegen"])
                self.assertIn(expected, codes(result["validation_result"]["errors"]))

    def test_quoted_declarations_and_column_case_preserve_evidence(self):
        sources = [{"exact_location": "`fixture`.`source`", "logical_name": "current", "required_columns": ['"Value"']}]
        contract = reference_contract(sources, column="Value")
        before = copy.deepcopy(contract)
        self.assertEqual(([], []), validate_field_source_references(contract))
        contract["field_contracts"][0]["physical_source_field"] = "value"
        self.assertIn("FIELD_SOURCE_COLUMN_UNDECLARED", codes(validate_field_source_references(contract)[0]))
        self.assertEqual(before["source_contracts"], contract["source_contracts"])

    def test_string_and_list_column_forms_have_the_same_ordered_inventory(self):
        for value in ("business_date,value", ["business_date,value"], ["business_date; value"], ["business_date，value；"],
                      ["business_date\nvalue"], ["`business_date`", "value", "value"]):
            with self.subTest(value=value):
                facts = complete_facts()
                facts["report_sources"][0]["fields"] = value
                before = copy.deepcopy(facts)
                result = build_contract_v2(facts, BASE)
                self.assertTrue(result["ready_for_codegen"], result["validation_result"])
                self.assertEqual(["business_date", "value"], result["source_contracts"][0]["required_columns"])
                self.assertEqual(before, facts)

    def test_source_matrix_column_list_reaches_the_contract(self):
        text = "| 位置 | 数据表名 | 数据表 | 取数范围 | 字段 |\n| --- | --- | --- | --- | --- |\n| HBase | orders | fixture.source | business date | business_date,value |\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "source.md"
            path.write_text(text, encoding="utf-8")
            paragraphs, tables, _ = parse_markdown_evidence(path, root / "tables", 0, 1)
            facts = build_structured_facts(tables, paragraphs)
            self.assertEqual(["business_date", "value"], build_source_contracts(facts)[0]["required_columns"])

    def test_complex_expressions_are_preserved_as_unverified(self):
        facts = complete_facts()
        facts["report_sources"][0]["fields"] = ["coalesce(a,b)", "a + b"]
        self.assertEqual(["coalesce(a,b)", "a + b"], build_source_contracts(facts)[0]["required_columns"])
        for table, column, expected in (("fixture.source", "coalesce(a,b)", "FIELD_SOURCE_COLUMN_EXPRESSION_UNVERIFIED"),
                                        ("fixture.source, fixture.other", "value", "FIELD_SOURCE_REFERENCE_UNVERIFIED")):
            errors, warnings = validate_field_source_references(reference_contract(table=table, column=column))
            self.assertFalse(errors)
            self.assertIn(expected, codes(warnings))
        errors, warnings = validate_field_source_references(reference_contract([
            {"exact_location": "fixture.source", "required_columns": []}]))
        self.assertFalse(errors)
        self.assertIn("FIELD_SOURCE_COLUMNS_UNVERIFIED", codes(warnings))

    def test_storage_spelling_does_not_shadow_authoritative_inventory(self):
        for field_name, expected_ready in (("value", True), ("missing", False)):
            with self.subTest(field_name=field_name):
                facts = complete_facts()
                for field in facts["report_field_mappings"][0]["fields"]:
                    field["source_storage"] = "hbase"
                facts["report_field_mappings"][0]["fields"][1]["source_field"] = field_name
                explicit = copy.deepcopy(facts["report_sources"][0])
                _infer_sources_from_field_mappings(facts)
                self.assertEqual([explicit], facts["report_sources"])
                before = copy.deepcopy(facts)
                _infer_sources_from_field_mappings(facts)
                self.assertEqual(before, facts)
                result = build_contract_v2(facts, BASE)
                self.assertEqual(expected_ready, result["ready_for_codegen"])
                if not expected_ready:
                    self.assertIn("FIELD_SOURCE_COLUMN_UNDECLARED", codes(result["validation_result"]["errors"]))

    def test_storage_boundaries_remain_distinct(self):
        facts = {"report_sources": [], "report_field_mappings": [{"fields": [
            {"source_storage": storage, "source_table": "fixture.source", "source_field": field}
            for storage, field in (("HBase", "id"), ("hbase", "value"), ("FS", "file_id"))]}]}
        _infer_sources_from_field_mappings(facts)
        self.assertEqual(2, len(facts["report_sources"]))
        self.assertEqual(["id", "value"], facts["report_sources"][0]["fields"])
        self.assertEqual(["file_id"], facts["report_sources"][1]["fields"])

    def test_exact_physical_name_precedes_a_colliding_logical_alias(self):
        sources = [{"exact_location": "fixture.source", "logical_name": "current", "required_columns": ["value"]},
                   {"exact_location": "fixture.backup", "logical_name": "fixture.source", "required_columns": ["backup"]}]
        for ordered in (sources, sources[::-1]):
            self.assertEqual(([], []), validate_field_source_references(reference_contract(ordered)))

    def test_duplicate_evidence_and_real_conflicts_remain_distinguishable(self):
        contract = reference_contract()
        duplicate = dict(contract["source_contracts"][0], id="s2", provenance={"document": "supplement"})
        contract["source_contracts"].append(duplicate)
        self.assertEqual(([], []), validate_field_source_references(contract))
        duplicate["required_columns"] = ["other"]
        self.assertIn("FIELD_SOURCE_AMBIGUOUS", codes(validate_field_source_references(contract)[0]))

    def test_short_names_bind_only_when_unique(self):
        contract = reference_contract(table="source")
        self.assertEqual(([], []), validate_field_source_references(contract))
        contract["source_contracts"].append({"exact_location": "another.source", "required_columns": ["value"]})
        self.assertIn("FIELD_SOURCE_AMBIGUOUS", codes(validate_field_source_references(contract)[0]))

    def test_file_paths_are_not_case_folded_or_matched_by_basename(self):
        windows = PureWindowsPath("X:/")
        for actual, reference in (("/Fixture/Orders.csv", "/fixture/orders.csv"),
                                  ("fs://fixture/Orders.csv", "fs://fixture/orders.csv"),
                                  (str(windows / "Fixture" / "Orders.csv"), str(windows / "fixture" / "orders.csv"))):
            with self.subTest(actual=actual):
                sources = [{"exact_location": actual, "storage_kind": "fs", "required_columns": ["value"]}]
                self.assertEqual(([], []), validate_field_source_references(reference_contract(sources, table=actual)))
                self.assertIn("FIELD_SOURCE_UNDECLARED", codes(validate_field_source_references(reference_contract(sources, table=reference))[0]))
                self.assertIn("FIELD_SOURCE_UNDECLARED", codes(validate_field_source_references(reference_contract(sources, table="Orders.csv"))[0]))

    def test_explicit_fs_storage_and_uri_have_a_confirmed_location(self):
        for storage, location in (("FS", "fs://fixture/Orders.csv"), ("GatewayFS", "gateway://fixture/Orders.csv"),
                                  ("DataHub_FS", "/fixture/hbase_history.csv"), ("FS", str(PureWindowsPath("X:/") / "Fixture" / "Orders.csv"))):
            with self.subTest(storage=storage):
                source = build_source_contracts({"report_sources": [{"storage": storage, "table_or_path": location}]})[0]
                self.assertEqual("fs", source["storage_kind"])
                self.assertEqual("confirmed", source["location_status"])
                self.assertEqual(location, source["exact_location"])
                self.assertEqual(location, source["range_contract"]["file_path"])

    def test_file_path_spacing_is_preserved_through_contract_building(self):
        facts = complete_facts()
        location = "fs://fixture/order  exports/Orders.csv"
        facts["report_sources"][0].update(storage="FS", table_or_path=location)
        for field in facts["report_field_mappings"][0]["fields"]:
            field["source_table"] = location
        result = build_contract_v2(facts, BASE)
        self.assertTrue(result["ready_for_codegen"], result["validation_result"])
        self.assertEqual(location, result["field_contracts"][0]["physical_source_table"])
        self.assertEqual(location, result["source_contracts"][0]["exact_location"])

    def test_bare_file_uri_is_not_a_confirmed_location(self):
        for uri in ("fs://", "gateway://"):
            source = build_source_contracts({"report_sources": [{"storage": "FS", "table_or_path": uri}]})[0]
            self.assertNotEqual("confirmed", source["location_status"])

    def test_explicit_location_conflicts_respect_paths_and_identifier_quotes(self):
        sources = build_source_contracts({"report_sources": [
            {"storage": "FS", "path": "/Fixture/Orders.csv", "table_or_path": "/fixture/orders.csv"},
            {"storage": "HBase", "physical_table": "fixture.source", "table_or_path": "`fixture`.`source`"}]})
        self.assertEqual(2, len(sources[0]["location_candidates"]))
        self.assertEqual("needs_confirmation", sources[0]["location_status"])
        self.assertNotIn("location_candidates", sources[1])

    def test_new_validation_observes_mutated_source_inventory(self):
        contract = reference_contract()
        self.assertEqual(([], []), validate_field_source_references(contract))
        contract["source_contracts"][0]["required_columns"] = ["other"]
        before = copy.deepcopy(contract)
        self.assertIn("FIELD_SOURCE_COLUMN_UNDECLARED", codes(validate_field_source_references(contract)[0]))
        self.assertEqual(before, contract)


class ExtractionCompleteness(unittest.TestCase):
    def extract(self, root, rows, limit, stale_dimension=False):
        payload = make_xlsx(root / "fields.xlsx", rows)
        if stale_dimension:
            output = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(payload)) as source, zipfile.ZipFile(output, "w") as target:
                for name in source.namelist():
                    data = source.read(name)
                    if name == "xl/worksheets/sheet1.xml":
                        import re
                        data = re.sub(rb'<dimension ref="[^"]*"', b'<dimension ref="A1"', data)
                    target.writestr(name, data)
            payload = output.getvalue()
        path = root / "input.docx"
        make_docx(path, "Synthetic completeness", [payload], [rows])
        output = root / "extracted"
        output.mkdir()
        paragraphs, _, embedded, word = extract_document_to_dirs(path, output, output / "embedded", output / "word", limit, 1)
        return paragraphs, embedded + word, output

    def test_truncation_is_diagnosed_in_both_docx_table_kinds(self):
        with tempfile.TemporaryDirectory() as temporary:
            paragraphs, tables, output = self.extract(Path(temporary), [["Field", "Type"], ["id", "String"], ["value", "String"]], 2)
            self.assertEqual(2, len(tables))
            for table in tables:
                self.assertEqual(2, table.row_count)
                self.assertTrue(any(issue["severity"] == "ERROR" and "TRUNCATED" in issue["code"] for issue in table.extraction_issues))
                with table.csv_path.open(encoding="utf-8-sig", newline="") as handle:
                    self.assertEqual([["Field", "Type"], ["id", "String"]], list(csv.reader(handle)))
            facts = build_structured_facts(tables, paragraphs)
            self.assertEqual(2, len(facts["extraction_issues"]))
            questions = build_question_groups_v2(paragraphs, tables, facts)
            self.assertEqual(2, sum("TRUNCATED" in item.get("extraction_code", "") for item in questions["blocking_codegen"]))
            rendered = (output / "extracted_document.md").read_text(encoding="utf-8")
            for table in tables:
                self.assertIn(table.extraction_issues[0]["code"], rendered)

    def test_equal_limit_and_blank_tail_are_not_truncation(self):
        for limit in (0, 3):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as temporary:
                _, tables, _ = self.extract(Path(temporary), [["Field", "Type"], ["id", "String"], ["value", "String"], ["", ""]], limit)
                self.assertTrue(all(table.row_count == 3 and not table.extraction_issues for table in tables))

    def test_stale_excel_dimension_does_not_hide_overflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, tables, _ = self.extract(Path(temporary), [["Field", "Type"], ["id", "String"], ["value", "String"]], 2, True)
            self.assertEqual("A1", tables[0].dimension)
            self.assertTrue(tables[0].extraction_issues)

    def test_word_preamble_limit_semantics_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, tables, _ = self.extract(Path(temporary), [["explanation"], ["字段名", "类型"], ["id", "String"], ["value", "String"]], 3)
            word = next(table for table in tables if table.source == "word")
            self.assertEqual(2, word.row_count)
            with word.csv_path.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual([["字段名", "类型"], ["id", "String"]], list(csv.reader(handle)))
            self.assertTrue(word.extraction_issues)

    def test_header_only_truncation_is_reported_without_recognized_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            paragraphs, tables, _ = self.extract(Path(temporary), [["Field", "Type"], ["id", "String"]], 1)
            facts = build_structured_facts(tables, paragraphs)
            self.assertEqual(2, len(facts["extraction_issues"]))
            questions = build_question_groups_v2(paragraphs, tables, facts)
            self.assertTrue(any("TRUNCATED" in item.get("extraction_code", "") for item in questions["blocking_codegen"]))


class CodeUnitAndLookup(unittest.TestCase):
    def test_quoted_bad_reference_blocks_only_its_own_unit(self):
        facts = structured_facts()
        for index, mapping in enumerate(facts["report_field_mappings"]):
            mapping["fields"][0].update(source_table="orders", source_field="`missing`" if index == 0 else "amount")
        facts["codegen_contract"] = build_contract_v2(facts, facts["codegen_contract"])
        confirmed_units(facts)
        self.assertFalse(facts["code_units"][0]["readiness"]["ready_for_codegen"])
        self.assertTrue(facts["code_units"][1]["readiness"]["ready_for_codegen"])
        validation = validate_code_unit_contract(facts)
        self.assertFalse(validation["unit_readiness"]["daily_unit"]["ready_for_codegen"])
        self.assertTrue(validation["unit_readiness"]["period_unit"]["ready_for_codegen"])
        before = copy.deepcopy(facts)
        for skill in ("report-codegen", "data-sync-codegen"):
            spec = importlib.util.spec_from_file_location("round4_" + skill.replace("-", "_"), SOURCE_ROOT / "skills" / skill / "scripts/code_unit_selection.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertFalse(module.select_code_unit(facts, "daily_unit", "report-codegen")["readiness"]["ready_for_codegen"])
            self.assertTrue(module.select_code_unit(facts, "period_unit", "report-codegen")["readiness"]["ready_for_codegen"])
        self.assertEqual(before, facts)

    def test_truncated_mapping_blocks_only_its_own_unit(self):
        rows = [["数据表：fixture.daily_output", "", "", "", "", ""],
                ["字段key", "字段名称", "数据源位置", "数据表", "来源字段", "计算逻辑"],
                ["revenue", "revenue", "injected", "orders", "amount", "copy"],
                ["quantity", "quantity", "injected", "orders", "quantity", "copy"]]
        with tempfile.TemporaryDirectory() as temporary:
            paragraphs, tables, _ = ExtractionCompleteness().extract(Path(temporary), rows, 3)
            targets = [Paragraph("", "ClickHouse"), Paragraph("", "fixture.daily_output")]
            extracted = build_structured_facts([tables[0]], targets + paragraphs)
            facts = structured_facts()
            facts["report_field_mappings"][0] = extracted["report_field_mappings"][0]
            facts["extraction_issues"] = extracted["extraction_issues"]
            facts["codegen_contract"] = build_contract_v2(facts, facts["codegen_contract"])
            confirmed_units(facts)
            self.assertFalse(facts["code_units"][0]["readiness"]["ready_for_codegen"])
            self.assertTrue(facts["code_units"][1]["readiness"]["ready_for_codegen"])
            self.assertTrue(any("FIELD_MAPPING_UNCONFIRMED" in item for item in facts["code_units"][0]["blockers"]))

    def test_truncated_source_inventory_blocks_its_unit_and_correction_clears_derived_blockers(self):
        rows = [["位置", "数据表名", "数据表", "取数范围", "字段"],
                ["injected", "orders", "orders", "business date", "store_code,amount"],
                ["injected", "additional", "additional", "business date", "value"]]
        with tempfile.TemporaryDirectory() as temporary:
            paragraphs, tables, _ = ExtractionCompleteness().extract(Path(temporary), rows, 2)
            extracted = build_structured_facts([tables[0]], paragraphs)
            facts = structured_facts()
            facts["report_sources"][0] = extracted["report_sources"][0]
            for index, mapping in enumerate(facts["report_field_mappings"]):
                mapping["fields"][0].update(source_table="orders" if index == 0 else "stores",
                                           source_field="amount" if index == 0 else "region")
            facts["codegen_contract"] = build_contract_v2(facts, facts["codegen_contract"])
            self.assertIn("SOURCE_EVIDENCE_INCOMPLETE", codes(facts["codegen_contract"]["validation_result"]["errors"]))
            confirmed_units(facts)
            self.assertFalse(facts["code_units"][0]["readiness"]["ready_for_codegen"])
            self.assertTrue(facts["code_units"][1]["readiness"]["ready_for_codegen"])
            facts["codegen_contract"]["source_contracts"][0].pop("extraction_issues")
            facts["codegen_contract"]["source_contracts"][0]["status"] = "confirmed"
            unit = facts["code_units"][0]
            contract = copy.deepcopy(unit["execution_contract"])
            change = {"base_sha256": fingerprint(facts),
                      "authorization": {"actor": "user", "evidence": "synthetic complete re-extraction", "reason": "source evidence corrected"},
                      "unit_changes": [{"code_unit_id": unit["code_unit_id"], "execution_contract": contract,
                                        "waterline_contracts": {unit["covered_waterlines"][0]: contract}}]}
            corrected = revise(facts, change)
            self.assertTrue(corrected["code_units"][0]["readiness"]["ready_for_codegen"])
            self.assertFalse(corrected["code_units"][0]["blockers"])
            self.assertTrue(corrected["codegen_contract"]["ready_for_codegen"])
            self.assertEqual(facts["code_units"][1], corrected["code_units"][1])

    def test_source_location_reads_do_not_scale_with_fields_times_sources(self):
        class CountedSource(dict):
            location_reads = 0
            def get(self, key, *default):
                if key in {"exact_location", "logical_name"}:
                    type(self).location_reads += 1
                return super().get(key, *default)

        sources = [CountedSource(exact_location="fixture.source_" + str(index), logical_name="alias_" + str(index),
                                 required_columns=["value"]) for index in range(30)]
        fields = [dict(reference_contract(table="fixture.source_" + str(index % 30))["field_contracts"][0]) for index in range(150)]
        contract = {"source_contracts": sources, "field_contracts": fields}
        before = copy.deepcopy(contract)
        self.assertEqual(([], []), validate_field_source_references(contract))
        self.assertLessEqual(CountedSource.location_reads, len(sources) * 10)
        self.assertEqual(before, contract)
