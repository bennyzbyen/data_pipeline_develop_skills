#!/usr/bin/env python3
"""Offline revision, Markdown completeness and connector-evidence regressions."""

from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT

import copy
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

DOC = SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"
sys.path.insert(0, str(SOURCE_ROOT / "skills/pipeline-forge-guide/scripts"))
sys.path.insert(0, str(DOC))

from code_unit_contract import confirm_code_unit_plan, validate_code_unit_contract
from docx_bundle_contract import build_question_groups_v2, build_codegen_contract
from docx_bundle_facts import build_structured_facts
from docx_bundle_ooxml import Paragraph
from requirement_bundle_markdown import parse_markdown_evidence, write_markdown_evidence
from revise_confirmed_contract import fingerprint, revise
from technical_contract import build_contract_v2, unit_source_reference_errors
from verify_multi_code_unit_delivery import structured_facts
from verify_technical_contract_regression import complete_facts


def confirmed(*, bad=False, manual=False):
    facts = structured_facts()
    for index, mapping in enumerate(facts["report_field_mappings"]):
        mapping["fields"][0].update(source_table="orders", source_field="unselected" if bad and index == 0 else "amount")
    facts["codegen_contract"] = build_contract_v2(facts, facts["codegen_contract"])
    mapping = {"units": [
        {"code_unit_id": "daily_unit", "covered_waterlines": ["daily"], "codegen_route": "report-codegen", "component_kind": "standard_report",
         "blockers": ["manual deployment hold"] if manual else []},
        {"code_unit_id": "period_unit", "covered_waterlines": ["period"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
    ]}
    confirm_code_unit_plan(facts, mapping, timestamp="2026-10-30T00:00:00+00:00")
    return facts


def change_retry(facts):
    unit = facts["code_units"][0]
    contract = copy.deepcopy(unit["execution_contract"])
    contract.setdefault("retry", {})["max_attempts"] = 3
    return {"base_sha256": fingerprint(facts),
            "authorization": {"actor": "user", "evidence": "synthetic correction", "reason": "retry correction"},
            "unit_changes": [{"code_unit_id": unit["code_unit_id"], "execution_contract": contract,
                              "waterline_contracts": {unit["covered_waterlines"][0]: contract}}]}


class CurrentReadiness(unittest.TestCase):
    def test_validator_reports_current_reference_errors_without_mutating_input(self):
        facts = confirmed()
        facts["codegen_contract"]["field_contracts"][0]["physical_source_field"] = "unselected"
        before = copy.deepcopy(facts)
        result = validate_code_unit_contract(facts)
        self.assertEqual("failed", result["status"])
        self.assertFalse(result["unit_readiness"]["daily_unit"]["ready_for_codegen"])
        self.assertTrue(result["unit_readiness"]["period_unit"]["ready_for_codegen"])
        self.assertEqual(before, facts)

    def test_selectors_refresh_only_the_selected_unit(self):
        facts = confirmed()
        facts["codegen_contract"]["field_contracts"][0]["physical_source_field"] = "unselected"
        before = copy.deepcopy(facts)
        for skill in ("report-codegen", "data-sync-codegen"):
            with self.subTest(skill=skill):
                path = SOURCE_ROOT / "skills" / skill / "scripts/code_unit_selection.py"
                spec = importlib.util.spec_from_file_location("round3_" + skill.replace("-", "_"), path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                bad = module.select_code_unit(facts, "daily_unit", "report-codegen")
                good = module.select_code_unit(facts, "period_unit", "report-codegen")
                self.assertFalse(bad["readiness"]["ready_for_codegen"])
                self.assertTrue(good["readiness"]["ready_for_codegen"])
        self.assertEqual(before, facts)

    def test_doc_selector_allows_an_independent_valid_unit(self):
        spec = importlib.util.spec_from_file_location("round3_doc_selector", DOC / "code_unit_selection.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        facts = confirmed()
        facts["codegen_contract"]["field_contracts"][0]["physical_source_field"] = "unselected"
        self.assertEqual("period_unit", module.select_code_unit(facts, "period_unit", "report-codegen")["code_unit_id"])
        with self.assertRaises(ValueError):
            module.select_code_unit(facts, "daily_unit", "report-codegen")

    def test_corrected_reference_clears_only_generated_blockers(self):
        facts = confirmed(bad=True)
        facts["codegen_contract"]["field_contracts"][0]["physical_source_field"] = "amount"
        before = copy.deepcopy(facts)
        result = revise(facts, change_retry(facts))
        self.assertTrue(result["code_units"][0]["readiness"]["ready_for_codegen"])
        self.assertFalse(result["code_units"][0]["blockers"])
        self.assertTrue(result["codegen_contract"]["ready_for_codegen"])
        self.assertEqual([], result["codegen_contract"]["validation_result"]["errors"])
        self.assertFalse(any("unselected" in item for item in result["codegen_contract"]["blockers"]))
        self.assertEqual(before, facts)
        self.assertEqual(before["code_units"][1], result["code_units"][1])
        self.assertEqual(before["code_unit_plan"]["confirmation_audit"], result["code_unit_plan"]["confirmation_audit"])

    def test_manual_and_legacy_untagged_blockers_remain(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                facts = confirmed(bad=True, manual=True)
                facts["codegen_contract"]["field_contracts"][0]["physical_source_field"] = "amount"
                if legacy:
                    facts["code_units"][0].pop("derived_blockers", None)
                result = revise(facts, change_retry(facts))
                self.assertFalse(result["code_units"][0]["readiness"]["ready_for_codegen"])
                self.assertIn("manual deployment hold", result["code_units"][0]["blockers"])
                if legacy:
                    self.assertTrue(any("unselected" in item for item in result["code_units"][0]["blockers"]))

    def test_unresolved_reference_stays_blocked_after_revision(self):
        facts = confirmed(bad=True)
        result = revise(facts, change_retry(facts))
        self.assertFalse(result["code_units"][0]["readiness"]["ready_for_codegen"])
        self.assertTrue(result["code_units"][1]["readiness"]["ready_for_codegen"])

    def test_global_manual_blocker_is_not_rewritten_or_released(self):
        for corrected in (False, True):
            with self.subTest(corrected=corrected):
                facts = confirmed(bad=True)
                facts["codegen_contract"]["blockers"].append("manual global hold")
                if corrected:
                    facts["codegen_contract"]["field_contracts"][0]["physical_source_field"] = "amount"
                result = revise(facts, change_retry(facts))
                self.assertIn("manual global hold", result["codegen_contract"]["blockers"])
                self.assertFalse(result["codegen_contract"]["ready_for_codegen"])

    def test_completed_execution_contract_clears_its_generated_gap(self):
        facts = confirmed()
        steps = copy.deepcopy(facts["code_units"][0]["execution_contract"]["steps"])
        facts["code_units"][0]["execution_contract"]["steps"] = []
        from code_unit_contract import refresh_code_unit_readiness
        refresh_code_unit_readiness(facts, facts["code_units"][0])
        self.assertFalse(facts["code_units"][0]["readiness"]["ready_for_codegen"])
        change = change_retry(facts)
        change["unit_changes"][0]["execution_contract"]["steps"] = steps
        for contract in change["unit_changes"][0]["waterline_contracts"].values():
            contract["steps"] = copy.deepcopy(steps)
        result = revise(facts, change)
        self.assertTrue(result["code_units"][0]["readiness"]["ready_for_codegen"])


class MarkdownCompleteness(unittest.TestCase):
    def parse(self, text, root, limit=0):
        path = root / "requirement.md"
        path.write_text(text, encoding="utf-8")
        paragraphs, tables, original = parse_markdown_evidence(path, root / "tables", limit, 1)
        return path, paragraphs, tables, original

    def rows(self, table):
        with table.csv_path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle))

    def test_short_row_is_padded_and_later_rows_are_preserved(self):
        text = "| Field | Type | Note |\n| --- | --- | --- |\n| id | String |\n| code | String | explicit |\n"
        with tempfile.TemporaryDirectory() as temporary:
            path, paragraphs, tables, original = self.parse(text, Path(temporary))
            self.assertEqual([["Field", "Type", "Note"], ["id", "String", ""], ["code", "String", "explicit"]], self.rows(tables[0]))
            issue = tables[0].extraction_issues[0]
            self.assertEqual(("MARKDOWN_ROW_PADDED", "WARNING", 3), (issue["code"], issue["severity"], issue["line"]))
            self.assertEqual(text, original)
            self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_wide_row_is_reported_without_losing_following_valid_rows(self):
        text = "| Field | Type |\n| --- | --- |\n| ambiguous | String | extra |\n| id | String |\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, paragraphs, tables, original = self.parse(text, root)
            self.assertEqual([["Field", "Type"], ["id", "String"]], self.rows(tables[0]))
            issue = tables[0].extraction_issues[0]
            self.assertEqual(("MARKDOWN_ROW_TOO_WIDE", "ERROR", 3), (issue["code"], issue["severity"], issue["line"]))
            evidence = root / "evidence.md"
            write_markdown_evidence(evidence, path, paragraphs, tables, original)
            rendered = evidence.read_text(encoding="utf-8")
            self.assertIn("MARKDOWN_ROW_TOO_WIDE", rendered)
            self.assertIn("| ambiguous | String | extra |", rendered)

    def test_ambiguous_mapping_reaches_codegen_blockers(self):
        text = """# Fields
数据表：fixture.output

| 字段key | 字段名称 | 数据源位置 | 数据表 | 来源字段 | 计算逻辑 |
| --- | --- | --- | --- | --- | --- |
| bad | 坏行 | HBase | fixture.source | bad | copy | extra |
| id | 编号 | HBase | fixture.source | id | copy |
"""
        with tempfile.TemporaryDirectory() as temporary:
            _path, paragraphs, tables, _original = self.parse(text, Path(temporary))
            paragraphs = [Paragraph("", "ClickHouse", 1, "requirement.md"),
                          Paragraph("", "fixture.output", 1, "requirement.md")] + paragraphs
            facts = build_structured_facts(tables, paragraphs)
            self.assertEqual(["id"], [field["target_field"] for field in facts["report_field_mappings"][0]["fields"]])
            self.assertTrue(facts["report_field_mappings"][0]["requires_confirmation"])
            questions = build_question_groups_v2(paragraphs, tables, facts)
            self.assertTrue(any(item.get("extraction_code") == "MARKDOWN_ROW_TOO_WIDE" for item in questions["blocking_codegen"]))
            contract = build_codegen_contract(facts, questions)
            self.assertFalse(contract["ready_for_codegen"])
            self.assertTrue(any(item["code"] == "FIELD_MAPPING_UNCONFIRMED"
                                for item in unit_source_reference_errors(contract, ["fixture.output"])))

    def test_explicit_truncation_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            _path, _paragraphs, tables, _text = self.parse("| Field | Type |\n| --- | --- |\n| id | String |\n| code | String |\n", Path(temporary), 2)
            self.assertEqual(2, tables[0].row_count)
            self.assertTrue(any(item["code"] == "MARKDOWN_TABLE_TRUNCATED" for item in tables[0].extraction_issues))

    def test_adjacent_tables_escaped_pipes_and_valid_rows_remain_supported(self):
        text = "| Field | Type |\n| --- | --- |\n| id | String |\n| Field | Note |\n| --- | --- |\n| code | a\\|b |\n"
        with tempfile.TemporaryDirectory() as temporary:
            _path, _paragraphs, tables, _text = self.parse(text, Path(temporary))
            self.assertEqual(2, len(tables))
            self.assertEqual(["code", "a|b"], self.rows(tables[1])[1])
            self.assertTrue(all(not table.extraction_issues for table in tables))


class FsEvidence(unittest.TestCase):
    def has_fs_question(self, text, sources=None):
        facts = complete_facts()
        if sources is not None:
            facts["report_sources"] = sources
        groups = build_question_groups_v2([Paragraph("", text)], [], facts)
        return any(question["id"] == "TC-CG-014" for question in groups["blocking_codegen"])

    def test_substrings_and_explicit_nonuse_do_not_invent_fs_requirements(self):
        for text in ("pagination offset = 0", "DFS cache", "fs_count is a field", "不使用FS", "without FS", "no FS required"):
            with self.subTest(text=text):
                self.assertFalse(self.has_fs_question(text))

    def test_actual_connector_terms_and_chinese_cues_are_retained(self):
        for text in ("FS", "FS目录", "Gateway下载", "文件目录", "留痕", "未提供FS路径", "without FS, use Gateway"):
            with self.subTest(text=text):
                self.assertTrue(self.has_fs_question(text))

    def test_structured_storage_and_paths_take_precedence_over_text(self):
        for source in ({"storage": "FS", "table_or_path": "/fixture/file.csv"},
                       {"storage": "DataHub_FS", "table_or_path": "monthly"},
                       {"storage": "GatewayFS", "table_or_path": "monthly"},
                       {"storage": "Gateway", "table_or_path": "monthly"},
                       {"storage": "", "table_or_path": "/fixture/file.csv"}):
            with self.subTest(source=source):
                self.assertTrue(self.has_fs_question("no FS required", [source]))
        self.assertFalse(self.has_fs_question("", [{"storage": "HBase", "table_or_path": "fixture.offset_history", "fields": ["fs_count"]}]))
