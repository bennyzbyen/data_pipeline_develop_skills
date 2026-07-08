# Repository Guidelines

## Project Structure & Module Organization

This repository maintains Codex skills for data-development workflows. The source of truth is `skills/`; each skill should contain `SKILL.md` and may include `scripts/`, `references/`, `assets/`, or `agents/`. Current source skills include `data-doc-to-dev-md`, `data-sync-codegen`, `report-codegen`, `data-job-log-debugger`, and `pipeline-excel-builder`. `plugins/pipeline-forge/` is the plugin packaging workspace. Local-only material belongs in `doc/`, `prod_code_sample/`, `outputs/`, and `templates/`; keep those paths out of committed source and generated project code.

## Build, Test, and Development Commands

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1 -DryRun` previews skill sync operations.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1 -Clean` refreshes `%USERPROFILE%\.codex\skills`.
- `Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }` syntax-checks all Python helper scripts.
- `python .\plugins\pipeline-forge\scripts\validate_package.py` checks plugin package metadata, required modules, assets, and helper syntax.
- `python .\skills\data-sync-codegen\scripts\verify_cot_runtime_semantics.py --project-dir <generated-project>` validates generated COT sync scaffolds.
- `python .\skills\report-codegen\scripts\verify_report_runtime_semantics.py --project-dir <generated-project> --project-type supervisor_portal` validates supported report scaffolds.
- `python .\skills\pipeline-excel-builder\scripts\validate_pipeline_excel.py --xlsx <workbook.xlsx> --json-out <validation.json>` validates generated Pipeline Export workbooks.

## Coding Style & Naming Conventions

Use lowercase kebab-case for skill and plugin-skill directories, matching the `name` in `SKILL.md` front matter. Keep skill instructions direct, constraint-driven, and scoped to one workflow. Python uses 4-space indentation, `pathlib.Path` for paths, placeholder credentials only, and `argparse` for CLIs. Prefer structured parsing over ad hoc string handling for DOCX, Excel, JSON, DDL, and config files.

## Testing Guidelines

There is no central test framework. Validate changes with Python compilation, relevant fake-runtime verifier scripts, plugin validation when packaging changes, and a deploy dry run. New verifiers must be deterministic and must not connect to real database, HBase, FS, Gateway, DataHub, or production services. Record meaningful regression results in `ITERATION_LOG.md`.

## Commit & Pull Request Guidelines

Git history currently has only the initial baseline commit, so use short imperative commit messages such as `Add report scaffold verifier`. Pull requests should summarize changed skills, list verification commands and results, mention any deployment impact, and flag assumptions about rowkeys, schemas, credentials, or production samples.

## Windows & PowerShell Workflow

Assume Windows PowerShell in this repository. Use `Get-Content`, `Get-ChildItem`, `Copy-Item`, `Move-Item`, and `Remove-Item -LiteralPath` instead of Bash-style commands. Prefer `rg -n -F 'text' .` for fixed-string search. Quote paths with spaces, Chinese characters, brackets, or `$` using single quotes and `-LiteralPath`. Before changing source code because a command failed, rule out shell, quoting, working-directory, encoding, regex, and permission issues.

## Security & Configuration Tips

Keep credentials, IPs, app keys, tokens, internal documents, logs, templates, and production code out of committed files. Generated skill output must use placeholders unless explicitly requested otherwise. Do not encode absolute `skill_lab`, `doc`, `outputs`, `templates`, or `prod_code_sample` paths into generated project artifacts.
