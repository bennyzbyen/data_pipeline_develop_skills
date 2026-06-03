---
name: data-doc-to-dev-md
description: Convert PRD, DataEngine, DataHub, COT, HBase, ClickHouse, Superview, and report requirement DOCX files into AI-readable Markdown development documents, extracting正文, embedded Excel tables, source/target tables, field dictionaries, calculation logic, scheduling, rerun rules, and open questions for Python data synchronization or report development.
---

# Data Doc To Dev Markdown

Use this skill when the user provides PRD, DataEngine, DataHub, waterline, report, COT, HBase, ClickHouse, or Superview DOCX documents and asks to produce an AI-readable development document.

## Core Rules

- Do not write production code in this skill.
- Extract facts first; keep uncertain business meaning in `questions.md`.
- Treat DOCX embedded Excel workbooks as primary evidence, not decoration.
- Treat Word正文表格 as primary evidence too, especially Data Source, Data Target, HBase field dictionaries, and logic tables that are not embedded Excel workbooks.
- Preserve original Chinese business terms, field names, table names, and calculation text.
- Never invent field mappings, rowkey rules, credentials, or production paths.

## Inputs

- Required: one or more `.docx` files.
- Optional: project name, supplemental Excel files, screenshots, copied tables, known target project type (`data-sync` or `report`).

## Outputs

Create outputs under a user-provided output folder, or default to `outputs/<project-name>/`:

- `extracted/extracted_document.md`: document title, paragraphs, headings, embedded workbook summary.
- `extracted/extracted_tables/*.csv`: CSV exports for embedded Excel sheets.
- `extracted/word_tables/*.csv`: CSV exports for Word正文表格 when present.
- `dev_doc/dev_doc.md`: standard AI-readable development document.
- `dev_doc/structured_facts.json`: machine-readable facts extracted from recognized embedded Excel matrices.
- `dev_doc/questions.md`: missing or uncertain points requiring user confirmation.

## Standard Dev Doc Sections

The generated `dev_doc.md` must contain these sections in this order:

1. Project Overview
2. Source Tables
3. Target Tables
4. Field Dictionary
5. Field Mapping
6. Data Processing Flow
7. KPI / Calculation Logic
8. Write Strategy
9. Scheduling And Rerun
10. Parameter Design
11. Log Verification Plan
12. Open Questions

## Workflow

1. Inspect the input path and confirm the DOCX exists.
2. Run `scripts/extract_docx_bundle.py`:

```powershell
python .\skills\data-doc-to-dev-md\scripts\extract_docx_bundle.py `
  --docx ".\doc\example.docx" `
  --out ".\outputs\example"
```

3. Review `extracted/extracted_document.md` and the CSV files.
4. Review `dev_doc/structured_facts.json` before code generation. For COT-style sync docs, this file should contain source/target report rows, Data Utilization names, target mappings, schedules, and field dictionaries.
5. Use `assets/dev_doc_template.md` as the final document shape.
6. Move ambiguous points into `questions.md`; do not hide uncertainty in prose.

## Quality Bar

- For COT/data-sync documents, `dev_doc.md` is not good enough if it only lists embedded CSV filenames. It must expose the sync matrix: source table, target table, field dictionary, schedule, target prefixes, and unresolved rowkey/table exception questions.
- For report documents, `dev_doc.md` must expose target output fields and calculation/filter/join facts well enough for `report-codegen` to implement output-equivalent logic without reopening the original DOCX. If field rules live in Word正文表格 such as `字段名 / 字段key / 数据源位置 / 数据表 / 数据源对应的字段 / 计算逻辑`, they must be extracted into `report_field_mappings`.
- Treat `structured_facts.json` as the handoff artifact for codegen skills whenever it exists.

## Reference Loading

- Read `references/docx_rules.md` before changing extraction behavior.
- Use `assets/dev_doc_template.md` whenever generating or revising a development document.
