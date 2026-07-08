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

- Filled Pipeline Export Excel workbook.
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
  --out-xlsx "<output.xlsx>" `
  --questions-out "<questions.md>" `
  --project-name "<PROJECT_NAME>"
```

6. Validate the generated workbook:

```powershell
python skills\pipeline-excel-builder\scripts\validate_pipeline_excel.py `
  --xlsx "<output.xlsx>" `
  --json-out "<validation.json>"
```

7. Review `questions.md` with the user before treating the workbook as import-ready.

## Hard Constraints

- Use the user's empty template as the workbook base. Do not rebuild the workbook from scratch unless the user explicitly asks.
- Only write data rows from row 3 onward in the four data sheets. Preserve `Readme`, headers, merged cells, column widths, row heights, and styles.
- Do not guess owner, email, catalog registration values, MLP params, task-target links, credentials, URLs, or platform-specific IDs.
- When catalog owner/name values are derived from emails, fill owner/name columns with person-style names without digits; keep full addresses only in email columns.
- Leave all Pipeline timing columns blank: `pipeline_trigger`, `pipeline_trigger_start`, and `pipeline_trigger_end`.
- Prefer technical DataEngine/waterline document facts over PRD facts for target names, storage, table names, field names, and schedules.
- If the document contains conflicting target counts or duplicate field dictionaries, generate the higher-confidence rows and record the conflict in `questions.md`.
- Do not commit local template Excel files, production exports, generated outputs, or source documents to Git.

## Handoff Standard

Before handing off a generated workbook, report:

- Workbook path.
- Data row counts for `Data Utilization`, `Target & Catalog`, `Target Field`, and `Pipeline`.
- Validation result and warning count.
- Any fields intentionally left blank.
- Whether the workbook has only been locally generated or has also been manually reviewed/imported.
