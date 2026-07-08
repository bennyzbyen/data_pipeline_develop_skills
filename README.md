# Data Pipeline Develop Skills

This repository maintains Codex Skills for Python data development workflows.

## Skills

- `data-doc-to-dev-md`: convert PRD/DataEngine/DataHub/COT/report DOCX documents into AI-readable development docs.
- `data-sync-codegen`: generate COT/DataEngine data synchronization project scaffolds.
- `report-codegen`: generate DataEngine report development project scaffolds.
- `data-job-log-debugger`: diagnose deployed DataEngine/DataHub job failures from logs or screenshots.
- `pipeline-excel-builder`: build DataHub/DataEngine Pipeline Export Excel workbooks from waterline documents.

## Repository Layout

```text
skills/              Source-of-truth skill directories
deploy_skills.ps1    Sync skills into the local Codex runtime skill directory
ITERATION_LOG.md     Engineering iteration and regression log
使用教程.txt          End-user workflow notes
```

Local samples and generated outputs are intentionally excluded from Git:

```text
doc/
prod_code_sample/
outputs/
templates/
```

Those directories may contain internal documents, production code, generated artifacts, logs, paths, keys, or tokens.

## Deploy Locally

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Benny\skill_lab\deploy_skills.ps1"
```

The default Codex runtime target is:

```text
C:\Users\51217\.codex\skills
```
