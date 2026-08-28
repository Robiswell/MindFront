param(
  [string]$OutputRoot = "test-output/mindfront-runtime-pickup",
  [string]$CodexConfig = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
  $OutputRoot = Join-Path $repoRoot $OutputRoot
}

if ([string]::IsNullOrWhiteSpace($CodexConfig)) {
  $homeRoot = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
  $CodexConfig = Join-Path $homeRoot ".codex\config.toml"
}

$hooksJson = Join-Path $repoRoot ".codex\hooks.json"
$promptHook = Join-Path $repoRoot ".codex\hooks\mindfront-prompt.ps1"
$stopHook = Join-Path $repoRoot ".codex\hooks\mindfront-stop.ps1"
$commonHook = Join-Path $repoRoot ".codex\hooks\mindfront-common.ps1"
$manifestPath = Join-Path $repoRoot "config\automation-manifest.json"
$globalMindfrontSkill = Join-Path ([System.IO.Path]::GetDirectoryName($CodexConfig)) "skills\mindfront\SKILL.md"

$checks = New-Object System.Collections.Generic.List[object]
$failed = 0

function Add-Check {
  param(
    [string]$Name,
    [bool]$Passed,
    [string]$Detail
  )

  $script:checks.Add([ordered]@{
    name = $Name
    passed = $Passed
    detail = $Detail
  }) | Out-Null

  if (-not $Passed) {
    $script:failed += 1
  }
}

function Get-TrustedHashForKey {
  param([string]$ConfigText, [string]$Key)

  $escaped = [regex]::Escape($Key)
  $match = [regex]::Match($ConfigText, "(?is)\[hooks\.state\.'$escaped'\](?:(?!\r?\n\[).)*trusted_hash\s*=\s*""([^""]+)""")
  if (-not $match.Success) {
    return ""
  }

  return $match.Groups[1].Value
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

Add-Check "project_hooks_json_exists" (Test-Path -LiteralPath $hooksJson) $hooksJson
Add-Check "project_prompt_hook_exists" (Test-Path -LiteralPath $promptHook) $promptHook
Add-Check "project_stop_hook_exists" (Test-Path -LiteralPath $stopHook) $stopHook
Add-Check "project_common_hook_exists" (Test-Path -LiteralPath $commonHook) $commonHook
Add-Check "codex_config_exists" (Test-Path -LiteralPath $CodexConfig) $CodexConfig

$configText = ""
if (Test-Path -LiteralPath $CodexConfig) {
  $configText = Get-Content -LiteralPath $CodexConfig -Raw
}

$hooksEnabled = $configText -match '(?is)\[features\](?:(?!\r?\n\[).)*\bhooks\s*=\s*true\b'
Add-Check "global_hooks_feature_enabled" $hooksEnabled "Requires [features] hooks = true in active Codex config."

$currentDirectory = (Get-Location).ProviderPath
Add-Check "current_working_directory_is_repo_root" ($currentDirectory -ieq $repoRoot) "current=$currentDirectory; expected=$repoRoot"

$repoKey = [regex]::Escape($repoRoot.ToLowerInvariant())
$projectTrusted = $configText -match "(?is)\[projects\.'$repoKey'\](?:(?!\r?\n\[).)*trust_level\s*=\s*""trusted"""
Add-Check "project_trusted_in_codex_config" $projectTrusted "Requires this repo to be trusted by Codex."

$userHookKey = [regex]::Escape($hooksJson + ":user_prompt_submit:0:0")
$stopHookKey = [regex]::Escape($hooksJson + ":stop:0:0")
$userHookTrustHash = Get-TrustedHashForKey $configText ($hooksJson + ":user_prompt_submit:0:0")
$stopHookTrustHash = Get-TrustedHashForKey $configText ($hooksJson + ":stop:0:0")
Add-Check "user_prompt_hook_trust_state_entry_present" ($userHookTrustHash -match '^sha256:[0-9a-f]{64}$') "Requires trusted hook state entry for project UserPromptSubmit command; current command hash is owned by Codex and not recomputed by this audit."
Add-Check "stop_hook_trust_state_entry_present" ($stopHookTrustHash -match '^sha256:[0-9a-f]{64}$') "Requires trusted hook state entry for project Stop command; current command hash is owned by Codex and not recomputed by this audit."

if (Test-Path -LiteralPath $hooksJson) {
  $projectHooks = Get-Content -LiteralPath $hooksJson -Raw | ConvertFrom-Json -ErrorAction Stop
  $promptCommand = [string]$projectHooks.hooks.UserPromptSubmit[0].hooks[0].command
  $stopCommand = [string]$projectHooks.hooks.Stop[0].hooks[0].command
  Add-Check "hooks_json_has_prompt_command" ($promptCommand -eq 'powershell -NoProfile -ExecutionPolicy Bypass -File .\.codex\hooks\mindfront-prompt.ps1') $promptCommand
  Add-Check "hooks_json_has_stop_command" ($stopCommand -eq 'powershell -NoProfile -ExecutionPolicy Bypass -File .\.codex\hooks\mindfront-stop.ps1') $stopCommand
}

if (Test-Path -LiteralPath $manifestPath) {
  $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -ErrorAction Stop
  Add-Check "manifest_project_local_scope" ($manifest.scope -eq "project-local") "scope=$($manifest.scope)"
  Add-Check "manifest_runtime_deployment_false" ($manifest.runtimeDeploymentRequired -eq $false) "runtimeDeploymentRequired=$($manifest.runtimeDeploymentRequired)"
}
else {
  Add-Check "manifest_exists" $false $manifestPath
}

Add-Check "global_mindfront_skill_optional" $true ("present=" + [string](Test-Path -LiteralPath $globalMindfrontSkill) + "; project-local hooks are the active runtime path.")

$result = [ordered]@{
  artifactType = "mindfront_runtime_pickup_result"
  status = if ($failed -eq 0) { "passed" } else { "failed" }
  checkedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  repoRoot = $repoRoot
  codexConfig = $CodexConfig
  trustHashVerification = "entry_present_only; Codex owns exact current-command trust hash validation"
  checks = $checks
}

$resultPath = Join-Path $OutputRoot "mindfront-runtime-pickup-result.json"
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8

if ($failed -gt 0) {
  throw "Mindfront runtime pickup audit failed with $failed failed check(s). See $resultPath"
}

Write-Output "Mindfront runtime pickup audit passed: $resultPath"
