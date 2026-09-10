# Data Pipeline Develop Skills

This repository maintains Codex Skills for Python data development workflows.

## Skills

- `data-doc-to-dev-md`: convert PRD/DataEngine/DataHub/COT/report DOCX documents into AI-readable development docs.
- `data-sync-codegen`: generate COT/DataEngine data synchronization project scaffolds.
- `report-codegen`: generate DataEngine report development project scaffolds.
- `data-job-log-debugger`: diagnose deployed DataEngine/DataHub job failures from logs or screenshots.
- `pipeline-excel-builder`: build DataHub/DataEngine Pipeline Export Excel workbooks from waterline documents.
- `pipeline-forge-guide`: route document-to-delivery work across the PipelineForge skills.
- `db-ddl-generator-skill`: generate and review portable database DDL with explicit deployment profiles.
- `pipeline-doc-generator`: generate editable DataEngine waterline Markdown, interactive standalone HTML, and paginated PDF email attachments together from PRD/HLD evidence.

## GPT-6 Astra compatibility

The primary project model is `gpt-6-astra`; start a new evaluation at `medium` reasoning or preserve an existing supported effort. The Director's separately pinned `gpt-5.6-sol` sub-agent policy remains in `AGENTS.md`. Model selection belongs to the host task, not skill `agents/openai.yaml` metadata. See the [official migration guidance](https://developers.openai.com/api/docs/guides/latest-model).

Use `invoke_source_validation.ps1` for offline artifact and contract regressions, including audited assistant adoption, separate ready units, and disabled blocked scaffolds. Compare live-model behavior separately using the same synthetic inputs, source revision, reasoning effort, and tool access. Record unnecessary clarification, missed deliverables, incorrect facts, elapsed time, and available usage; a decision-only smoke test does not establish full workflow acceptance or a cost improvement.

For rollout, record both repository revisions and back up the eight installed skill directories before deployment. Validate source changes, mirror with `sync_pipeline_forge.ps1`, validate package parity, and deploy with `deploy_skills.ps1`. On a regression, restore the matching source/package revisions in separate checkouts and restore the backed-up installed directories. Restore the recorded host model only if it changed. Do not overwrite unrelated work or plugin-manager caches.

## Repository Layout

```text
skills/              Source-of-truth skill directories
deploy_skills.ps1    Sync skills into the local Codex runtime skill directory
invoke_source_validation.ps1
                     Run deterministic source checks and regression tests
sync_pipeline_forge.ps1
                     Mirror source skills into the sibling PipelineForge repository
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

## PipelineForge Repository

PipelineForge is an independent sibling Git repository, not a nested repository:

```text
<workspace>\
├── skill_lab\          Source-of-truth skills
└── pipeline-forge\     Plugin packaging and releases
```

Preview or perform the one-way mirror from this repository:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sync_pipeline_forge.ps1 -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sync_pipeline_forge.ps1
```

The sync script validates that the destination is the sibling PipelineForge Git repository before mirroring. Do not edit packaged skill copies as the source of truth or copy them back into `skill_lab`.

## Validate Source

Install the validation-only dependencies, then run the unified Windows entrypoint:

```powershell
python -m pip install --requirement .\requirements-validation.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\invoke_source_validation.ps1 -JsonOut .\outputs\source-validation-summary.json -JUnitOut .\outputs\source-validation-junit.xml
```

The command checks Python syntax, verifies that the DDL templates are tracked, scans source deliverables for sensitive values and machine-specific absolute paths, and runs every self-contained deterministic regression suite. It exits nonzero on any failed check and can write UTF-8 JSON and JUnit XML reports. Tests use synthetic fixtures and do not connect to real services.

## Project History

Git commits and pull requests are the engineering record. Non-trivial commits should explain `Why`, list `Validation` results, and cite the related PipelineForge commit when both repositories change. PipelineForge release notes belong in its `CHANGELOG.md`; unresolved follow-up work belongs in GitHub Issues.

## Deploy Locally

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1
```

The default Codex runtime target is:

```text
%USERPROFILE%\.codex\skills
```
