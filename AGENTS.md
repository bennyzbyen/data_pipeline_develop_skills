# Repository Guidelines

## Project Structure & Module Organization

This repository maintains Codex skills for data-development workflows. The source of truth is `skills/`; each skill should contain `SKILL.md` and may include `scripts/`, `references/`, `assets/`, or `agents/`. Current source skills include `data-doc-to-dev-md`, `data-sync-codegen`, `report-codegen`, `data-job-log-debugger`, `pipeline-excel-builder`, `pipeline-forge-guide`, and `db-ddl-generator-skill`. PipelineForge packaging lives in the independent sibling repository `..\pipeline-forge`; never recreate it as a nested checkout under this repository. Local-only material belongs in `doc/`, `prod_code_sample/`, `outputs/`, and `templates/`; keep those paths out of committed source and generated project code.

## Build, Test, and Development Commands

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1 -DryRun` previews skill sync operations.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1 -Clean` refreshes `%USERPROFILE%\.codex\skills`.
- `Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }` syntax-checks all Python helper scripts.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sync_pipeline_forge.ps1 -DryRun` previews the one-way source-to-plugin mirror into the sibling repository.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sync_pipeline_forge.ps1` mirrors source skills into `..\pipeline-forge` and validates source/package parity.
- `python ..\pipeline-forge\scripts\validate_package.py --source-root .` checks plugin package metadata, required modules, assets, helper syntax, and byte-level parity with this repository.
- `python .\skills\data-sync-codegen\scripts\verify_cot_runtime_semantics.py --project-dir <generated-project>` validates generated COT sync scaffolds.
- `python .\skills\report-codegen\scripts\verify_report_runtime_semantics.py --project-dir <generated-project> --project-type supervisor_portal` validates supported report scaffolds.
- `python .\skills\pipeline-excel-builder\scripts\validate_pipeline_excel.py --xlsx <workbook.xlsx> --json-out <validation.json>` validates generated Pipeline Export workbooks.

## Coding Style & Naming Conventions

Use lowercase kebab-case for skill and plugin-skill directories, matching the `name` in `SKILL.md` front matter. Keep skill instructions direct, constraint-driven, and scoped to one workflow. Python uses 4-space indentation, `pathlib.Path` for paths, placeholder credentials only, and `argparse` for CLIs. Prefer structured parsing over ad hoc string handling for DOCX, Excel, JSON, DDL, and config files.

## Testing Guidelines

There is no central test framework. Validate changes with Python compilation, relevant fake-runtime verifier scripts, plugin validation when packaging changes, and a deploy dry run. New verifiers must be deterministic and must not connect to real database, HBase, FS, Gateway, DataHub, or production services. Record the commands and results in the Git commit body or pull request instead of maintaining a duplicate iteration log.

## Commit & Pull Request Guidelines

Use a short imperative subject such as `Add report scaffold verifier`. For non-trivial changes, include `Why`, `Validation`, and `Related` sections in the commit body. `Validation` lists the commands or deterministic checks that passed; `Related` cites the corresponding PipelineForge commit as `pipeline-forge@<sha>` when both repositories change. Put unresolved work in GitHub Issues and user-visible plugin release changes in the PipelineForge `CHANGELOG.md`. Pull requests should mention deployment impact and assumptions about rowkeys, schemas, credentials, or production samples.

## Windows & PowerShell Workflow

Assume Windows PowerShell in this repository. Use `Get-Content`, `Get-ChildItem`, `Copy-Item`, `Move-Item`, and `Remove-Item -LiteralPath` instead of Bash-style commands. Prefer `rg -n -F 'text' .` for fixed-string search. Quote paths with spaces, Chinese characters, brackets, or `$` using single quotes and `-LiteralPath`. Before changing source code because a command failed, rule out shell, quoting, working-directory, encoding, regex, and permission issues.

## Security & Configuration Tips

Keep credentials, IPs, app keys, tokens, internal documents, logs, templates, and production code out of committed files. Generated skill output must use placeholders unless explicitly requested otherwise. Do not encode absolute `skill_lab`, `doc`, `outputs`, `templates`, or `prod_code_sample` paths into generated project artifacts.
