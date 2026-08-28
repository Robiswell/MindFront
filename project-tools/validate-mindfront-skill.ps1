param(
  [string]$SkillPath = "skills/mindfront"
)

$ErrorActionPreference = "Stop"
$skillFile = Join-Path $SkillPath "SKILL.md"
if (-not (Test-Path -LiteralPath $skillFile)) {
  throw "SKILL.md not found at $skillFile"
}

$content = Get-Content -LiteralPath $skillFile -Raw
if ($content -notmatch "(?s)^---\r?\n(.*?)\r?\n---") {
  throw "Invalid or missing YAML frontmatter."
}

$frontmatter = $Matches[1]
$fields = @{}
foreach ($line in ($frontmatter -split "\r?\n")) {
  if ($line -match "^([^:]+):\s*(.*)$") {
    $fields[$Matches[1].Trim()] = $Matches[2].Trim()
  }
}

foreach ($key in $fields.Keys) {
  if ($key -notin @("name", "description", "license", "allowed-tools", "metadata")) {
    throw "Unexpected frontmatter key: $key"
  }
}

if (-not $fields.ContainsKey("name")) {
  throw "Missing name in frontmatter."
}
if (-not $fields.ContainsKey("description")) {
  throw "Missing description in frontmatter."
}
if ($fields["name"] -ne "mindfront") {
  throw "Expected skill name 'mindfront', found '$($fields["name"])'."
}
if ($fields["name"] -notmatch "^[a-z0-9-]+$") {
  throw "Skill name must be lowercase hyphen-case."
}
if ($fields["description"].Length -gt 1024) {
  throw "Description exceeds 1024 characters."
}
if ($fields["description"] -match "[<>]") {
  throw "Description cannot contain angle brackets."
}
if ($content -match "TODO") {
  throw "Skill file still contains TODO text."
}

$required = @(
  "agents/openai.yaml",
  "references/confidence-policy.md",
  "references/workflow-contract.md",
  "references/source-first-deployment.md",
  "assets/report-output-checklist.md",
  "scripts/run_mindfront_workflow.ps1"
)
foreach ($relativePath in $required) {
  $path = Join-Path $SkillPath $relativePath
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Missing required skill resource: $relativePath"
  }
}

Write-Output "Mindfront skill is valid."
