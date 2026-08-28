param(
  [ValidateRange(1, 65535)]
  [int] $Port = 8765,

  [switch] $NoBrowser
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path -LiteralPath $bundledPython -PathType Leaf) {
  $bundledPython
}
else {
  $resolved = Get-Command python -ErrorAction SilentlyContinue
  if ($null -eq $resolved) {
    throw 'Python 3.11 or later is required. The bundled Codex Python runtime was not found.'
  }
  $resolved.Source
}

$env:PYTHONPATH = Join-Path $repoRoot 'backend\src'
$arguments = @(
  '-m',
  'mindfront.gui',
  '--host',
  '127.0.0.1',
  '--port',
  $Port
)
if (-not $NoBrowser) {
  $arguments += '--open-browser'
}

Push-Location $repoRoot
try {
  & $python @arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Mindfront GUI exited with code $LASTEXITCODE."
  }
}
finally {
  Pop-Location
}
