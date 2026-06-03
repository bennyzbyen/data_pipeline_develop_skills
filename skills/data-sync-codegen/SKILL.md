---
name: data-sync-codegen
description: Generate or review portable Python DataEngine data synchronization project code from AI-readable development docs, especially COT yearly sync work where sync logic stays stable and source tables, target tables, fields, rowkeys, period ranges, and runtime parameters change. Uses bundled sync patterns and templates first, with local production samples only as optional extra references, and keeps credentials as placeholders.
---

# Data Sync Codegen

Use this skill when the user asks to generate, review, or modify Python code for data synchronization jobs between MySQL, Blob, FS, HBase, and ClickHouse in DataEngine/DataHub-style projects.

## Scope

- Primary source of truth: bundled `references/cot_sync_patterns.md` and `assets/minimal_sync_project/`.
- Optional extra reference: `prod_code_sample/cot_202604101607` when it exists in the current workspace.
- Assume the COT synchronization logic is usually stable; most yearly changes are table lists, fields, parameters, target tables, rowkey rules, and period ranges.
- Fixed platform package directories: `gateway/`, `hbase/`, `fs/`. Do not generate business logic in them or overwrite existing package files; only keep existing packages or create minimal placeholders when the target project does not have the fixed package installed/copied yet.
- Credentials, IPs, tokens, app keys, and app secrets must remain placeholders unless the user supplies real values and explicitly asks to insert them.
- Do not connect to databases or production services.

## Inputs

- Required: `dev_doc.md` or equivalent structured requirement.
- Required: target project directory already created by the user.
- Strongly recommended: `structured_facts.json` from `data-doc-to-dev-md` when it exists.
- Optional: current params JSON, target table list, rowkey rules, period/full/delta sync list, existing code to modify.

## Outputs

- Python sync project files in the target project directory.
- `params.example.json` with placeholder secrets.
- `cot_config/rowkey_config.py` with fill-in comments for HBase rowkey confirmation and post-generation edits.
- Self-contained scaffold files copied from `assets/minimal_sync_project/` when the target project has no established implementation.
- A verification note explaining local static checks and deployment log checks.
- Optional runtime-semantics report from `scripts/verify_cot_runtime_semantics.py`.
- A risk list covering table/schema assumptions, rowkey assumptions, and rerun behavior.

## Workflow

1. Read `references/cot_sync_patterns.md`.
2. If `structured_facts.json` exists, load it before writing code and use it as the source/target/table/schedule matrix.
3. Prefer `scripts/scaffold_cot_sync_project.py` for COT yearly sync scaffolding. Pass `--structured-facts`, `--output-dir`, and optionally `--extracted-tables` when embedded CSV field dictionaries are available from document extraction.
4. Use `assets/minimal_sync_project/` as the fallback scaffold if the script is not appropriate.
5. If `prod_code_sample/cot_202604101607` exists, inspect it only as optional workspace-local guidance or regression comparison after the blind generation step; never require it.
6. Inspect the target project directory before editing.
7. State planned file modifications, reasons, and risks.
8. Generate minimum necessary files following the COT shape; prefer bundled scaffold modules over copying from samples.
9. Keep business-specific logic in config modules where possible.
10. Verify with syntax checks only unless the user provides a safe local runtime.
11. For generated COT scaffold projects, run `scripts/verify_cot_runtime_semantics.py --project-dir <target>` to check dispatch defaults, with-period rerun behavior, incremental timestamp updates, no-change exits, and write ordering without connecting to external services.

## Output-Equivalence Standard

Generated code may be simpler than the production sample, but it must preserve these output semantics:

- the same source table is exported for the selected task
- the same HBase and ClickHouse target names are used
- the same with-period or without-period branch is selected
- the same rowkey columns and rowkey prefix rule are used for HBase
- the same ClickHouse delete/drop/truncate rule is used before insert
- manual period reruns do not advance the stored timestamp
- automatic incremental runs update the stored timestamp only after successful writes
- returned DataEngine metrics include source, HBase target, ClickHouse target, row counts, and status

## Hard Constraints

- Do not overwrite user code without reading it first.
- Do not add new dependencies unless explicitly approved.
- Do not fill real credentials.
- Do not guess HBase rowkey rules. Generate or preserve `cot_config/rowkey_config.py`, keep `confirmed = False` until verified, and sync confirmed changes back to `plugin_config.py` or runtime params before deployment.
- Do not modify fixed platform package implementations under `gateway/`, `hbase/`, or `fs/`; source/target/table-specific logic belongs in COT modules and config.
- Do not widen scope into report KPI development; use `report-codegen` for report projects.
- Do not fail just because `prod_code_sample` or the supervisor portal repository is unavailable; fall back to bundled assets and references.
- Do not encode absolute `skill_lab`, `doc`, `outputs`, or `prod_code_sample` paths into generated project files.
- Do not claim runtime parity unless the generated project passes the fake runtime semantics verifier or equivalent deployment-log evidence.
