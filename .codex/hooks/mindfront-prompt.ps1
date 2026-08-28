$ErrorActionPreference = "Stop"

$rawInput = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($rawInput)) {
  exit 0
}

try {
  $event = $rawInput | ConvertFrom-Json -ErrorAction Stop
}
catch {
  exit 0
}

try {
  . (Join-Path $PSScriptRoot "mindfront-common.ps1")
}
catch {
  exit 0
}

$prompt = [string]$event.prompt
$route = Get-MindfrontPromptRoute $prompt
if ($route -eq "none") {
  exit 0
}

$context = Get-MindfrontPromptContext -Route $route
if ($route -eq "workplace_assistance") {
  $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
  $selfProfileStore = Join-Path $repoRoot "runtime-data\self-workplace-assistance.vault"
  $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if ((Test-Path -LiteralPath $selfProfileStore) -and (Test-Path -LiteralPath $bundledPython)) {
    $priorPythonPath = $env:PYTHONPATH
    try {
      $env:PYTHONPATH = Join-Path $repoRoot "backend\src"
      $profileContextRaw = & $bundledPython -B -m mindfront.cli assist profile context --store $selfProfileStore 2>$null
      if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($profileContextRaw -join "`n"))) {
        $profileContext = ($profileContextRaw -join "`n") | ConvertFrom-Json -ErrorAction Stop
        if (
          $profileContext.artifactType -eq "self_workplace_assistance_context" -and
          $profileContext.humanReviewRequired -eq $true -and
          $profileContext.automaticSendingAllowed -eq $false
        ) {
          $context = @(
            $context,
            "The current user's encrypted self-workplace-assistance profile was validated and is available. Before substantive guidance, privately run mindfront.cli assist profile context --store runtime-data/self-workplace-assistance.vault and apply the returned context without copying its JSON or values into hook output, normal history, reports, or the final response unless the user explicitly asks."
          ) -join "`n"
        }
      }
    }
    catch {
      # Static workplace-assistance safeguards remain active when private context cannot be loaded.
    }
    finally {
      $env:PYTHONPATH = $priorPythonPath
    }
  }
}

[ordered]@{
  hookSpecificOutput = [ordered]@{
    hookEventName = "UserPromptSubmit"
    additionalContext = $context.Trim()
  }
} | ConvertTo-Json -Depth 6 -Compress
