[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$JsonOut = "",
    [string]$JUnitOut = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$startedAt = [DateTimeOffset]::UtcNow
$checks = [System.Collections.Generic.List[object]]::new()
$previousPythonUtf8 = $env:PYTHONUTF8
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$previousDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$previousPycachePrefix = $env:PYTHONPYCACHEPREFIX
$validationTempRoot = [System.IO.Path]::GetFullPath(
    (Join-Path ([System.IO.Path]::GetTempPath()) ("pipeline-forge-source-validation-" + [Guid]::NewGuid().ToString("N")))
)
[System.IO.Directory]::CreateDirectory($validationTempRoot) | Out-Null

function Add-CheckResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Category,
        [Parameter(Mandatory = $true)]
        [bool]$Passed,
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,
        [Parameter(Mandatory = $true)]
        [long]$DurationMs,
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string]$Output = ""
    )

    $checks.Add([ordered]@{
        name = $Name
        category = $Category
        status = if ($Passed) { "passed" } else { "failed" }
        exit_code = $ExitCode
        duration_ms = $DurationMs
        command = $Command
        output = $Output
    })
}

function Invoke-PythonCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Category,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $displayCommand = $PythonExecutable + " " + (($Arguments | ForEach-Object {
        if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
    }) -join " ")
    Write-Host "==> $Name"
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Windows PowerShell 5.1 represents redirected native stderr as ErrorRecord.
        # Keep it in the captured diagnostic output without turning normal log lines
        # into terminating PowerShell errors.
        $outputLines = @(& $PythonExecutable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
    $stopwatch.Stop()
    $output = ($outputLines | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    if ($output) {
        Write-Host $output
    }
    $passed = $exitCode -eq 0
    Add-CheckResult -Name $Name -Category $Category -Passed $passed -ExitCode $exitCode `
        -DurationMs $stopwatch.ElapsedMilliseconds -Command $displayCommand -Output $output
    if (-not $passed) {
        Write-Warning "$Name failed with exit code $exitCode"
    }
}

function Test-DdlTemplates {
    $expectedTemplates = @(
        "clickhouse_prod_create_table.sql",
        "clickhouse_qa_create_table.sql",
        "mssql_create_table.sql",
        "mysql_create_table.sql",
        "postgres_create_table.sql"
    )
    $templateRoot = Join-Path $repositoryRoot "skills\db-ddl-generator-skill\templates"
    $messages = [System.Collections.Generic.List[string]]::new()
    $passed = $true
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    foreach ($templateName in $expectedTemplates) {
        $templatePath = Join-Path $templateRoot $templateName
        $relativePath = "skills/db-ddl-generator-skill/templates/$templateName"
        if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
            $messages.Add("missing: $relativePath")
            $passed = $false
            continue
        }
        & git -C $repositoryRoot check-ignore --quiet --no-index -- $relativePath
        if ($LASTEXITCODE -eq 0) {
            $messages.Add("ignored: $relativePath")
            $passed = $false
        } elseif ($LASTEXITCODE -ne 1) {
            $messages.Add("git check-ignore failed for: $relativePath")
            $passed = $false
        }
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & git -C $repositoryRoot ls-files --error-unmatch -- $relativePath 1>$null 2>$null
            $trackedExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedErrorActionPreference
        }
        if ($trackedExitCode -ne 0) {
            $messages.Add("untracked: $relativePath")
            $passed = $false
        } else {
            $messages.Add("tracked: $relativePath")
        }
    }
    $stopwatch.Stop()
    $output = $messages -join [Environment]::NewLine
    Write-Host "==> DDL templates are tracked by Git"
    Write-Host $output
    Add-CheckResult -Name "ddl_templates_tracked" -Category "source_integrity" -Passed $passed `
        -ExitCode $(if ($passed) { 0 } else { 1 }) -DurationMs $stopwatch.ElapsedMilliseconds `
        -Command "git check-ignore --quiet --no-index; git ls-files --error-unmatch -- skills/db-ddl-generator-skill/templates/*.sql" -Output $output
}

function Resolve-ReportPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $resolved = if ([System.IO.Path]::IsPathRooted($Path)) {
        [System.IO.Path]::GetFullPath($Path)
    } else {
        [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $Path))
    }
    $parent = Split-Path -Parent $resolved
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    return $resolved
}

function Write-JUnitReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Summary
    )

    $settings = [System.Xml.XmlWriterSettings]::new()
    $settings.Encoding = [System.Text.UTF8Encoding]::new($false)
    $settings.Indent = $true
    $settings.NewLineChars = [Environment]::NewLine
    $settings.CloseOutput = $true
    $writer = [System.Xml.XmlWriter]::Create($Path, $settings)
    $invariantCulture = [System.Globalization.CultureInfo]::InvariantCulture
    $xmlUnsafeCharacters = [regex]::new("[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD]")
    try {
        $writer.WriteStartDocument()
        $writer.WriteStartElement("testsuites")
        $writer.WriteStartElement("testsuite")
        $writer.WriteAttributeString("name", "PipelineForge source validation")
        $writer.WriteAttributeString("tests", [string]$Summary.check_count)
        $writer.WriteAttributeString("failures", [string]$Summary.failed_count)
        $writer.WriteAttributeString("errors", "0")
        $writer.WriteAttributeString("time", [string]::Format($invariantCulture, "{0:0.000}", ([double]$Summary.duration_ms / 1000)))
        $writer.WriteAttributeString("timestamp", $Summary.started_at_utc)
        foreach ($check in $Summary.checks) {
            $writer.WriteStartElement("testcase")
            $writer.WriteAttributeString("classname", "source_validation.$($check.category)")
            $writer.WriteAttributeString("name", $check.name)
            $writer.WriteAttributeString("time", [string]::Format($invariantCulture, "{0:0.000}", ([double]$check.duration_ms / 1000)))
            if ($check.status -eq "failed") {
                $writer.WriteStartElement("failure")
                $writer.WriteAttributeString("type", "validation_failure")
                $writer.WriteAttributeString("message", "$($check.name) failed with exit code $($check.exit_code)")
                if ($check.output) {
                    $writer.WriteString($xmlUnsafeCharacters.Replace($check.output, ""))
                }
                $writer.WriteEndElement()
            }
            if ($check.output) {
                $writer.WriteStartElement("system-out")
                $writer.WriteString($xmlUnsafeCharacters.Replace($check.output, ""))
                $writer.WriteEndElement()
            }
            $writer.WriteEndElement()
        }
        $writer.WriteEndElement()
        $writer.WriteEndElement()
        $writer.WriteEndDocument()
    } finally {
        $writer.Dispose()
    }
}

try {
    Push-Location -LiteralPath $repositoryRoot
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    $pythonCommand = Get-Command $PythonExecutable -ErrorAction Stop
    Write-Host "Repository: $repositoryRoot"
    Write-Host "Python: $($pythonCommand.Source)"

    Test-DdlTemplates

    $env:PYTHONPYCACHEPREFIX = Join-Path $validationTempRoot "pycache"
    Invoke-PythonCheck -Name "python_syntax" -Category "syntax" -Arguments @(
        "-m", "compileall", "-q", "-f", (Join-Path $repositoryRoot "skills")
    )
    $env:PYTHONPYCACHEPREFIX = $previousPycachePrefix

    $regressions = @(
        [ordered]@{
            Name = "technical_contract_regression"
            Script = "skills\data-doc-to-dev-md\scripts\verify_technical_contract_regression.py"
        },
        [ordered]@{
            Name = "docx_bundle_multidoc_regression"
            Script = "skills\data-doc-to-dev-md\scripts\verify_docx_bundle_multidoc.py"
        },
        [ordered]@{
            Name = "cot_manifest_semantics_regression"
            Script = "skills\data-sync-codegen\scripts\verify_cot_manifest_semantics_regression.py"
        },
        [ordered]@{
            Name = "cot_runtime_semantics_regression"
            Script = "skills\data-sync-codegen\scripts\verify_cot_runtime_semantics_regression.py"
        },
        [ordered]@{
            Name = "generic_report_runtime_semantics"
            Script = "skills\report-codegen\scripts\verify_generic_report_runtime_semantics.py"
        },
        [ordered]@{
            Name = "qas_synthetic_acceptance"
            Script = "skills\report-codegen\scripts\verify_qas_synthetic_acceptance.py"
        },
        [ordered]@{
            Name = "clickhouse_deployment_profile"
            Script = "skills\db-ddl-generator-skill\scripts\verify_clickhouse_deployment_profile.py"
        },
        [ordered]@{
            Name = "pipeline_excel_synthetic_regression"
            Script = "skills\pipeline-excel-builder\scripts\verify_pipeline_excel_synthetic_regression.py"
        }
    )
    foreach ($regression in $regressions) {
        Invoke-PythonCheck -Name $regression.Name -Category "regression" -Arguments @(
            (Join-Path $repositoryRoot $regression.Script)
        )
    }
    Invoke-PythonCheck -Name "source_safety_scan" -Category "security" -Arguments @(
        (Join-Path $repositoryRoot "scripts\verify_source_safety.py")
    )
} finally {
    Pop-Location
    $env:PYTHONUTF8 = $previousPythonUtf8
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
    $env:PYTHONDONTWRITEBYTECODE = $previousDontWriteBytecode
    $env:PYTHONPYCACHEPREFIX = $previousPycachePrefix
    $systemTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\") + "\"
    if ($validationTempRoot.StartsWith($systemTempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $validationTempRoot -PathType Container)) {
        Remove-Item -LiteralPath $validationTempRoot -Recurse -Force
    }
}

$failedCount = @($checks | Where-Object { $_.status -eq "failed" }).Count
$finishedAt = [DateTimeOffset]::UtcNow
$summary = [ordered]@{
    schema_version = 1
    status = if ($failedCount -eq 0) { "passed" } else { "failed" }
    repository_root = $repositoryRoot
    started_at_utc = $startedAt.ToString("o")
    finished_at_utc = $finishedAt.ToString("o")
    duration_ms = [long]($finishedAt - $startedAt).TotalMilliseconds
    check_count = $checks.Count
    passed_count = $checks.Count - $failedCount
    failed_count = $failedCount
    checks = $checks
}
$summaryJson = $summary | ConvertTo-Json -Depth 8

if (-not [string]::IsNullOrWhiteSpace($JsonOut)) {
    $jsonPath = Resolve-ReportPath -Path $JsonOut
    [System.IO.File]::WriteAllText($jsonPath, $summaryJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Validation summary: $jsonPath"
}

if (-not [string]::IsNullOrWhiteSpace($JUnitOut)) {
    $junitPath = Resolve-ReportPath -Path $JUnitOut
    Write-JUnitReport -Path $junitPath -Summary $summary
    Write-Host "JUnit report: $junitPath"
}

Write-Host "Source validation $($summary.status): $($summary.passed_count)/$($summary.check_count) checks passed."
if ($failedCount -ne 0) {
    exit 1
}
exit 0
