#!/usr/bin/env python3
"""Scan source deliverables for secrets and machine-specific absolute paths."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Pattern


EXCLUDED_ROOTS = {".git", "doc", "outputs", "plugins", "prod_code_sample", "templates"}
ROOT_SOURCE_FILES = {
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "deploy_skills.ps1",
    "invoke_source_validation.ps1",
    "requirements-validation.txt",
    "sync_pipeline_forge.ps1",
    "使用教程.txt",
}
SOURCE_PREFIXES = (".github/", "scripts/", "skills/")
MAX_SOURCE_BYTES = 5 * 1024 * 1024

LINE_PATTERNS: dict[str, Pattern[str]] = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "openai_api_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}\b"),
    "slack_token": re.compile(r"\bxox(?:b|p|a|r|s)-[A-Za-z0-9-]{20,}\b"),
    "jwt_token": re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "private_ipv4": re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
    ),
    "windows_absolute_workspace_path": re.compile(
        r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/](?:[^\\/\r\n\"'<>|:]+[\\/])+[^\\/\r\n\"'<>|:]*"
    ),
    "posix_absolute_workspace_path": re.compile(
        r"(?<![:A-Za-z0-9_])/(?:Users|home|mnt|workspace|workspaces)/(?:[^/\s\"'<>]+/)+[^/\s\"'<>]*"
    ),
}
CREDENTIAL_URL = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://(?P<user>[^:/\s<>]+):(?P<password>[^@\s<>]+)@"
)
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|app[_-]?key|app[_-]?secret|access[_-]?key)\b"
    r"\s*[:=]\s*[\"'](?P<value>[^\"']+)[\"']"
)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@(?P<domain>[A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
SAFE_EMAIL_DOMAINS = {"example.com", "example.invalid", "example.net", "example.org"}


def source_paths(repository_root: Path) -> list[Path]:
    process = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    relative_paths = process.stdout.decode("utf-8").split("\0")
    result: list[Path] = []
    for raw_path in relative_paths:
        if not raw_path:
            continue
        normalized = raw_path.replace("\\", "/")
        root_name = normalized.split("/", 1)[0]
        if root_name in EXCLUDED_ROOTS:
            continue
        if normalized in ROOT_SOURCE_FILES or normalized.startswith(SOURCE_PREFIXES):
            result.append(repository_root / Path(normalized))
    return sorted(set(result))


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    if (normalized.startswith("<") and normalized.endswith(">")) or (
        normalized.startswith("${") and normalized.endswith("}")
    ):
        return True
    return any(marker in normalized for marker in ("placeholder", "example", "fixture", "synthetic", "fake"))


def scan_text(relative_path: str, text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for finding_type, pattern in LINE_PATTERNS.items():
            if pattern.search(line):
                findings.append({"type": finding_type, "path": relative_path, "line": line_number})
        credential_url = CREDENTIAL_URL.search(line)
        if credential_url and not all(
            is_placeholder(credential_url.group(name)) for name in ("user", "password")
        ):
            findings.append({"type": "credential_url", "path": relative_path, "line": line_number})
        assignment = CREDENTIAL_ASSIGNMENT.search(line)
        if assignment and not is_placeholder(assignment.group("value")):
            findings.append({"type": "credential_assignment", "path": relative_path, "line": line_number})
        for email in EMAIL.finditer(line):
            if email.group("domain").lower() not in SAFE_EMAIL_DOMAINS:
                findings.append({"type": "non_example_email", "path": relative_path, "line": line_number})
    return findings


def run_scan(repository_root: Path) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    scanned_files = 0
    for path in source_paths(repository_root):
        relative_path = path.relative_to(repository_root).as_posix()
        if not path.is_file():
            findings.append({"type": "missing_source_file", "path": relative_path, "line": 0})
            continue
        data = path.read_bytes()
        if len(data) > MAX_SOURCE_BYTES:
            findings.append({"type": "source_file_too_large", "path": relative_path, "line": 0})
            continue
        if b"\0" in data:
            findings.append({"type": "binary_source_file", "path": relative_path, "line": 0})
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append({"type": "non_utf8_source_file", "path": relative_path, "line": 0})
            continue
        scanned_files += 1
        findings.extend(scan_text(relative_path, text))
    return {
        "status": "passed" if not findings else "failed",
        "scanned_file_count": scanned_files,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run_scan(args.repository_root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
