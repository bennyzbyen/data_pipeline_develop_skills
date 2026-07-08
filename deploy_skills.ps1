[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot,
    [string[]]$SkillNames = @(
        "data-doc-to-dev-md",
        "data-sync-codegen",
        "report-codegen",
        "data-job-log-debugger",
        "pipeline-excel-builder"
    ),
    [switch]$DryRun,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    (Get-Location).Path
} else {
    $PSScriptRoot
}

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = Join-Path $scriptRoot "skills"
}

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = Join-Path $env:USERPROFILE ".codex\skills"
}

function Get-ResolvedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return (Resolve-Path -LiteralPath $Path).Path
}

function Test-IsUnderRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $normalizedRoot = $Root.TrimEnd("\")
    return $Path.StartsWith($normalizedRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)
}

if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    throw "SourceRoot does not exist: $SourceRoot"
}

if (-not (Test-Path -LiteralPath $TargetRoot -PathType Container)) {
    if ($DryRun) {
        Write-Host "DRY-RUN: would create target root: $TargetRoot"
    } else {
        New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
    }
}

$sourceRootResolved = Get-ResolvedPath -Path $SourceRoot
$targetRootResolved = if (Test-Path -LiteralPath $TargetRoot -PathType Container) {
    Get-ResolvedPath -Path $TargetRoot
} else {
    $TargetRoot
}

$robocopy = Join-Path $env:SystemRoot "System32\robocopy.exe"
if (-not (Test-Path -LiteralPath $robocopy -PathType Leaf)) {
    throw "robocopy.exe was not found at expected path: $robocopy"
}

$excludeDirs = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git")
$excludeFiles = @("*.pyc", "*.pyo", ".DS_Store")

foreach ($skillName in $SkillNames) {
    if ($skillName -notmatch "^[a-z0-9][a-z0-9-]*$") {
        throw "Invalid skill name: $skillName"
    }

    $sourceDir = Join-Path $sourceRootResolved $skillName
    $targetDir = Join-Path $targetRootResolved $skillName
    $sourceSkillMd = Join-Path $sourceDir "SKILL.md"

    if (-not (Test-Path -LiteralPath $sourceDir -PathType Container)) {
        throw "Skill source directory does not exist: $sourceDir"
    }

    if (-not (Test-Path -LiteralPath $sourceSkillMd -PathType Leaf)) {
        throw "Skill is missing SKILL.md: $sourceSkillMd"
    }

    if ($Clean -and (Test-Path -LiteralPath $targetDir -PathType Container)) {
        $resolvedTargetDir = Get-ResolvedPath -Path $targetDir
        if (-not (Test-IsUnderRoot -Path $resolvedTargetDir -Root $targetRootResolved)) {
            throw "Refusing to clean outside target root: $resolvedTargetDir"
        }

        if ($DryRun) {
            Write-Host "DRY-RUN: would remove existing target skill: $resolvedTargetDir"
        } else {
            Remove-Item -LiteralPath $resolvedTargetDir -Recurse -Force
        }
    }

    if ($DryRun) {
        Write-Host "DRY-RUN: would sync $sourceDir -> $targetDir"
        continue
    }

    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

    $copyArgs = @(
        $sourceDir,
        $targetDir,
        "/E",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
        "/XD"
    ) + $excludeDirs + @("/XF") + $excludeFiles

    & $robocopy @copyArgs | Out-Host
    $exitCode = $LASTEXITCODE
    if ($exitCode -ge 8) {
        throw "robocopy failed for $skillName with exit code $exitCode"
    }

    $targetSkillMd = Join-Path $targetDir "SKILL.md"
    if (-not (Test-Path -LiteralPath $targetSkillMd -PathType Leaf)) {
        throw "Sync failed; target SKILL.md is missing: $targetSkillMd"
    }

    Write-Host "Synced skill: $skillName"
}

Write-Host "Skill deployment complete: $targetRootResolved"
