# Data Development Codex Skills Iteration Log

## Purpose

This file is the persistent maintenance log for the data-development Codex Skills in `D:\Benny\skill_lab`.

Use it to record:

- Skill baseline status
- Sample projects used for iteration
- Blind-generation comparison results
- Skill/reference/script/template changes
- Regression verification
- Deployment sync status
- Remaining risks and follow-up work

This file is **not** a runtime dependency of any skill.

## 2026-07-08 - Pipeline Excel Builder Skill

### Objective

- Add `pipeline-excel-builder` for generating DataHub/DataEngine Pipeline Export Excel workbooks from waterline design documents.
- Use the QAS abnormal-data project as the first acceptance sample.

### Inputs

| Type | Path |
| --- | --- |
| Waterline document | `doc/QAS(六真) Data Engine水线文档.docx` |
| PRD | `doc/26028 QAS(六真) PRD.docx` |
| Empty target template | `templates/uat_[QAS_Abnormal_Data]_Pipeline_Export_File_20260708105821.xlsx` |
| Production schema examples | `templates/prod_[cot_2026]_Pipeline_Export_File_20260708114242.xlsx`, `templates/prod_[Execute_King_2025]_Pipeline_Export_File_20260708114300.xlsx`, `templates/prod_[fos_vehicle_verification]_Pipeline_Export_File_20260708114318.xlsx` |

### Changes

| File | Change |
| --- | --- |
| `skills/pipeline-excel-builder/SKILL.md` | Added the new skill contract, workflow, inputs/outputs, and hard constraints |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py` | Added workbook generator from `structured_facts.json` and an empty Pipeline Export workbook |
| `skills/pipeline-excel-builder/scripts/validate_pipeline_excel.py` | Added workbook schema, required-column, reference, type, and warning validation |
| `skills/pipeline-excel-builder/references/pipeline_export_schema.md` | Documented fixed sheets, headers, storage types, and field type mappings |
| `skills/pipeline-excel-builder/references/fill_rules.md` | Documented conservative fill rules and question generation policy |
| `deploy_skills.ps1` | Added `pipeline-excel-builder` to the default sync list |
| `.gitignore` | Added `templates/` so production Excel exports remain local-only |

Follow-up hardening:

| File | Change |
| --- | --- |
| `skills/data-doc-to-dev-md/scripts/extract_docx_bundle.py` | Added `report_catalog_basic_info` extraction from Catalog Basic Info tables with `数据项 / Title / owner email` columns |
| `skills/data-doc-to-dev-md/references/docx_rules.md` | Documented Catalog Basic Info table recognition for report development documents |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py` | Fills `data_utilization_description` from waterline Data Utilization Management and fills catalog registration fields from `report_catalog_basic_info` |
| `skills/pipeline-excel-builder/scripts/validate_pipeline_excel.py` | Warns if owner/name columns contain email addresses or digits |
| `skills/pipeline-excel-builder/SKILL.md` and `references/fill_rules.md` | Require owner/name columns to use person-style names without digits; email addresses stay in email columns |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py` and `scripts/validate_pipeline_excel.py` | Leave Pipeline timing columns blank for every row and stop warning on blank `pipeline_trigger` |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py`, `scripts/validate_pipeline_excel.py`, and references | Fill every `Target Field.*field_type` as fixed `TEXT` and reject non-`TEXT` values |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py`, `scripts/validate_pipeline_excel.py`, and references | Store `Target Field.field_sequence` as text instead of numeric cells, matching production exports |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py`, `scripts/validate_pipeline_excel.py`, and references | Remove blank data cells from workbook XML instead of writing empty inline strings, matching production exports for Pipeline timing columns |
| `skills/pipeline-excel-builder/scripts/build_pipeline_excel.py`, `scripts/validate_pipeline_excel.py`, and references | Convert saved text cells from `inlineStr` to shared-string references (`xl/sharedStrings.xml`, `t="s"`) because the platform importer missed `Data Utilization` names stored as inline strings |

### Verification

- Generated QAS output:
  - `outputs/pipeline_excel_builder_qas_round1/QAS_Abnormal_Data_Pipeline_Export_File.xlsx`
  - `outputs/pipeline_excel_builder_qas_round1/questions.md`
  - `outputs/pipeline_excel_builder_qas_round1/validation.json`
- Acceptance result:
  - `Data Utilization`: 1 generated row.
  - `Target & Catalog`: 11 generated rows.
  - `Target Field`: 291 generated rows from QAS field mappings.
  - `Pipeline`: 5 generated rows.
  - Validator result: pass, 0 errors.
  - `data_utilization_description` is filled as `六真异常数据`.
  - Catalog registration fields are filled for 11 QAS targets from Catalog Basic Info.
  - Owner/name columns use person-style names without digits, for example `tracy.zhang1@effem.com` -> `Tracy Zhang`.
  - Pipeline timing columns are intentionally blank: `pipeline_trigger`, `pipeline_trigger_start`, and `pipeline_trigger_end`.
  - Target Field `*field_type` is intentionally fixed to `TEXT` for every generated field row.
  - Target Field `field_sequence` is stored as text strings such as `0`, `1`, `2`, not numeric cells.
  - Blank optional cells are absent/null in workbook XML, not empty inline string cells.
  - Workbook text cells use shared strings (`xl/sharedStrings.xml`); XML check found `inlineStr` count `0`, and `Data Utilization!A3` is stored as `t="s"`.
  - Regression validation passed on three production Pipeline exports with the new shared-string validator rule.
  - Conservative blanks remain as warnings/questions: `clickhouse_soldto_details_p` field dictionary, task-target links, MLP params, and QAS document conflicts.
- Schema regression:
  - `prod_[cot_2026]_Pipeline_Export_File_20260708114242.xlsx`: pass, 0 errors.
  - `prod_[Execute_King_2025]_Pipeline_Export_File_20260708114300.xlsx`: pass, 0 errors.
  - `prod_[fos_vehicle_verification]_Pipeline_Export_File_20260708114318.xlsx`: pass, 0 errors.
  - `uat_[QAS_Abnormal_Data]_Pipeline_Export_File_20260708105821.xlsx`: pass, 0 errors.
- Skill validation:
  - `pipeline-excel-builder`: pass with `$env:PYTHONUTF8 = '1'; python quick_validate.py`.
  - `data-doc-to-dev-md`: pass with `$env:PYTHONUTF8 = '1'; python quick_validate.py`.

### Remaining Risks

- The generated workbook is a pre-import review artifact; DataHub import success still requires manual confirmation of blank task-target links, MLP params, `clickhouse_soldto_details_p` fields, and any schedule setup that must be handled outside the generated timing columns.
- Production Excel samples are intentionally not committed to Git.

## 2026-07-03 - bySKU Report Pipeline Handoff Hardening

### Sample

- Documents:
  - `doc/25053 FoS - HQ BI 执行为王新品+B5数据 PRD.docx`
  - `doc/执行为王 Data Engine 设计文档.docx`
- Production code:
  - `prod_code_sample/datahub_executing_king`

### RED Baseline

- `data-doc-to-dev-md` extracted the two documents, but `report-codegen` classified the generated plan as `standard_report`.
- Baseline `structured_facts.json` had `report_sources`, `report_targets`, and many `report_field_mappings`, but no `report_physical_targets`.
- NPD/B5 target names were represented as multi-table strings, which made field dictionary to output-table mapping unsafe.
- Field-rule parsing missed common bySKU report column names such as `数据源表`, `数据源字段key`, and `报表字段逻辑`.

### Changes

- Added generic bySKU report DOCX handoff rules:
  - `skills/data-doc-to-dev-md/references/bysku_report_doc_rules.md`
- Added generic bySKU report/codegen patterns:
  - `skills/report-codegen/references/bysku_report_pipeline_patterns.md`
- Added generic bySKU report log diagnosis reference:
  - `skills/data-job-log-debugger/references/bysku_report_failure_modes.md`
- Updated `data-doc-to-dev-md` extractor:
  - emits `component_hints` with `component_kind = bysku_report_pipeline`
  - infers NPD/B5 ClickHouse physical targets as confirmation-required only when document/sample evidence supports them
  - emits `handoff_readiness` with blocked checks when output field dictionaries or FS/SKU/write contracts are incomplete
  - maps `store_np_sku_details` and `store_b5_sku_details` field dictionaries to physical tables when headings prove the table
  - recognizes additional source/logic field aliases
- Updated `report-codegen` plan builder:
  - consumes `component_hints` and `handoff_readiness`
  - classifies bySKU report pipelines as `bysku_report_pipeline`
  - prefers exact field-mapping physical table matches before description fallbacks
- Updated skill contracts:
  - `data-sync-codegen` routes bySKU report pipelines to `report-codegen`
  - `report-codegen` reads bySKU report pipeline patterns and respects blocked handoff readiness
  - `data-job-log-debugger` reads bySKU report failure modes and compares logs with manifest/plan evidence when provided

### Verification

- Re-ran extraction on the two bySKU/Executing King sample documents.
- Rebuilt report plan from the new `structured_facts.json`.
- Result:
  - `component_kind = bysku_report_pipeline`
  - `component_hints = 1`
  - `physical_targets = 6`
  - `ready_for_full_codegen = False`, intentionally blocked because summary/ttl field dictionaries and FS/SKU/write contracts still require confirmation
  - field parsing improved to `source_field_nonempty = 862 / 885`, `calculation_logic_nonempty = 455 / 885`
  - NPD and B5 detail mappings now resolve to distinct physical tables:
    - `store_np_sku_details -> supervisor_dashboard.store_np_sku_details`
    - `store_b5_sku_details -> supervisor_dashboard.store_b5_sku_details`

## Repository Role

| Path | Role |
| --- | --- |
| `D:\Benny\skill_lab` | Skill development, sample analysis, regression, deployment sync |
| `D:\Benny\skill_lab\skills` | Source-of-truth skill directories |
| `D:\Benny\skill_lab\doc` | High-quality requirement document samples |
| `D:\Benny\skill_lab\prod_code_sample` | High-quality production code samples for comparison |
| `D:\Benny\skill_lab\outputs` | Blind generation, diff, verifier, and regression outputs |
| `C:\Users\51217\.codex\skills` | Codex runtime skill install directory |

## Baseline: 2026-06-02

### Skills

| Skill | Current Scope | Baseline Status |
| --- | --- | --- |
| `data-doc-to-dev-md` | Convert PRD/DataEngine/DataHub/COT/report DOCX documents into AI-readable development docs | MVP usable |
| `data-sync-codegen` | Generate COT/DataEngine data sync Python project code from `dev_doc.md` / `structured_facts.json` | MVP usable for COT-style sync |
| `report-codegen` | Generate DataEngine report project code with `DataSource / DataProcess / DataStorage` | About 80% usable for supervisor/vehicle-style reports |
| `data-job-log-debugger` | Diagnose deployed DataEngine/DataHub job failures from full logs or screenshots | MVP usable for common failures |
| `pipeline-excel-builder` | Generate and validate DataHub/DataEngine Pipeline Export Excel workbooks from waterline docs and structured facts | MVP in progress with QAS acceptance sample |

### Key Design Decisions

- `skill_lab` is the maintenance and regression workspace.
- `.codex\skills` is the runtime install location used by Codex.
- `doc/`, `prod_code_sample/`, and `outputs/` must not be synced into `.codex\skills`.
- New real projects should not depend on `skill_lab/prod_code_sample`.
- `gateway/`, `hbase/`, and `fs/` are fixed platform package directories.
- Skill-generated code must not put business logic into `gateway/`, `hbase/`, or `fs/`.
- Existing fixed platform package files must not be overwritten.
- Credentials, IPs, tokens, app keys, and app secrets remain placeholders by default.
- Local validation is syntax/static/fake-runtime only.
- Final correctness still depends on deployment logs and actual output data.

## Baseline Verification

### `data-doc-to-dev-md`

Confirmed capabilities:

- DOCX body extraction
- Embedded Excel extraction
- `dev_doc.md` generation
- `structured_facts.json` generation
- `questions.md` generation

Known limitation:

- Needs more document samples to improve recognition across different PRD/DataEngine formats.

### `data-sync-codegen`

Confirmed capabilities:

- COT-style sync scaffold
- COT sync pattern reference
- Fixed platform package boundary for `gateway/`, `hbase/`, `fs/`
- Runtime semantics verifier for generated COT scaffold

Regression result:

| Check | Result |
| --- | --- |
| COT runtime verifier | Pass |
| Verifier case count | `6` |

### `report-codegen`

Confirmed capabilities:

- Supervisor portal style report scaffold
- Vehicle verification style complex report scaffold
- `DataSource / DataProcess / DataStorage` project structure
- Fixed platform package boundary for `gateway/`, `hbase/`, `fs/`
- Runtime semantics verifier for supervisor portal projects
- Runtime semantics verifier for vehicle verification projects

Regression result:

| Check | Result |
| --- | --- |
| Supervisor portal runtime verifier | Pass |
| Vehicle verification runtime verifier | Pass |
| Supervisor portal output table count | `7` |
| Vehicle verification output types | detail, presale summary, instock summary |

### `data-job-log-debugger`

Confirmed failure classes:

| Failure Class | Status |
| --- | --- |
| ClickHouse unknown table / cluster | Covered |
| Gateway / HBase / FS permission or connection issue | Covered |
| No changed data | Covered |
| Missing params / wrapped single params | Covered |
| Missing rowkey column | Covered |

## Deployment Sync

Deployment script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Benny\skill_lab\deploy_skills.ps1"
```

Installed target:

```text
C:\Users\51217\.codex\skills
```

First sync date:

```text
2026-06-02
```

First sync verification:

| Skill | Source Files | Target Files | `SKILL.md` | `agents/openai.yaml` |
| --- | ---: | ---: | --- | --- |
| `data-doc-to-dev-md` | 5 | 5 | Present | Present |
| `data-sync-codegen` | 26 | 26 | Present | Present |
| `report-codegen` | 23 | 23 | Present | Present |
| `data-job-log-debugger` | 4 | 4 | Present | Present |

## Standard Iteration Workflow

Use this workflow when a new sample document/code/log is added.

1. Read new sample paths.
2. Generate development docs with `data-doc-to-dev-md`.
3. Blind-generate code from `dev_doc.md` / `structured_facts.json`.
4. Read the matching production sample after blind generation.
5. Compare generated output against production sample.
6. Identify gaps in the skill, reference docs, scripts, or templates.
7. Make the smallest necessary skill changes.
8. Run relevant syntax checks and fake runtime verifiers.
9. Run `deploy_skills.ps1`.
10. Append an entry to this log.

Comparison checklist:

- Output tables
- Output columns
- Column order
- Source filters
- Join keys and join direction
- KPI formulas
- Null/default behavior
- Rowkey rules
- Parameter design
- Write/delete/replace strategy
- Logging behavior
- Deployment validation evidence

## Current Known Risks

- Fake runtime verification is not a replacement for deployment validation.
- Real environment package availability is still required for `gateway/`, `hbase/`, and `fs/`.
- Real credentials and runtime paths must be filled by the user.
- New report types may require additional KPI/join/default-value rules.
- DOCX extraction rules need more samples to generalize.
- Screenshot-based debugging is less reliable than complete text logs.

## Non-Synced Maintenance Artifacts

These artifacts currently exist or may exist under `outputs/` and are not synced by `deploy_skills.ps1`:

- `outputs\tmp_vehicle_runtime_compare.py`
- `outputs\tmp_vehicle_runtime_compare.json`
- `__pycache__` directories
- `.pyc` files

`deploy_skills.ps1` excludes `__pycache__` and `.pyc` files by default.

## Iteration Entry Template

```markdown
## Iteration: YYYY-MM-DD - <short-name>

### Objective

- 

### Inputs

| Type | Path |
| --- | --- |
| Requirement doc |  |
| Production sample |  |
| Logs |  |

### Target Skills

- 

### Blind Generation Output

- 

### Comparison Findings

| Finding | Impact | Skill Gap |
| --- | --- | --- |
|  |  |  |

### Changes

| File | Change |
| --- | --- |
|  |  |

### Verification

| Check | Result |
| --- | --- |
|  |  |

### Deployment Sync

- Command:
- Result:

### Remaining Risks

- 
```

## Iterations

### 2026-07-03 - Gateway FS HBase Production Usage Hardening

Objective:

- Learn common `gateway`, `fs`, and `hbase` usage from `prod_code_sample`.
- Steer generated sync/report code toward production-common facade calls and away from uncommon low-level package APIs.
- Keep fixed platform package implementations unchanged.

Inputs:

| Type | Path |
| --- | --- |
| Production samples | `prod_code_sample/` |
| COT regression facts | `outputs/cot_regression_after_supervisor_round4/dev_doc/structured_facts.json` |
| Supervisor regression project | `outputs/supervisor_portal_blind_codegen_round6/project` |
| Vehicle regression project | `outputs/vehicle_blind_codegen_round7/project` |
| Fos HBase prepare project | `outputs/fos_store_dts_iter6/project` |

Findings:

| Finding | Impact | Skill Gap |
| --- | --- | --- |
| Business code normally uses `Client` or `GateWayClient` facade before HBase/FS access | Generated code should not call Gateway token/header/API helpers directly | Needed explicit facade-first rules |
| FS business usage is mostly `exists`, `listdir`, `copy_to_local`, and `copy_from_local(..., overwrite=True)` | Codex can overuse low-level or uncommon FS functions | Needed default/avoid lists |
| HBase business usage is mostly `query_df`, `insert_df(mode="import")`, `insert_file(..., sep="\x1D")`, `delete_df`, and explicit `truncate` | Codex can choose incomplete or uncommon functions such as `mode="insert"` or `HbaseClient.delete(...)` | Needed HBase operation selection rules |
| Sync template initialized HBase without `fs_root_dir` and used `fs_client.mkdir` for initial timestamp setup | Generated COT scaffold drifted from production-common FS/HBase usage | Needed template correction |

Changes:

| File | Change |
| --- | --- |
| `skills/data-sync-codegen/references/platform_client_usage.md` | Added gateway/FS/HBase facade-first usage rules, default operations, rowkey naming, and avoid list |
| `skills/report-codegen/references/platform_client_usage.md` | Added report-oriented gateway/FS/HBase usage rules with local fake-runtime injection guidance |
| `skills/data-sync-codegen/SKILL.md` | Added the platform usage reference as required reading before generating `gateway`/`fs`/`hbase` code |
| `skills/report-codegen/SKILL.md` | Added the platform usage reference as required reading before generating `gateway`/`fs`/`hbase` code |
| `skills/data-sync-codegen/references/cot_sync_patterns.md` | Added platform package usage rules and HBase write cautions |
| `skills/report-codegen/references/supervisor_portal_patterns.md` | Added platform package usage rules |
| `skills/report-codegen/references/vehicle_verification_patterns.md` | Added vehicle/report FS/HBase usage constraints |
| `skills/data-sync-codegen/assets/minimal_sync_project/plugin_common.py.template` | Passes `fs_root_dir` to `getHbaseClient` and no longer creates/uploads an initial remote timestamp file during timestamp fetch |

Verification:

| Check | Result |
| --- | --- |
| Read-only subagent audits for FS, Gateway, HBase | Pass |
| Skill creator quick validation for all 4 skills | Pass |
| Skill script `py_compile` | Pass |
| COT scaffold generation from regression facts | Pass |
| Generated COT scaffold compile | Pass |
| Generated COT runtime verifier | Pass, 6 cases |
| Supervisor portal runtime verifier | Pass |
| Vehicle verification runtime verifier | Pass |
| Fos HBase prepare project compile/static platform-call scan | Pass |
| Deploy dry run | Pass |

Notes:

- `verify_report_runtime_semantics.py` currently supports only `supervisor_portal` and `vehicle_verification`; it does not expose an `hbase_prepare_pipeline` project type. Fos HBase prepare validation used compile/static checks in this iteration.

### 2026-07-03 - Skill Trigger And Credential Handling Hardening

Objective:

- Strengthen trigger descriptions and shared operating constraints for the four data-development skills.
- Clarify that existing code, logs, documents, and production samples may contain database connection strings, Gateway app keys, app secrets, hosts, ports, URLs, or tokens.
- Keep new generated examples/templates/docs placeholder-safe without refusing in-scope work on existing files that already contain credentials.

Target skills:

- `data-doc-to-dev-md`
- `data-sync-codegen`
- `report-codegen`
- `data-job-log-debugger`

Changes:

| File | Change |
| --- | --- |
| `skills/data-doc-to-dev-md/SKILL.md` | Changed frontmatter description to `Use when...`, added sensitive evidence handling, and strengthened `structured_facts.json` handoff expectations |
| `skills/data-sync-codegen/SKILL.md` | Changed frontmatter description to `Use when...` and replaced absolute credential placeholder wording with preserve-existing / placeholder-new rules |
| `skills/report-codegen/SKILL.md` | Changed frontmatter description to `Use when...` and replaced absolute credential placeholder wording with preserve-existing / placeholder-new rules |
| `skills/data-job-log-debugger/SKILL.md` | Changed frontmatter description to `Use when...` and added log/screenshot credential handling guidance |
| `skills/data-sync-codegen/references/cot_sync_patterns.md` | Clarified generated scaffold credential handling and verification wording |
| `skills/report-codegen/references/supervisor_portal_patterns.md` | Clarified generated scaffold credential handling and verification wording |

Verification:

| Check | Result |
| --- | --- |
| Skill creator quick validation for all 4 skills | Pass |
| Skill script `py_compile` | Pass |
| Deploy dry run | Pass |
| Residual absolute credential-ban wording scan | Pass |

Remaining risks:

- This iteration only hardens trigger/instruction wording. It does not add automated lint rules for future skill wording regressions.

### 2026-06-03 - HBase Rowkey Confirmation Config

Objective:

- Add an explicit post-fill surface for HBase rowkey rules in generated data-sync and report projects.
- Keep rowkey generation conservative: provide candidates and fill comments, but do not mark rowkeys as production-confirmed without docs/code/log evidence.

Inputs:

| Type | Path |
| --- | --- |
| Report regression plan | `outputs/fos_store_dts_iter6/plan/report_codegen_plan.json` |
| COT regression facts | `outputs/cot_regression_after_supervisor_round4/dev_doc/structured_facts.json` |
| Supervisor regression project | `outputs/supervisor_portal_blind_codegen_round6/project` |
| Vehicle regression project | `outputs/vehicle_blind_codegen_round7/project` |

Changes:

| File | Change |
| --- | --- |
| `skills/report-codegen/scripts/scaffold_report_project.py` | Generates `params_configs/rowkey_config.py` for HBase outputs, with inferred candidates, blank confirmed `columns`, prefix/date/example placeholders, and fill notes |
| `skills/report-codegen/assets/minimal_report_project/params_configs/rowkey_config.py.template` | Added reusable report rowkey template with field-by-field comments |
| `skills/report-codegen/SKILL.md` | Added output contract and hard constraint for HBase rowkey confirmation |
| `skills/report-codegen/references/supervisor_portal_patterns.md` | Documented `params_configs/rowkey_config.py` as the report-side manual confirmation surface |
| `skills/data-sync-codegen/scripts/scaffold_cot_sync_project.py` | Generates `cot_config/rowkey_config.py` for COT HBase sync tables, using inferred rowkey candidates and `confirmed = False` |
| `skills/data-sync-codegen/assets/minimal_sync_project/cot_config/rowkey_config.py.template` | Added reusable COT rowkey template with runtime sync-back notes |
| `skills/data-sync-codegen/SKILL.md` | Added output contract and hard constraint for COT rowkey confirmation |
| `skills/data-sync-codegen/references/cot_sync_patterns.md` | Documented COT rowkey config and the need to copy confirmed values back to runtime config/params |

Generated outputs:

| Output | Path |
| --- | --- |
| Fos rowkey test project | `outputs/rowkey_enhancement_fos/project` |
| COT rowkey test project | `outputs/rowkey_enhancement_cot/project` |
| Supervisor verifier output | `outputs/rowkey_enhancement_fos/supervisor_portal_runtime_semantics.json` |
| COT verifier output | `outputs/rowkey_enhancement_cot/runtime_semantics.json` |

Verification:

| Check | Result |
| --- | --- |
| Skill script `py_compile` | Pass |
| Fos report scaffold generation | Pass, generated `params_configs/rowkey_config.py` |
| Fos generated rowkey config compile | Pass |
| COT sync scaffold generation | Pass, generated `cot_config/rowkey_config.py` |
| COT generated rowkey config compile | Pass |
| COT runtime verifier | Pass |
| Supervisor portal runtime verifier | Pass |
| Vehicle verification runtime verifier | Pass |

Notes:

- `params_configs/rowkey_config.py` is a review/fill file for report projects and does not change generated runtime behavior by itself.
- `cot_config/rowkey_config.py` is also a review/fill file. COT runtime still reads rowkey columns from `plugin_config.py` or DataEngine runtime params, so confirmed values must be copied back before deployment.
- A first supervisor verifier run completed business execution but failed while writing `runtime_semantics_rowkey_regression.json` with `PermissionError`; the output file did not exist and the directory was normal. Re-running to `outputs/rowkey_enhancement_fos/supervisor_portal_runtime_semantics.json` passed.

### 2026-06-03 - Fos Store DTS HBase Prepare Pipeline

Objective:

- Use the new `Fos Store DTS Classification Data Engine 设计文档.docx` and production sample `prepare_data_202509051610` to improve report-development skills.
- Keep `vehicle_verification_202605221431` as the existing complex report regression reference.

Inputs:

| Type | Path |
| --- | --- |
| Requirement doc | `doc/Fos Store DTS Classification Data Engine 设计文档.docx` |
| Production sample | `prod_code_sample/prepare_data_202509051610` |
| Regression sample | `prod_code_sample/vehicle_verification_202605221431` |

Blind-generation finding:

- Before the iteration, `data-doc-to-dev-md` only extracted embedded Excel sheets from this DOCX.
- The key `3.1.1 Hbase: l1_cot.store_yield_grade_p` field matrix was in a Word正文 table, so `structured_facts.json` missed `report_field_mappings`.
- `report-codegen` then produced an empty generic scaffold with no real source/output rules.

Comparison findings:

| Finding | Impact | Skill Gap |
| --- | --- | --- |
| Source matrix lives in Word tables, not embedded Excel | Missing HBase source table list and field list | `data-doc-to-dev-md` needed Word table extraction |
| Target is HBase-only (`l1_cot.store_yield_grade_p`) | Existing report plan assumed ClickHouse physical targets | `build_report_codegen_plan.py` needed generic physical target support |
| Production component exports HBase source data to FS and optionally triggers DataHub pipeline | Generic scaffold incorrectly pointed toward ClickHouse `DataStorage` | `report-codegen` needed HBase prepare/pipeline scaffold mode |
| Production sample contains real app keys/API keys | Generated code must not copy secrets | Scaffold keeps placeholder config values |

Changes:

| File | Change |
| --- | --- |
| `skills/data-doc-to-dev-md/scripts/extract_docx_bundle.py` | Added Word table CSV export, Word field-table header detection, HBase physical target extraction, source/field mapping extraction from Word tables, and HBase-aware questions |
| `skills/data-doc-to-dev-md/SKILL.md` | Documented Word正文 tables as primary evidence |
| `skills/data-doc-to-dev-md/references/docx_rules.md` | Updated extraction priority and report matrix recognition rules for Word tables and HBase targets |
| `skills/report-codegen/scripts/build_report_codegen_plan.py` | Added `report_physical_targets`, HBase target matching, and `component_kind = hbase_prepare_pipeline` inference |
| `skills/report-codegen/scripts/scaffold_report_project.py` | Added HBase prepare/pipeline project generation: HBase period export to FS, optional pipeline activation, no-op DataStorage, and prepare-specific params |
| `skills/report-codegen/SKILL.md` | Added HBase-only prepare-data project rules and hard constraint not to force ClickHouse DataStorage |
| `skills/report-codegen/references/supervisor_portal_patterns.md` | Added HBase Prepare / Pipeline Pattern |

Generated outputs:

| Output | Path |
| --- | --- |
| Latest extracted dev doc | `outputs/fos_store_dts_iter6/dev_doc/dev_doc.md` |
| Latest structured facts | `outputs/fos_store_dts_iter6/dev_doc/structured_facts.json` |
| Latest report plan | `outputs/fos_store_dts_iter6/plan/report_codegen_plan.md` |
| Latest generated project | `outputs/fos_store_dts_iter6/project` |

Verification:

| Check | Result |
| --- | --- |
| Fos DOCX extraction | Pass, `embedded_sheets=7`, `word_tables=4` |
| Fos structured facts | Pass, 4 HBase sources, 1 HBase physical target, 1 output, 11 field rules |
| Fos plan component kind | Pass, `hbase_prepare_pipeline` |
| Fos generated project compile | Pass |
| Fos fake HBase prepare verification | Pass, period derivation/filter/group/export checked |
| COT runtime verifier | Pass |
| Supervisor portal runtime verifier | Pass |
| Vehicle verification runtime verifier | Pass |
| Log debugger regression | Pass, 5 cases |
| Skill script `py_compile` | Pass |
| Skill JSON parse | Pass |
| Skill secret scan | Pass |

Remaining risks:

- The generated Fos prepare scaffold matches the observed prepare-data component, but the downstream `cal_store_yield_grade` calculation/write remains pipeline-owned unless the downstream code is provided.
- Real deployment still needs fixed `gateway/`, `hbase/`, `fs/` packages and real placeholder replacement.
- HBase rowkey and downstream delete/overwrite behavior remain deployment/pipeline questions.

### 2026-07-01 - QAS Multi-DOCX PRD + Waterline Extraction

Objective:

- Strengthen `data-doc-to-dev-md` for projects where one requirement is split across a PRD and a DataEngine/waterline document.
- Use the QAS(六真) PRD and Data Engine waterline documents as the first multi-DOCX regression sample.
- Fix a COT2026 field-dictionary mismatch where `sixzhen_gps_distance` was mapped by sheet order to the wrong 43-field dictionary instead of the 51-field dictionary shown in the DOCX context.

Inputs:

| Type | Path |
| --- | --- |
| PRD | `doc/26028 QAS(六真) PRD.docx` |
| Waterline | `doc/QAS(六真) Data Engine水线文档.docx` |
| COT2026 | `D:\Benny\work code\datahub_cot2025\prd\COT2026同步数据到DataEngine的设计文档.docx` |

Findings:

| Finding | Impact | Skill Gap |
| --- | --- | --- |
| `extract_docx_bundle.py` accepted only one effective `--docx` value | PRD and waterline facts could not be merged into one codegen handoff | Needed native multi-DOCX aggregation |
| Many QAS field dictionaries start with `报表路由` / `数据表：qas_*` / `数据粒度` preamble rows | Only one field dictionary was recognized before this iteration | Needed delayed header detection in exported CSVs |
| Physical ClickHouse targets are in a Word table with `位置 / 数据库 / 数据表名 / 数据表` | `questions.md` falsely reported missing physical target tables | Needed Word target-matrix recognition |
| Target Management names use `clickhouse_qas_*`, while physical tables are `abnormal_monitor.qas_*` | Field dictionaries could be mapped to wrong targets by sheet order | Needed normalized target matching |
| PRD contains abnormal rules and KPI aggregation tables | `dev_doc.md` missed business/KPI logic needed by report codegen | Needed PRD rule matrix extraction |
| COT2026 field dictionaries are not always in Data Utilization order | `sixzhen_gps_distance` was mapped to `embedding_031` with `id / period / code` instead of `embedding_028` with `inksaa_id / period / store_code` | Needed embedding-object正文 context matching before order fallback |

Changes:

| File | Change |
| --- | --- |
| `skills/data-doc-to-dev-md/scripts/extract_docx_bundle.py` | Added repeated/multi-value `--docx`, per-document extraction folders, merged facts, provenance, delayed header detection, QAS physical target matching, PRD abnormal/KPI rule extraction, and tighter question generation |
| `skills/data-doc-to-dev-md/scripts/extract_docx_bundle.py` | Added embedding context extraction from `word/_rels/document.xml.rels` and正文 OLE placement; COT field dictionaries now prefer context-name matches before sheet-order fallback |
| `skills/data-doc-to-dev-md/scripts/verify_docx_bundle_multidoc.py` | Added standard-library regression fixtures for multi-DOCX extraction, delayed-header tables, and COT context-based field-dictionary matching |
| `skills/data-doc-to-dev-md/SKILL.md` | Documented multi-DOCX workflow, merged handoff expectations, and warning to review COT order fallback mappings |
| `skills/data-doc-to-dev-md/references/docx_rules.md` | Added multi-document precedence, delayed header, QAS target, PRD rule-matrix, and COT embedding-context rules |
| `skills/data-doc-to-dev-md/agents/openai.yaml` | Updated default prompt for multiple DOCX inputs |

Verification:

| Check | Result |
| --- | --- |
| Synthetic multi-DOCX regression | Pass |
| QAS single waterline extraction | Pass, `documents=1`, `embedded_sheets=18`, `word_tables=6` |
| QAS PRD + waterline extraction | Pass, `documents=2`, `embedded_sheets=38`, `word_tables=68` |
| QAS structured facts | Pass, `report_sources=26`, `report_targets=11`, `report_physical_targets=11`, `report_schedules=5`, `report_field_mappings=20`, `report_business_rules=8`, `report_kpi_rules=25`, `conflicts=7` |
| QAS dev doc content | Pass, contains `abnormal_monitor.qas_mw_visit_abnormal_store_daily`, `qas_feedback_detail`, and PRD abnormal/KPI rules |
| QAS questions | Pass, no false `报表物理目标表未识别` or ClickHouse-only `HBase rowkey` question |
| COT2026 `sixzhen_gps_distance` mapping | Pass, mapped to `embedding_028_sheet_001_M4DaN0.csv`, `row_count=51`, `inference_method=embedding_context`, first fields include `inksaa_id`, `period`, `store_code` |
| Skill script `py_compile` | Pass |
| Skill creator validation | Pass with `PYTHONUTF8=1` on Windows |

Remaining risks:

- `report_sources=26` includes PRD and waterline source evidence; codegen should deduplicate or prefer waterline source rows when generating runtime code.
- `conflicts=7` intentionally exposes PRD/waterline field-rule differences for review before code generation.
- The validator script under `.codex\skills\.system\skill-creator` uses platform default text encoding; on Windows, run it with `$env:PYTHONUTF8 = '1'` for UTF-8 skill files.

### 2026-06-02 - Baseline Build

Objective:

- Create and validate the first usable baseline for four data-development Codex Skills.
- Reach approximately 80% practical usability, with future improvements driven by real samples.

Target skills:

- `data-doc-to-dev-md`
- `data-sync-codegen`
- `report-codegen`
- `data-job-log-debugger`

Key changes:

- Created the four-skill split.
- Added structured doc extraction workflow.
- Added COT data sync codegen scaffold and verifier.
- Added supervisor portal and vehicle verification report scaffolds and verifiers.
- Added log debugging classifier and common failure mode reference.
- Added fixed platform package boundary rules for `gateway/`, `hbase/`, and `fs/`.
- Added `deploy_skills.ps1`.
- Added `使用教程.txt`.

Verification:

| Check | Result |
| --- | --- |
| COT runtime verifier | Pass |
| Supervisor portal runtime verifier | Pass |
| Vehicle verification runtime verifier | Pass |
| Log debugger regression | Pass |
| Skill script `py_compile` | Pass |
| Skill JSON parse | Pass |
| Secret scan | Pass |
| Deployment sync to `.codex\skills` | Pass |

Remaining risks:

- More production samples are needed for broader coverage.
- Real deployment logs are still required to validate production behavior.
- New project windows should be used for real project delivery; this window remains the skill maintenance thread.
