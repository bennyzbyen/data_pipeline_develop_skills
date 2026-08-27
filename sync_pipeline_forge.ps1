[CmdletBinding()]
param(
    [string]$PluginRoot = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$sourceSkillsRoot = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot "skills"))
if (-not $PluginRoot) {
    $PluginRoot = Join-Path (Split-Path -Parent $repositoryRoot) "pipeline-forge"
}
$pluginRepositoryRoot = [System.IO.Path]::GetFullPath($PluginRoot)
$pluginSkillsRoot = [System.IO.Path]::GetFullPath((Join-Path $pluginRepositoryRoot "skills"))
$pluginPrefix = $pluginRepositoryRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not (Test-Path -LiteralPath (Join-Path $pluginRepositoryRoot ".git"))) {
    throw "PipelineForge destination is not the expected Git repository: $pluginRepositoryRoot"
}
if (-not $pluginSkillsRoot.StartsWith($pluginPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to mirror outside the PipelineForge repository: $pluginSkillsRoot"
}
if (-not (Test-Path -LiteralPath $sourceSkillsRoot -PathType Container)) {
    throw "Source skills directory does not exist: $sourceSkillsRoot"
}
if (-not (Test-Path -LiteralPath $pluginSkillsRoot -PathType Container)) {
    throw "Packaged skills directory does not exist: $pluginSkillsRoot"
}

$sourceSkills = @(
    Get-ChildItem -LiteralPath $sourceSkillsRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") } |
        Sort-Object Name
)

foreach ($skill in $sourceSkills) {
    $destination = [System.IO.Path]::GetFullPath((Join-Path $pluginSkillsRoot $skill.Name))
    if (-not $destination.StartsWith($pluginPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to mirror skill outside the PipelineForge repository: $destination"
    }
    if ($DryRun) {
        Write-Output "DRY-RUN: would mirror $($skill.FullName) -> $destination"
        continue
    }

    & robocopy $skill.FullName $destination /MIR /XD __pycache__ /XF *.pyc /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed for $($skill.Name) with exit code $LASTEXITCODE"
    }
}

if ($DryRun) {
    Write-Output "Dry run complete. No files changed."
    exit 0
}

$validator = Join-Path $pluginRepositoryRoot "scripts\validate_package.py"
$env:PYTHONUTF8 = "1"
& python $validator --source-root $repositoryRoot
if ($LASTEXITCODE -ne 0) {
    throw "PipelineForge package validation failed with exit code $LASTEXITCODE"
}

Write-Output "PipelineForge skill mirror complete: $pluginSkillsRoot"
