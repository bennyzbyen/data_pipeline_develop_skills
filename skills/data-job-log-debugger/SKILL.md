---
name: data-job-log-debugger
description: Diagnose DataEngine/DataHub Python job failures from full printed logs or screenshots, covering data synchronization and report development jobs with ClickHouse, HBase, FS, Gateway, MSSQL, MySQL, Blob, encoding, path, parameter, permission, missing data, and deployment environment issues.
---

# Data Job Log Debugger

Use this skill when the user provides complete printed logs, copied traceback text, or screenshots from deployed DataEngine/DataHub jobs and asks for root cause analysis or minimal fix suggestions.

## Scope

- Diagnose before proposing code changes.
- Prefer non-code causes first: path handling, PowerShell parsing, encoding, params, missing files, permissions, environment variables, service access, upstream data absence.
- Then check business logic and code defects.
- Default output is analysis and minimal fix suggestion, not automatic code modification.

## Inputs

- Full printed log text, or screenshots if text is unavailable.
- Optional: params JSON, related code path, environment (`uat`/`prod`), rerun period/date, recent code changes.

## Outputs

- Confirmed root cause or highest-confidence hypothesis.
- Impact scope.
- Minimum recommended fix.
- Verification steps using logs or safe local checks.
- Remaining uncertainty.

## Workflow

1. Read `references/common_failure_modes.md`.
2. For text logs, run `scripts/analyze_data_job_log.py --log <log.txt>` when a local log file is available. Use its classification as a starting point, then verify against the full log manually.
3. For screenshots, visually extract or OCR the exception line, final failure symptom, params snippet, and the 30-50 lines around the failure before classifying.
4. Extract the first real exception and the final failure symptom.
5. Classify the issue: environment, params, path/encoding, dependency, gateway/HBase/ClickHouse, data absence, or business logic.
6. Identify the smallest evidence-backed fix.
7. Ask for code modification only when root cause and target file are clear.

## Output Format

Use these sections:

- Confirmed Issues
- High-Confidence Assumptions
- Uncertain Points
- Recommended Next Steps
- Verification

For deployment jobs, always mention whether the log proves that HBase, ClickHouse, FS, and timestamp update steps did or did not run.

## Hard Constraints

- Do not rewrite large code blocks from logs alone.
- Do not assume screenshots contain all context; list missing log lines when needed.
- Do not recommend production retries that can duplicate or delete data unless rerun behavior is known.
- Do not treat "no changed rows/periods" as a code defect until source SQL, timestamp, and manual period/date params are checked.
