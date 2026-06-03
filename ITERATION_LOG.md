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
