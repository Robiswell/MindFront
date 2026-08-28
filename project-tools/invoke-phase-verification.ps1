param(
  [switch]$RequirePlan,
  [string]$PlanPath = "plans/automatic-mindfront-activation.md",
  [int]$Passes = 3,
  [string]$OutputRoot = "test-output/phase-verification",
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"

if ($Passes -lt 1) {
  throw "Passes must be at least 1."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
  $OutputRoot = Join-Path $repoRoot $OutputRoot
}

if (-not [System.IO.Path]::IsPathRooted($PlanPath)) {
  $PlanPath = Join-Path $repoRoot $PlanPath
}
$plansRoot = (Resolve-Path (Join-Path $repoRoot "plans")).Path
$planPath = [System.IO.Path]::GetFullPath($PlanPath)
$plansPrefix = $plansRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $planPath.StartsWith($plansPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "PlanPath must resolve below the repo plans directory: $planPath"
}
$automationSmoke = Join-Path $repoRoot "project-tools\test-mindfront-automation.ps1"
$runtimePickup = Join-Path $repoRoot "project-tools\test-mindfront-runtime-pickup.ps1"
$skillWorkflow = Join-Path $repoRoot "project-tools\test-mindfront-skill.ps1"
$skillValidator = Join-Path $repoRoot "project-tools\validate-mindfront-skill.ps1"
$officialSkillValidator = Join-Path $env:USERPROFILE ".codex\skills\.system\skill-creator\scripts\quick_validate.py"

if ([string]::IsNullOrWhiteSpace($Python)) {
  $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path -LiteralPath $bundledPython) {
    $Python = $bundledPython
  }
  else {
    $Python = "python"
  }
}

if ($RequirePlan) {
  if (-not (Test-Path -LiteralPath $planPath)) {
    throw "Required phase plan is missing: $planPath"
  }
  $planText = Get-Content -LiteralPath $planPath -Raw
  if ($planText -notmatch '(?im)^Status:\s*implemented and verified\.?$') {
    throw "Required phase plan is not marked implemented and verified: $planPath"
  }
}

foreach ($path in @($automationSmoke, $runtimePickup, $skillWorkflow, $skillValidator)) {
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Required verification script is missing: $path"
  }
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$passesRun = New-Object System.Collections.Generic.List[object]

for ($pass = 1; $pass -le $Passes; $pass += 1) {
  $passRoot = Join-Path $OutputRoot ("pass-" + $pass)
  $automationOutput = Join-Path $passRoot "automation"
  $runtimeOutput = Join-Path $passRoot "runtime"
  $skillOutput = Join-Path $passRoot "skill-workflow"
  $skillDb = Join-Path $skillOutput "mindfront.sqlite"

  $global:LASTEXITCODE = 0
  & $automationSmoke -OutputRoot $automationOutput
  if (-not $?) {
    throw "Automation smoke verification failed during pass $pass."
  }

  $global:LASTEXITCODE = 0
  & $runtimePickup -OutputRoot $runtimeOutput
  if (-not $?) {
    throw "Runtime pickup verification failed during pass $pass."
  }

  $global:LASTEXITCODE = 0
  & $skillValidator -SkillPath "skills/mindfront"
  if (-not $?) {
    throw "Skill validation failed during pass $pass."
  }

  Push-Location $repoRoot
  try {
    $env:PYTHONPATH = "backend/src;backend/.test-deps"
    $global:LASTEXITCODE = 0
    & $Python -c "import yaml; assert yaml.__version__ == '6.0.3', yaml.__version__"
    if (-not $? -or $LASTEXITCODE -ne 0) {
      throw "Runtime dependency preflight failed during pass $pass with exit code $LASTEXITCODE."
    }

    $global:LASTEXITCODE = 0
    & $Python -B -m pytest backend\tests -q
    if (-not $? -or $LASTEXITCODE -ne 0) {
      throw "Backend unit tests failed during pass $pass with exit code $LASTEXITCODE."
    }

    $global:LASTEXITCODE = 0
    & $Python -B -m compileall backend\src backend\tests
    if (-not $? -or $LASTEXITCODE -ne 0) {
      throw "Python compilation failed during pass $pass with exit code $LASTEXITCODE."
    }

    if (Test-Path -LiteralPath $officialSkillValidator) {
      $global:LASTEXITCODE = 0
      & $Python $officialSkillValidator "skills\mindfront"
      if (-not $? -or $LASTEXITCODE -ne 0) {
        throw "Official skill validation failed during pass $pass with exit code $LASTEXITCODE."
      }
    }

    $global:LASTEXITCODE = 0
    & $skillWorkflow -Python $Python -OutputRoot $skillOutput -DbPath $skillDb -RenderPdf
    if (-not $?) {
      throw "Mindfront skill workflow failed during pass $pass."
    }
  }
  finally {
    Pop-Location
  }

  $passesRun.Add([ordered]@{
    pass = $pass
    automationOutput = $automationOutput
    runtimeOutput = $runtimeOutput
    skillWorkflowOutput = $skillOutput
    pdfRenderingRequired = $true
  }) | Out-Null
}

$result = [ordered]@{
  artifactType = "mindfront_phase_verification_result"
  status = "passed"
  checkedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  planRequired = [bool]$RequirePlan
  planPath = $planPath
  python = $Python
  passesRequested = $Passes
  pdfRenderingRequired = $true
  passes = $passesRun
}

$resultPath = Join-Path $OutputRoot "mindfront-phase-verification-result.json"
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output "Mindfront phase verification passed: $resultPath"
