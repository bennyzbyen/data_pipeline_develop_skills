# Repository Guidelines

## Project Structure & Module Organization

This repository maintains Codex skills for data-development workflows. The source of truth is `skills/`, where each skill has a `SKILL.md` plus optional `scripts/`, `references/`, `assets/`, and `agents/` subdirectories. Top-level docs include `README.md`, `ITERATION_LOG.md`, and `使用教程.txt`. `deploy_skills.ps1` syncs selected skills into the local Codex runtime. Local-only inputs and generated artifacts belong in `doc/`, `prod_code_sample/`, and `outputs/`; do not commit secrets, production samples, logs, or generated regressions from those directories.

## Build, Test, and Development Commands

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1 -DryRun` checks which skill directories would be synced.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy_skills.ps1 -Clean` refreshes the local runtime copy under `%USERPROFILE%\.codex\skills`.
- `Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }` syntax-checks all Python helper scripts.
- `python .\skills\data-sync-codegen\scripts\verify_cot_runtime_semantics.py --project-dir <generated-project>` validates generated COT sync behavior when a scaffold exists.
- `python .\skills\report-codegen\scripts\verify_report_runtime_semantics.py --project-dir <generated-project> --project-type supervisor_portal` validates supported report scaffolds.

## Coding Style & Naming Conventions

Use lowercase kebab-case for skill directories, matching the `name` in `SKILL.md` front matter. Keep skill instructions direct, constraint-driven, and scoped to one workflow. Python scripts should use 4-space indentation, `pathlib.Path` for paths, placeholder credentials only, and clear CLI arguments via `argparse`. Prefer PowerShell-safe examples and quote paths with spaces using `-LiteralPath`.

## Testing Guidelines

There is no central test framework. Validate changes with Python compilation, relevant fake-runtime verifier scripts, and a deploy dry run. When adding a script, include deterministic checks that avoid real database, HBase, FS, Gateway, or production-service connections. Record meaningful regression results in `ITERATION_LOG.md`.

## Commit & Pull Request Guidelines

Git history currently has only the initial baseline commit, so use short imperative commit messages such as `Add report scaffold verifier`. Pull requests should summarize changed skills, list verification commands and results, mention any deployment impact, and flag assumptions about rowkeys, schemas, credentials, or production samples.

## Security & Configuration Tips

Keep credentials, IPs, app keys, tokens, internal documents, logs, and production code out of committed files. Generated skill output must use placeholders unless a user explicitly requests otherwise. Do not encode absolute `skill_lab`, `doc`, `outputs`, or `prod_code_sample` paths into generated project artifacts.
