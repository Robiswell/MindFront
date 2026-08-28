param(
  [Parameter(Mandatory = $true)]
  [string]$BriefPath,

  [string]$ConfigRoot = "config",
  [string]$OutputRoot = "test-output/mindfront-skill-run",
  [string]$DbPath = "",
  [string]$Python = "python",
  [string]$RecipientName = "",
  [string]$ProfileStorePath = "",
  [string]$CommunicationVaultPath = "",
  [ValidateSet("", "decision_request", "executive_update", "incident_response", "informal_coordination", "meeting_follow_up", "project_planning", "status_update", "support_request", "technical_discussion")]
  [string]$RecipientContext = "",
  [string]$TaskValidationInput = "",
  [string]$TaskSessionsCsv = "",
  [ValidateSet("synthetic_fixture", "real_task_observation")]
  [string]$TaskSessionsObservationSource = "synthetic_fixture",
  [string]$DocumentId = "",
  [string]$DocumentType = "internal_documentation",
  [switch]$GenerateTaskProtocol,
  [switch]$RenderPdf
)

$ErrorActionPreference = "Stop"

$hasRecipientName = -not [string]::IsNullOrWhiteSpace($RecipientName)
$hasProfileStorePath = -not [string]::IsNullOrWhiteSpace($ProfileStorePath)
$hasCommunicationVaultPath = -not [string]::IsNullOrWhiteSpace($CommunicationVaultPath)
$hasRecipientContext = -not [string]::IsNullOrWhiteSpace($RecipientContext)
if ($hasRecipientName -ne $hasProfileStorePath) {
  throw "-RecipientName and -ProfileStorePath must be provided together."
}
if ($hasRecipientContext -and -not $hasRecipientName) {
  throw "-RecipientContext requires both -RecipientName and -ProfileStorePath."
}
if ($hasCommunicationVaultPath -and -not $hasRecipientName) {
  throw "-CommunicationVaultPath requires both -RecipientName and -ProfileStorePath."
}

function Assert-LastExit {
  param([string]$Label)
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Invoke-ProfileCliCheck {
  param(
    [string]$PythonPath,
    [string]$StorePath,
    [string]$Name,
    [string]$Context,
    [string]$VaultPath
  )

  $profilePreflightArgs = @(
    "-m",
    "mindfront.cli",
    "profile",
    "context",
    "--store",
    $StorePath,
    "--name",
    $Name
  )
  if (-not [string]::IsNullOrWhiteSpace($VaultPath)) {
    $profilePreflightArgs += @("--vault", $VaultPath)
  }
  if (-not [string]::IsNullOrWhiteSpace($Context)) {
    $profilePreflightArgs += @("--context", $Context)
  }
  $profilePreflightArgs += "--json-errors"

  $originalPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $captured = @(& $PythonPath @profilePreflightArgs 2>&1)
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $originalPreference
  }

  $errorCode = "profile_preflight_failed"
  if ($exitCode -ne 0) {
    try {
      $payload = (($captured | ForEach-Object { "$_" }) -join "`n") | ConvertFrom-Json
      if ($payload.errors.Count -gt 0 -and $payload.errors[0].code) {
        $errorCode = [string]$payload.errors[0].code
      }
    }
    catch {
      $errorCode = "profile_preflight_unreadable_error"
    }
  }

  return @{
    Succeeded = ($exitCode -eq 0)
    ExitCode = $exitCode
    ErrorCode = $errorCode
  }
}

function Invoke-ProfileRefresh {
  param(
    [string]$PythonPath,
    [string]$StorePath,
    [string]$Name,
    [string]$VaultPath
  )

  $originalPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $null = @(
      & $PythonPath -m mindfront.cli corpus refresh-profile `
        --vault $VaultPath `
        --profile-store $StorePath `
        --name $Name `
        --json-errors 2>&1
    )
    return ($LASTEXITCODE -eq 0)
  }
  finally {
    $ErrorActionPreference = $originalPreference
  }
}

$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (($Python -eq "python" -or [string]::IsNullOrWhiteSpace($Python)) -and (Test-Path -LiteralPath $bundledPython)) {
  $Python = $bundledPython
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
if ($hasRecipientName -and -not $hasCommunicationVaultPath) {
  $CommunicationVaultPath = Join-Path $repoRoot "runtime-data\interaction-communications.vault"
  $hasCommunicationVaultPath = $true
}
Push-Location $repoRoot
try {
  $env:PYTHONPATH = "backend/src"
  $runRoot = New-Item -ItemType Directory -Force -Path $OutputRoot
  $profileArgs = @()

  if ($hasRecipientName) {
    $vaultForCheck = ""
    $vaultAvailable = $false
    if ($hasCommunicationVaultPath) {
      $vaultAvailable = Test-Path -LiteralPath $CommunicationVaultPath -PathType Leaf
      if ($vaultAvailable) {
        $vaultForCheck = $CommunicationVaultPath
      }
    }

    if ($hasCommunicationVaultPath -and -not $vaultAvailable) {
      $profileCheck = @{
        Succeeded = $false
        ExitCode = 1
        ErrorCode = "communication_vault_unavailable"
      }
    }
    elseif (Test-Path -LiteralPath $ProfileStorePath -PathType Leaf) {
      $profileCheck = Invoke-ProfileCliCheck `
        -PythonPath $Python `
        -StorePath $ProfileStorePath `
        -Name $RecipientName `
        -Context $RecipientContext `
        -VaultPath $vaultForCheck
    }
    else {
      $profileCheck = @{
        Succeeded = $false
        ExitCode = 1
        ErrorCode = "profile_not_found"
      }
    }

    $refreshableCodes = @(
      "profile_not_found",
      "profile_not_ready",
      "profile_not_active",
      "source_mismatch"
    )
    if (
      -not $profileCheck.Succeeded `
      -and $vaultAvailable `
      -and $refreshableCodes -contains $profileCheck.ErrorCode
    ) {
      $null = Invoke-ProfileRefresh `
        -PythonPath $Python `
        -StorePath $ProfileStorePath `
        -Name $RecipientName `
        -VaultPath $CommunicationVaultPath
      $profileCheck = Invoke-ProfileCliCheck `
        -PythonPath $Python `
        -StorePath $ProfileStorePath `
        -Name $RecipientName `
        -Context $RecipientContext `
        -VaultPath $CommunicationVaultPath
    }

    if ($profileCheck.Succeeded) {
      $profileArgs = @(
        "--profile-store",
        $ProfileStorePath,
        "--profile-name",
        $RecipientName
      )
      if ($hasRecipientContext) {
        $profileArgs += @("--profile-context", $RecipientContext)
      }
    }
    else {
      $fallbackCode = [string]$profileCheck.ErrorCode
      if ($hasCommunicationVaultPath -and -not $vaultAvailable) {
        $fallbackCode = "communication_vault_unavailable"
      }
      Write-Output (
        "Mindfront named-recipient profile fallback: no active, source-matched profile was applied " +
        "($fallbackCode). The workflow is continuing unprofiled; source coverage remains bounded."
      )
    }
  }

  & $Python -m mindfront.cli validate --strict --json-errors --config-root $ConfigRoot --brief-root examples/briefs --task-validation-root examples/task-validation
  Assert-LastExit "Mindfront validate"
  & $Python -m mindfront.cli analyze --brief $BriefPath --config-root $ConfigRoot --overwrite replace --output (Join-Path $runRoot "analysis") @profileArgs
  Assert-LastExit "Mindfront analyze"
  & $Python -m mindfront.cli rewrite --brief $BriefPath --config-root $ConfigRoot --overwrite replace --output (Join-Path $runRoot "rewrite") @profileArgs
  Assert-LastExit "Mindfront rewrite"
  & $Python -m mindfront.cli compare --variants (Join-Path $runRoot "rewrite/copy-variants.json") --overwrite replace --output (Join-Path $runRoot "compare")
  Assert-LastExit "Mindfront compare"
  & $Python -m mindfront.cli reader-stress-test --analysis (Join-Path $runRoot "analysis/message-analysis-report.json") --config-root $ConfigRoot --overwrite replace --output (Join-Path $runRoot "stress")
  Assert-LastExit "Mindfront reader-stress-test"
  & $Python -m mindfront.cli research-plan --analysis (Join-Path $runRoot "analysis/message-analysis-report.json") --overwrite replace --output (Join-Path $runRoot "research")
  Assert-LastExit "Mindfront research-plan"

  $taskProtocolArgs = @()
  $taskProtocolPath = Join-Path $runRoot "task-protocol/documentation-task-observation-protocol.json"
  if ($GenerateTaskProtocol -or $TaskValidationInput.Trim() -or $TaskSessionsCsv.Trim()) {
    $protocolCommandArgs = @(
      "-m",
      "mindfront.cli",
      "task-protocol",
      "--analysis",
      (Join-Path $runRoot "analysis/message-analysis-report.json"),
      "--research-plan",
      (Join-Path $runRoot "research/research-plan.json"),
      "--document-type",
      $DocumentType,
      "--overwrite",
      "replace",
      "--output",
      (Join-Path $runRoot "task-protocol")
    )
    if ($DocumentId.Trim()) {
      $protocolCommandArgs += @("--document-id", $DocumentId)
    }
    & $Python @protocolCommandArgs
    Assert-LastExit "Mindfront task-protocol"
    $taskProtocolArgs = @("--task-protocol", $taskProtocolPath)
  }

  $taskValidationArgs = @()
  if ($TaskSessionsCsv.Trim()) {
    if (-not (Test-Path -LiteralPath $taskProtocolPath)) {
      throw "Task sessions CSV requires a generated task-observation protocol."
    }
    & $Python -m mindfront.cli task-input `
      --protocol $taskProtocolPath `
      --sessions-csv $TaskSessionsCsv `
      --observation-source $TaskSessionsObservationSource `
      --overwrite replace `
      --output (Join-Path $runRoot "task-input")
    Assert-LastExit "Mindfront task-input"
    $TaskValidationInput = Join-Path $runRoot "task-input/documentation-task-validation-input.json"
  }
  if ($TaskValidationInput.Trim()) {
    & $Python -m mindfront.cli task-validation `
      --input $TaskValidationInput `
      --analysis (Join-Path $runRoot "analysis/message-analysis-report.json") `
      --overwrite replace `
      --output (Join-Path $runRoot "task-validation")
    Assert-LastExit "Mindfront task-validation"
    $taskValidationArgs = @("--task-validation", (Join-Path $runRoot "task-validation/documentation-task-validation-result.json"))
  }

  & $Python -m mindfront.cli report `
    --analysis (Join-Path $runRoot "analysis/message-analysis-report.json") `
    --variants (Join-Path $runRoot "rewrite/copy-variants.json") `
    --comparison (Join-Path $runRoot "compare/variant-comparison.json") `
    --stress (Join-Path $runRoot "stress/reader-stress-test.json") `
    --research-plan (Join-Path $runRoot "research/research-plan.json") `
    @taskProtocolArgs `
    @taskValidationArgs `
    --config-root $ConfigRoot `
    --overwrite replace `
    --output (Join-Path $runRoot "report")
  Assert-LastExit "Mindfront report"

  if ($RenderPdf) {
    $renderOutput = powershell -NoProfile -ExecutionPolicy Bypass -File ".\project-tools\render-mindfront-report-pdf.ps1" `
      -ReportDirectory (Join-Path $runRoot "report")
    if ($LASTEXITCODE -ne 0) {
      throw "Mindfront PDF render failed with exit code $LASTEXITCODE."
    }
    $renderOutput
  }

  if ($DbPath.Trim()) {
    & $Python -m mindfront.cli store ingest `
      --db $DbPath `
      --analysis (Join-Path $runRoot "analysis/message-analysis-report.json") `
      --variants (Join-Path $runRoot "rewrite/copy-variants.json") `
      --comparison (Join-Path $runRoot "compare/variant-comparison.json") `
      --stress (Join-Path $runRoot "stress/reader-stress-test.json") `
      --research-plan (Join-Path $runRoot "research/research-plan.json") `
      --report (Join-Path $runRoot "report/mindfront-audit-report.json") `
      @taskProtocolArgs `
      @taskValidationArgs
    Assert-LastExit "Mindfront store ingest"
    & $Python -m mindfront.cli store check-stale --db $DbPath
    Assert-LastExit "Mindfront store check-stale"
    & $Python -m mindfront.cli dashboard build --db $DbPath --overwrite replace --output (Join-Path $runRoot "dashboard")
    Assert-LastExit "Mindfront dashboard build"
    & $Python -m mindfront.cli improvement-plan --db $DbPath --overwrite replace --output (Join-Path $runRoot "improvement-plan")
    Assert-LastExit "Mindfront improvement-plan"
  } else {
    Write-Output "Mindfront history loop disabled: pass -DbPath to store history, build the dashboard, and generate the next improvement plan."
  }

  Write-Output "Mindfront workflow complete: $($runRoot.FullName)"
}
finally {
  Pop-Location
}
