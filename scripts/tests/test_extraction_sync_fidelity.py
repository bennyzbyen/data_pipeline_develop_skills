#!/usr/bin/env python3
"""Offline fidelity checks for source-field coverage and extraction optimizations."""

from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT

import ast
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


DOC_SCRIPTS = SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"
sys.path.insert(0, str(DOC_SCRIPTS))

import docx_bundle_ooxml as ooxml
from docx_bundle_facts import _infer_sources_from_field_mappings
from requirement_bundle_inputs import extract_document_to_dirs
from technical_contract import build_contract_v2, build_source_contracts
from verify_docx_bundle_multidoc import make_docx, make_docx_with_embedding_context, make_xlsx


def source_facts():
    fields = [
        {"source_storage": "HBase", "source_table": "fixture.orders", "source_field": name,
         "target_field": name, "calculation_logic": "copy"}
        for name in ("store_id", "amount", "period", "amount")
    ]
    return {"report_sources": [], "report_field_mappings": [
        {"declared_table": "fixture.output", "requires_confirmation": True, "fields": fields[:2]},
        {"declared_table": "fixture.output", "requires_confirmation": True, "fields": fields[2:]},
    ]}


class SourceCoverage(unittest.TestCase):
    def test_all_mapped_fields_reach_source_contract_in_order(self):
        facts = source_facts()
        original = copy.deepcopy(facts["report_field_mappings"])
        _infer_sources_from_field_mappings(facts)
        self.assertEqual(["store_id", "amount", "period"], facts["report_sources"][0]["fields"])
        self.assertEqual(["store_id", "amount", "period"], build_source_contracts(facts)[0]["required_columns"])
        self.assertEqual(original, facts["report_field_mappings"])
        before = copy.deepcopy(facts)
        _infer_sources_from_field_mappings(facts)
        self.assertEqual(before, facts)

    def test_storage_boundaries_and_missing_fields_stay_distinct(self):
        facts = source_facts()
        facts["report_field_mappings"].append({"fields": [
            {"source_storage": "FS", "source_table": "fixture.orders", "source_field": "file_id"},
            {"source_storage": "FS", "source_table": "fixture.orders", "source_field": ""},
            {"source_storage": "HBase", "source_table": "", "source_field": "unbound"},
        ]})
        _infer_sources_from_field_mappings(facts)
        self.assertEqual(2, len(facts["report_sources"]))
        self.assertEqual(["file_id"], facts["report_sources"][1]["fields"])
        self.assertEqual(["store_id", "amount", "period"], facts["report_sources"][0]["fields"])

    def test_explicit_source_and_unconfirmed_binding_are_preserved(self):
        facts = source_facts()
        explicit = {"storage": "HBase", "table_or_path": "fixture.orders", "fields": ["declared"],
                    "range": "confirmed slice", "rowkey": "confirmed rule"}
        facts["report_sources"] = [copy.deepcopy(explicit)]
        _infer_sources_from_field_mappings(facts)
        self.assertEqual([explicit], facts["report_sources"])
        contract = build_contract_v2(facts, {"ready_for_codegen": True})
        self.assertFalse(contract["ready_for_codegen"])
        self.assertTrue(any("field dictionary target binding" in item for item in contract["blockers"]))

    def test_docx_mapping_columns_reach_handoff_without_approving_codegen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [
                ["数据表：fixture.output", "", "", "", "", ""],
                ["字段key", "字段名称", "数据源位置", "数据表", "来源字段", "计算逻辑"],
                ["store_id", "门店", "HBase", "fixture.orders", "store_id", "copy"],
                ["amount", "金额", "HBase", "fixture.orders", "amount", "copy"],
                ["period", "周期", "HBase", "fixture.orders", "period", "copy"],
            ]
            workbook = make_xlsx(root / "fields.xlsx", rows)
            docx = root / "requirement.docx"
            make_docx(docx, "Synthetic field coverage", [workbook], [])
            completed = subprocess.run(
                [sys.executable, "-B", str(DOC_SCRIPTS / "extract_docx_bundle.py"),
                 "--docx", str(docx), "--out", str(root / "delivery")],
                capture_output=True, text=True, encoding="utf-8", check=False)
            self.assertEqual(0, completed.returncode, completed.stderr)
            facts = json.loads((root / "delivery/dev_doc/structured_facts.json").read_text(encoding="utf-8"))
            self.assertEqual(["store_id", "amount", "period"], facts["report_sources"][0]["fields"])
            self.assertEqual(["store_id", "amount", "period"], facts["codegen_contract"]["source_contracts"][0]["required_columns"])
            self.assertFalse(facts["codegen_contract"]["ready_for_codegen"])


class DocxFidelity(unittest.TestCase):
    def test_bundle_reuses_document_but_matches_public_extractors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workbook = make_xlsx(root / "fields.xlsx", [["字段", "类型"], ["id", "String"]])
            docx = root / "requirement.docx"
            make_docx_with_embedding_context(docx, [("fixture.orders 字段字典", workbook)])
            output = root / "output"
            output.mkdir()
            with patch.object(ooxml, "read_zip_text", wraps=ooxml.read_zip_text) as reader:
                paragraphs, count, embedded, word = extract_document_to_dirs(
                    docx, output, output / "embedded", output / "word", 0, 1)
            reads = sum(call.args[1] == "word/document.xml" for call in reader.call_args_list)
            self.assertEqual(1, reads)
            expected, expected_count, _ = ooxml.extract_docx_paragraphs(docx)
            self.assertEqual([(p.style, p.text) for p in expected], [(p.style, p.text) for p in paragraphs])
            self.assertEqual(expected_count, count)
            reference = ooxml.extract_embedded_tables(docx, root / "reference", 0)
            self.assertEqual(1, len(embedded))
            self.assertEqual(reference[0].context_text, embedded[0].context_text)
            self.assertEqual(reference[0].csv_path.read_bytes(), embedded[0].csv_path.read_bytes())
            self.assertEqual([], word)
            self.assertEqual("requirement.docx", embedded[0].source_doc_name)

    def test_word_tables_row_limit_and_changed_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx = root / "word.docx"
            for title in ("first version", "second version"):
                make_docx(docx, title, [], [[["说明"], ["字段名", "类型"], ["id", "String"], ["code", "String"]]])
                output = root / title
                output.mkdir()
                paragraphs, count, embedded, word = extract_document_to_dirs(
                    docx, output, output / "embedded", output / "word", 3, 2)
                self.assertEqual(title, paragraphs[0].text)
                self.assertEqual(1, count)
                self.assertEqual([], embedded)
                reference = ooxml.extract_word_tables(docx, root / "reference", 3)
                self.assertEqual(reference[0].csv_path.read_bytes(), word[0].csv_path.read_bytes())
                self.assertEqual(2, word[0].row_count)
                self.assertEqual(2, word[0].source_doc_index)

    def test_missing_or_malformed_document_does_not_write_tables(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, payload, error in (("missing", None, ValueError), ("malformed", b"<broken", ooxml.ET.ParseError)):
                docx = root / (name + ".docx")
                with zipfile.ZipFile(docx, "w") as archive:
                    archive.writestr("unrelated.txt", "fixture")
                    if payload is not None:
                        archive.writestr("word/document.xml", payload)
                output = root / name
                with self.assertRaises(error):
                    extract_document_to_dirs(docx, output, output / "embedded", output / "word", 0, 1)
                self.assertFalse(output.exists())


class CotCleaning(unittest.TestCase):
    def test_both_templates_preserve_values_and_csv_bytes(self):
        asset = SOURCE_ROOT / "skills/data-sync-codegen/assets/minimal_sync_project"
        row = ["中\n文\t'\"\r\x1d,空", "  keep spaces  ", "", None, 0, 1.25, False, b"bytes"]
        expected = ["中文,空", "  keep spaces  ", "", None, 0, 1.25, False, b"bytes"]
        for directory in ("cot_sync_with_period", "cot_sync_without_period"):
            with self.subTest(template=directory):
                path = asset / directory / "etl_source.py.template"
                tree = ast.parse(path.read_text(encoding="utf-8"))
                function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "process_row")
                function.decorator_list = []
                constants = [n for n in tree.body if isinstance(n, ast.Assign)]
                namespace = {}
                exec(compile(ast.Module(body=constants + [function], type_ignores=[]), str(path), "exec"), namespace)
                result = namespace["process_row"](row)
                self.assertEqual(expected, result)
                self.assertIsNone(result[3])
                self.assertIs(result[6], False)
                self.assertEqual("中\n文\t'\"\r\x1d,空", row[0])
                actual_csv, expected_csv = io.StringIO(newline=""), io.StringIO(newline="")
                csv.writer(actual_csv).writerow(result)
                csv.writer(expected_csv).writerow(expected)
                self.assertEqual(expected_csv.getvalue().encode("utf-8"), actual_csv.getvalue().encode("utf-8"))
