---
name: pipeline-excel-builder
description: Use when generating, filling, or validating DataHub/DataEngine Pipeline Export Excel workbooks from waterline design documents, PRDs, extracted structured facts, or an empty Pipeline Export template.
---

# Pipeline Excel Builder

Use this skill when the user needs a DataHub/DataEngine Pipeline Export Excel workbook for waterline setup, project migration, target registration, target fields, pipeline tasks, schedules, or platform import review.

## Scope

- Primary source of truth: a waterline/DataEngine design document and `structured_facts.json` produced by `data-doc-to-dev-md`.
- Required Excel base: an exported empty Pipeline workbook from the target platform/project.
- Production Pipeline Excel exports may be inspected as local examples, but do not copy project-specific owners, emails, MLP params, schedules, secrets, or internal links into a new project unless explicitly confirmed.
- This skill only creates or validates Excel files. It does not connect to DataHub, create platform objects, or run imports.

## Inputs

- Required: empty Pipeline Export Excel template.
- Required: `structured_facts.json` from `data-doc-to-dev-md`.
- Strongly recommended: original waterline/DataEngine DOCX and PRD for conflict review.
- Optional: expected project name, expected Data Utilization name, known owner/email/catalog values, confirmed pipeline schedules, confirmed task-target links.

## Outputs

- Filled source Pipeline Export Excel workbook. By default, fill the user-provided workbook in place.
- `questions.md` listing conflicts, missing values, and fields intentionally left blank.
- `validation.json` from `scripts/validate_pipeline_excel.py`.
- A short review summary: row counts, required-column status, warnings, and remaining manual checks.

## Workflow

1. If only DOCX files are provided, first run `data-doc-to-dev-md/scripts/extract_docx_bundle.py` to create `structured_facts.json`.
2. Read `references/pipeline_export_schema.md` before writing or validating Excel.
3. Read `references/fill_rules.md` before mapping facts into workbook rows.
4. Inspect the empty template workbook and verify it has the fixed sheets:
   - `Readme`
   - `Data Utilization`
   - `Target & Catalog`
   - `Target Field`
   - `Pipeline`
5. Generate the workbook with:

```powershell
python skills\pipeline-excel-builder\scripts\build_pipeline_excel.py `
  --template-xlsx "<empty export.xlsx>" `
  --structured-facts "<structured_facts.json>" `
  --questions-out "<questions.md>" `
  --project-name "<PROJECT_NAME>"
```

6. Validate the filled workbook:

```powershell
python skills\pipeline-excel-builder\scripts\validate_pipeline_excel.py `
  --xlsx "<filled export.xlsx>" `
  --json-out "<validation.json>"
```

7. Review `questions.md` with the user before treating the workbook as import-ready.

## Hard Constraints

- Use the user's empty template as the workbook base. Do not rebuild the workbook from scratch unless the user explicitly asks.
- Fill the user-provided Pipeline Export workbook in place by default. Only write a separate workbook when the user explicitly asks or `--out-xlsx` is provided.
- Only write data rows from row 3 onward in the four data sheets. Preserve `Readme`, headers, merged cells, column widths, row heights, and styles.
- When refilling a workbook that already has data rows, preserve existing row order by sheet key and append only new inferred rows.
- Do not guess owner, email, catalog registration values, MLP params, task-target links, credentials, URLs, or platform-specific IDs.
- When catalog owner/name values are derived from emails, fill owner/name columns with person-style names without digits; keep full addresses only in email columns.
- Fill catalog registration only for project-owned/report output tables; leave shared/reference table catalog columns blank unless explicitly confirmed.
- Fill `Target & Catalog.dataset_name` and `dataset_title` with the catalog data item name, and `dataset_description` with the catalog title/description.
- Fill every `Target Field` row's `*field_label` with the same value as `*field_name`; put Chinese/business text in `field_description`.
- Fill every `Target Field` row's `*field_type` as the fixed workbook value `TEXT`, regardless of the source document field type.
- Fill every `Target Field` row's `field_length` as the fixed text value `200`.
- Leave all Pipeline timing columns blank: `pipeline_trigger`, `pipeline_trigger_start`, and `pipeline_trigger_end`.
- Leave `pipeline_status_notification` blank for generated rows unless explicitly confirmed.
- Keep only Pipeline rows with high-confidence `task1_link_target_names`; infer links from exact target/table names, project-prefix-stripped aliases, and clear period groups.
- Save text cells in shared-string form (`xl/sharedStrings.xml`, `t="s"`), matching production exports; avoid `inlineStr` cells.
- Prefer technical DataEngine/waterline document facts over PRD facts for target names, storage, table names, field names, and schedules.
- If the document contains conflicting target counts or duplicate field dictionaries, generate the higher-confidence rows and record the conflict in `questions.md`.
- Do not commit local template Excel files, production exports, generated outputs, or source documents to Git.

## Handoff Standard

Before handing off a filled workbook, report:

- Workbook path.
- Data row counts for `Data Utilization`, `Target & Catalog`, `Target Field`, and `Pipeline`.
- Validation result and warning count.
- Any fields intentionally left blank.
- Whether the workbook has only been locally filled or has also been manually reviewed/imported.
