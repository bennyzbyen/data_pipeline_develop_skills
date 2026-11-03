#!/usr/bin/env python3
"""Offline table-role, Markdown-boundary and prepared-header regressions."""

from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT

import copy
import csv
import html
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


DOC = SOURCE_ROOT / "skills/data-doc-to-dev-md/scripts"
sys.path.insert(0, str(DOC))

import docx_bundle_ooxml as ooxml
import docx_bundle_tables as tables
from docx_bundle_contract import build_question_groups_v2
from docx_bundle_facts import build_structured_facts, report_field_rows
from requirement_bundle_inputs import extract_document_to_dirs
from requirement_bundle_markdown import parse_markdown_evidence, split_markdown_row
from verify_docx_bundle_multidoc import make_xlsx, table_xml, NS_REL_OFFICE, NS_REL_PKG, NS_W


HEADERS = ["Description", "Data Storage", "Database", "Table Name"]


def inventory(storage="ClickHouse", name="orders"):
    return [HEADERS, [name, storage, "fixture", name]]


def markdown_table(rows):
    return "\n".join("| " + " | ".join(row) + " |" for row in [rows[0], ["---"] * len(rows[0]), *rows[1:]]) + "\n"


def make_blocks(path, blocks):
    body, relationships = [], []
    with zipfile.ZipFile(path, "w") as archive:
        for kind, value in blocks:
            if kind == "heading":
                level, text = value
                body.append(f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr><w:r><w:t>{html.escape(text)}</w:t></w:r></w:p>')
            elif kind == "paragraph":
                body.append(f'<w:p><w:r><w:t>{html.escape(value)}</w:t></w:r></w:p>')
            elif kind == "word":
                body.append(table_xml(value))
            elif kind == "reuse":
                body.append(f'<w:p><w:r><w:object><o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="{NS_REL_OFFICE}" r:id="rId{value}"/></w:object></w:r></w:p>')
            else:
                index = len(relationships) + 1
                name = f"fixture_{index}.xlsx"
                archive.writestr("word/embeddings/" + name, value)
                body.append(f'<w:p><w:r><w:object><o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="{NS_REL_OFFICE}" r:id="rId{index}"/></w:object></w:r></w:p>')
                relationships.append(f'<Relationship Id="rId{index}" Target="embeddings/{name}" Type="{NS_REL_OFFICE}/package"/>')
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{NS_W}"><w:body>{"".join(body)}</w:body></w:document>')
        archive.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{NS_REL_PKG}">{"".join(relationships)}</Relationships>')


def extract_blocks(root, blocks, limit=0):
    path = root / "input.docx"
    make_blocks(path, blocks)
    output = root / "extracted"
    output.mkdir()
    paragraphs, _, embedded, word = extract_document_to_dirs(path, output, output / "embedded", output / "word", limit, 1)
    summaries = embedded + word
    return build_structured_facts(summaries, paragraphs), summaries, paragraphs


def parse(text, root, doc_index=1, name="input.md", limit=0):
    path = root / name
    path.write_text(text, encoding="utf-8")
    paragraphs, summaries, original = parse_markdown_evidence(path, root / (name + "_tables"), limit, doc_index)
    return build_structured_facts(summaries, paragraphs), summaries, paragraphs, original


class TableRoles(unittest.TestCase):
    def test_markdown_source_inventories_are_sources_for_both_storages(self):
        for storage in ("ClickHouse", "HBase"):
            with self.subTest(storage=storage), tempfile.TemporaryDirectory() as temporary:
                facts, _, _, _ = parse("# Data Sources\n\n" + markdown_table(inventory(storage)), Path(temporary))
                self.assertEqual(["fixture.orders"], [row["table_or_path"] for row in facts["report_sources"]])
                self.assertEqual([], facts["report_physical_targets"])
                self.assertEqual([], facts["report_clickhouse_targets"])

    def test_target_storage_is_not_implicitly_clickhouse(self):
        for storage, expected in (("ClickHouse", 1), ("HBase", 0), ("FS", 0)):
            with self.subTest(storage=storage), tempfile.TemporaryDirectory() as temporary:
                facts, _, _, _ = parse("# Data Targets\n\n" + markdown_table(inventory(storage)), Path(temporary))
                self.assertEqual(1, len(facts["report_physical_targets"]))
                self.assertEqual(expected, len(facts["report_clickhouse_targets"]))
                self.assertFalse(facts["report_sources"])

    def test_example_inventory_stays_in_evidence_without_formal_facts(self):
        text = "# Examples\n\n" + markdown_table(inventory())
        with tempfile.TemporaryDirectory() as temporary:
            facts, summaries, _, original = parse(text, Path(temporary))
            self.assertEqual(text, original)
            self.assertEqual(1, len(summaries))
            self.assertIn("orders", summaries[0].csv_path.read_text(encoding="utf-8-sig"))
            self.assertFalse(facts["report_sources"])
            self.assertFalse(facts["report_physical_targets"])

    def test_nested_target_heading_does_not_promote_an_example(self):
        with tempfile.TemporaryDirectory() as temporary:
            facts, _, _, _ = parse("# Examples\n\n## Data Targets\n\n" + markdown_table(inventory()), Path(temporary))
            self.assertFalse(facts["report_physical_targets"])

    def test_source_role_survives_a_deeper_generic_heading(self):
        with tempfile.TemporaryDirectory() as temporary:
            facts, _, _, _ = parse("# Data Sources\n\n## Order details\n\n" + markdown_table(inventory()), Path(temporary))
            self.assertEqual(1, len(facts["report_sources"]))
            self.assertFalse(facts["report_physical_targets"])

    def test_section_and_document_boundaries_reset_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = "# Data Sources\n\n" + markdown_table(inventory("HBase", "source"))
            text += "\n# Data Targets\n\n" + markdown_table(inventory("ClickHouse", "output"))
            first, summaries, paragraphs, _ = parse(text, root)
            self.assertEqual(["fixture.source"], [row["table_or_path"] for row in first["report_sources"]])
            self.assertEqual(["fixture.output"], [row["table"] for row in first["report_clickhouse_targets"]])
            _, second_tables, second_paragraphs, _ = parse(markdown_table(inventory("ClickHouse", "legacy")), root, 2, "legacy.md")
            combined = build_structured_facts(summaries + second_tables, paragraphs + second_paragraphs)
            self.assertEqual({"fixture.output", "fixture.legacy"}, {row["table"] for row in combined["report_clickhouse_targets"]})

    def test_word_tables_follow_explicit_sections(self):
        for heading, source_count, target_count in (("Data Sources", 1, 0), ("Data Targets", 0, 1), ("Examples", 0, 0)):
            with self.subTest(heading=heading), tempfile.TemporaryDirectory() as temporary:
                facts, _, _ = extract_blocks(Path(temporary), [("heading", (1, heading)), ("word", inventory())])
                self.assertEqual(source_count, len(facts["report_sources"]))
                self.assertEqual(target_count, len(facts["report_physical_targets"]))

    def test_embedded_workbooks_follow_explicit_sections(self):
        for heading, source_count, target_count in (("Data Sources", 1, 0), ("Data Targets", 0, 1), ("Examples", 0, 0)):
            with self.subTest(heading=heading), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workbook = make_xlsx(root / "inventory.xlsx", inventory())
                facts, _, _ = extract_blocks(root, [("heading", (1, heading)), ("embedded", workbook)])
                self.assertEqual(source_count, len(facts["report_sources"]))
                self.assertEqual(target_count, len(facts["report_physical_targets"]))

    def test_mixed_word_and_embedded_sections_share_one_document_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = make_xlsx(root / "target.xlsx", inventory("ClickHouse", "output"))
            with patch.object(ooxml, "read_zip_text", wraps=ooxml.read_zip_text) as reader:
                facts, summaries, _ = extract_blocks(root, [("heading", (1, "Data Sources")), ("word", inventory("HBase", "source")),
                    ("heading", (1, "Data Targets")), ("embedded", target),
                    ("heading", (1, "Examples")), ("word", inventory("ClickHouse", "example"))])
            self.assertEqual(1, sum(call.args[1] == "word/document.xml" for call in reader.call_args_list))
            self.assertEqual(3, len(summaries))
            self.assertEqual(["fixture.source"], [row["table_or_path"] for row in facts["report_sources"]])
            self.assertEqual(["fixture.output"], [row["table"] for row in facts["report_physical_targets"]])

    def test_standalone_extractors_keep_the_same_section_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workbook = make_xlsx(root / "inventory.xlsx", inventory("HBase"))
            _, summaries, _ = extract_blocks(root, [("heading", (1, "Data Sources")), ("embedded", workbook),
                ("heading", (1, "Data Targets")), ("word", inventory())])
            embedded = ooxml.extract_embedded_tables(root / "input.docx", root / "reference_embedded", 0)
            word = ooxml.extract_word_tables(root / "input.docx", root / "reference_word", 0)
            self.assertEqual(["source", "target"], [getattr(summary, "section_role", "") for summary in embedded + word])
            self.assertEqual([summary.csv_path.read_bytes() for summary in summaries],
                             [summary.csv_path.read_bytes() for summary in embedded + word])

    def test_reused_workbook_with_conflicting_roles_stays_unresolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workbook = make_xlsx(root / "inventory.xlsx", inventory())
            facts, summaries, paragraphs = extract_blocks(root, [("heading", (1, "Data Sources")), ("embedded", workbook),
                ("heading", (1, "Data Targets")), ("reuse", 1)])
            self.assertEqual(1, len(summaries))
            self.assertTrue(summaries[0].csv_path.exists())
            self.assertFalse(facts["report_sources"])
            self.assertFalse(facts["report_physical_targets"])
            questions = build_question_groups_v2(paragraphs, summaries, facts)
            self.assertTrue(any(question.get("extraction_code") == "TABLE_SECTION_AMBIGUOUS" for question in questions["blocking_codegen"]))

    def test_same_named_targets_keep_storage_boundaries(self):
        rows = [HEADERS, ["orders", "HBase", "fixture", "orders"], ["orders", "ClickHouse", "fixture", "orders"]]
        with tempfile.TemporaryDirectory() as temporary:
            facts, _, _, _ = parse("# Data Targets\n\n" + markdown_table(rows), Path(temporary))
            self.assertEqual(2, len(facts["report_physical_targets"]))
            self.assertEqual(["ClickHouse"], [row["storage"] for row in facts["report_clickhouse_targets"]])

    def test_chinese_matrix_uses_its_explicit_role(self):
        rows = [["位置", "数据库", "数据表名", "数据表"], ["HBase", "fixture", "orders", "orders"]]
        with tempfile.TemporaryDirectory() as temporary:
            facts, _, _, _ = parse("# 数据源\n\n" + markdown_table(rows), Path(temporary))
            self.assertEqual(["fixture.orders"], [row["table_or_path"] for row in facts["report_sources"]])
            self.assertFalse(facts["report_physical_targets"])
        rows = [["位置", "数据表名", "数据表", "取数范围"], ["ClickHouse", "output", "fixture.output", "business date"]]
        with tempfile.TemporaryDirectory() as temporary:
            facts, _, _, _ = parse("# 目标表\n\n" + markdown_table(rows), Path(temporary))
            self.assertEqual(["fixture.output"], [row["table"] for row in facts["report_clickhouse_targets"]])
            self.assertFalse(facts["report_sources"])

    def test_example_field_dictionary_does_not_infer_business_sources(self):
        rows = [["字段key", "字段名称", "数据源位置", "数据表", "来源字段", "计算逻辑"],
                ["amount", "amount", "HBase", "fixture.example", "amount", "copy"]]
        with tempfile.TemporaryDirectory() as temporary:
            facts, summaries, _, _ = parse("# Examples\n\n" + markdown_table(rows), Path(temporary))
            self.assertEqual(1, len(summaries))
            self.assertFalse(facts["report_field_mappings"])
            self.assertFalse(facts["report_sources"])

    def test_truncated_example_is_not_a_business_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            facts, summaries, paragraphs, _ = parse("# Examples\n\n" + markdown_table(inventory()), Path(temporary), limit=1)
            self.assertTrue(summaries[0].extraction_issues)
            questions = build_question_groups_v2(paragraphs, summaries, facts)
            self.assertFalse(any(question.get("extraction_code") for question in questions["blocking_codegen"]))

    def test_unsectioned_legacy_target_layout_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            facts, _, _, _ = parse(markdown_table(inventory()), Path(temporary))
            self.assertEqual(["fixture.orders"], [row["table"] for row in facts["report_clickhouse_targets"]])


class MarkdownBoundaries(unittest.TestCase):
    def test_short_inner_fence_does_not_close_a_long_outer_fence(self):
        text = "````markdown\n```\n# Data Targets\n" + markdown_table(inventory("ClickHouse", "fake")) + "````\n\n# Data Targets\n" + markdown_table(inventory("ClickHouse", "real"))
        with tempfile.TemporaryDirectory() as temporary:
            facts, summaries, _, original = parse(text, Path(temporary))
            self.assertEqual(text, original)
            self.assertEqual(1, len(summaries))
            self.assertEqual(["fixture.real"], [row["table"] for row in facts["report_clickhouse_targets"]])

    def test_fence_with_trailing_info_is_not_a_closer(self):
        text = "```markdown\n```python\n" + markdown_table(inventory()) + "```\n"
        with tempfile.TemporaryDirectory() as temporary:
            _, summaries, _, _ = parse(text, Path(temporary))
            self.assertFalse(summaries)

    def test_fence_character_must_match_and_unclosed_fences_stay_code(self):
        for opening, inner, closing in (("~~~~", "```", "~~~~"), ("`````", "````", "")):
            with self.subTest(opening=opening), tempfile.TemporaryDirectory() as temporary:
                text = opening + "\n" + inner + "\n" + markdown_table(inventory()) + closing
                _, summaries, _, original = parse(text, Path(temporary))
                self.assertFalse(summaries)
                self.assertEqual(text, original)

    def test_inline_code_uses_matching_marker_lengths(self):
        for value in ("``a|b``", "``a`|b``", "```a``|b```", "`a|b`"):
            with self.subTest(value=value):
                self.assertEqual(["id", value], split_markdown_row("| id | " + value + " |"))

    def test_unpaired_inline_marker_does_not_swallow_a_column(self):
        self.assertEqual(["id", "unmatched ` text", "tail"], split_markdown_row("| id | unmatched ` text | tail |"))

    def test_escaped_pipes_and_adjacent_tables_keep_existing_behavior(self):
        text = "| Field | Note |\n| --- | --- |\n| id | a\\|b |\n| Field | Type |\n| --- | --- |\n| amount | Int64 |\n"
        with tempfile.TemporaryDirectory() as temporary:
            _, summaries, _, _ = parse(text, Path(temporary))
            self.assertEqual(2, len(summaries))
            self.assertTrue(all(not summary.extraction_issues for summary in summaries))
            with summaries[0].csv_path.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(["id", "a|b"], list(csv.reader(handle))[1])


class HeaderLookup(unittest.TestCase):
    def test_exact_match_precedence_and_empty_values_are_preserved(self):
        rows = [{"Key": "", "字段key": "fallback", "字段名称": "label"},
                {"KEY": "normalized", "Field": "exact", "字段名称": "label"},
                {"字段_key": "first", "KEY": "second", "字段名称": "label"}]
        before = copy.deepcopy(rows)
        self.assertEqual(["", "exact", "first"], [row["target_field"] for row in report_field_rows(rows)])
        self.assertEqual(before, rows)
        self.assertEqual("", tables.cell_value({"Key": "", "KEY": "fallback"}, "Key"))

    def test_formula_and_contains_matching_remain_ordered_and_case_sensitive(self):
        rows = [{"字段key": "amount", "字段名称": "metric", "字段公式 A": " first ", "字段公式 B": "second",
                 "EO+ERP first": "eo1", "EO+ERP second": "eo2", "dms": "lower", "DMS explicit": "upper"}]
        value = report_field_rows(rows)[0]
        self.assertEqual("first", value["calculation_logic"])
        self.assertEqual("eo1", value["eo_order_logic"])
        self.assertEqual("upper", value["dms_order_logic"])

    def test_new_values_with_the_same_headers_are_not_cached(self):
        rows = [{"字段key": "id", "字段名称": "label", "来源字段": "before"}]
        self.assertEqual("before", report_field_rows(rows)[0]["source_field"])
        rows[0]["来源字段"] = "after"
        self.assertEqual("after", report_field_rows(rows)[0]["source_field"])

    def test_header_normalization_cost_depends_on_schemas_not_rows(self):
        rows = [{"字段key": f"field_{index}", "字段名称": "metric", "数据源位置": "HBase",
                 "数据表": "fixture.source", "来源字段": "amount", "计算逻辑": "copy"} for index in range(2000)]
        before = copy.deepcopy(rows)
        with patch.object(tables, "normalize_header", wraps=tables.normalize_header) as normalizer:
            result = report_field_rows(rows)
        self.assertEqual(2000, len(result))
        self.assertLessEqual(normalizer.call_count, 300)
        self.assertEqual(before, rows)
