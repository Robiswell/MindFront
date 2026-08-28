param(
  [string]$ReportDirectory = "",
  [string]$InputHtml = "",
  [string]$InputBrief = "",
  [string]$OutputPdf = "",
  [string]$BrowserPath = "",
  [switch]$VisualQaPassed
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$usingReportDirectory = $false

function Get-Sha256Uri {
  param([Parameter(Mandatory = $true)][string]$Path)
  $algorithm = [System.Security.Cryptography.SHA256]::Create()
  $stream = [System.IO.File]::OpenRead($Path)
  try {
    $hash = $algorithm.ComputeHash($stream)
    return "sha256:$(([System.BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant())"
  }
  finally {
    $stream.Dispose()
    $algorithm.Dispose()
  }
}

function Get-StringSha256Uri {
  param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
  $algorithm = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $hash = $algorithm.ComputeHash($bytes)
    return "sha256:$(([System.BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant())"
  }
  finally {
    $algorithm.Dispose()
  }
}

function ConvertTo-StableJson {
  param([AllowNull()]$Value)

  if ($null -eq $Value) {
    return "null"
  }
  if ($Value -is [string]) {
    return ($Value | ConvertTo-Json -Compress)
  }
  if ($Value -is [bool]) {
    return $(if ($Value) { "true" } else { "false" })
  }
  if (
    $Value -is [byte] -or $Value -is [sbyte] -or
    $Value -is [int16] -or $Value -is [uint16] -or
    $Value -is [int32] -or $Value -is [uint32] -or
    $Value -is [int64] -or $Value -is [uint64] -or
    $Value -is [single] -or $Value -is [double] -or
    $Value -is [decimal]
  ) {
    return ([System.Convert]::ToString($Value, [System.Globalization.CultureInfo]::InvariantCulture))
  }
  if ($Value -is [System.Collections.IDictionary]) {
    $keys = @($Value.Keys | ForEach-Object { [string]$_ })
    [System.Array]::Sort($keys, [System.StringComparer]::Ordinal)
    $parts = foreach ($key in $keys) {
      "$(ConvertTo-StableJson -Value $key):$(ConvertTo-StableJson -Value $Value[$key])"
    }
    return "{$($parts -join ',')}"
  }
  if (
    $Value -is [System.Collections.IEnumerable] -and
    $Value -isnot [System.Management.Automation.PSCustomObject]
  ) {
    $parts = foreach ($item in $Value) {
      ConvertTo-StableJson -Value $item
    }
    return "[$($parts -join ',')]"
  }

  $properties = @($Value.PSObject.Properties | Where-Object { $_.MemberType -match "Property" })
  $names = @($properties.Name)
  [System.Array]::Sort($names, [System.StringComparer]::Ordinal)
  $parts = foreach ($name in $names) {
    "$(ConvertTo-StableJson -Value $name):$(ConvertTo-StableJson -Value $Value.$name)"
  }
  return "{$($parts -join ',')}"
}

function Test-PathWithinRoot {
  param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Candidate
  )
  $rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
  $candidatePath = [System.IO.Path]::GetFullPath($Candidate)
  if ($candidatePath.Equals($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $true
  }
  $prefix = "$rootPath$([System.IO.Path]::DirectorySeparatorChar)"
  return $candidatePath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

if (-not ("Mindfront.NativeFilePath" -as [type])) {
  Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using System.Text;

namespace Mindfront {
  public static class NativeFilePath {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern uint GetFinalPathNameByHandle(
      SafeFileHandle handle,
      StringBuilder path,
      uint pathLength,
      uint flags
    );
  }
}
"@
}

function Get-FinalExistingFilePath {
  param([Parameter(Mandatory = $true)][string]$Path)
  $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
  $stream = [System.IO.File]::Open(
    $Path,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    $share
  )
  try {
    $buffer = New-Object System.Text.StringBuilder 32768
    $length = [Mindfront.NativeFilePath]::GetFinalPathNameByHandle(
      $stream.SafeFileHandle,
      $buffer,
      $buffer.Capacity,
      0
    )
    if ($length -eq 0 -or $length -ge $buffer.Capacity) {
      throw "Windows could not resolve the final file path."
    }
    return $buffer.ToString().Replace("\\?\UNC\", "\\").Replace("\\?\", "")
  }
  finally {
    $stream.Dispose()
  }
}

function Test-SameExistingFile {
  param(
    [Parameter(Mandatory = $true)][string]$Left,
    [Parameter(Mandatory = $true)][string]$Right
  )
  if (
    -not (Test-Path -LiteralPath $Left -PathType Leaf) -or
    -not (Test-Path -LiteralPath $Right -PathType Leaf)
  ) {
    return $false
  }
  return (Get-FinalExistingFilePath -Path $Left).Equals(
    (Get-FinalExistingFilePath -Path $Right),
    [System.StringComparison]::OrdinalIgnoreCase
  )
}

$script:RenderTrustFailure = $null

function Fail-RenderTrust {
  param([Parameter(Mandatory = $true)][string]$Reason)
  $script:RenderTrustFailure = $Reason
  return $false
}

function Test-TrustedRenderManifest {
  param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$HtmlPath,
    [string]$BriefPath = ""
  )

  $manifestPath = "$PdfPath.render-manifest.json"
  if (-not (Test-Path -LiteralPath $manifestPath)) {
    return (Fail-RenderTrust -Reason "render manifest is missing")
  }

  $script:RenderTrustFailure = $null
  try {
    $pdfFullPath = (Resolve-Path -LiteralPath $PdfPath -ErrorAction Stop).ProviderPath
    $htmlFullPath = (Resolve-Path -LiteralPath $HtmlPath -ErrorAction Stop).ProviderPath
    $briefFullPath = if ($BriefPath.Trim()) {
      (Resolve-Path -LiteralPath $BriefPath -ErrorAction Stop).ProviderPath
    }
    else {
      ""
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $rendererScript = (Resolve-Path -LiteralPath (Join-Path $repoRoot "project-tools\render-html-to-pdf-playwright.js") -ErrorAction Stop).ProviderPath
    $normalizerScript = (Resolve-Path -LiteralPath (Join-Path $repoRoot "project-tools\normalize-pdf-list-tags.py") -ErrorAction Stop).ProviderPath

    if (
      $manifest.artifactType -ne "html_to_pdf_render_manifest" -or
      [int]$manifest.schemaVersion -ne 2 -or
      [string]$manifest.sourceHtmlPath -ne $htmlFullPath -or
      $manifest.sourceHtmlSha256 -ne (Get-Sha256Uri -Path $htmlFullPath) -or
      [string]$manifest.outputPdfPath -ne $pdfFullPath -or
      $manifest.outputPdfSha256 -ne (Get-Sha256Uri -Path $pdfFullPath) -or
      [int64]$manifest.outputPdfBytes -ne (Get-Item -LiteralPath $pdfFullPath).Length -or
      [string]$manifest.rendererScriptPath -ne $rendererScript -or
      $manifest.rendererScriptSha256 -ne (Get-Sha256Uri -Path $rendererScript) -or
      $manifest.pdfOptions.tagged -ne $true -or
      $manifest.renderProfile.javaScriptEnabled -ne $false
    ) {
      return (Fail-RenderTrust -Reason "core source, output, renderer, or PDF option binding failed")
    }
    if ($briefFullPath) {
      if (
        [string]$manifest.sourceBriefPath -ne $briefFullPath -or
        [string]$manifest.sourceBriefSha256 -ne (Get-Sha256Uri -Path $briefFullPath)
      ) {
        return (Fail-RenderTrust -Reason "source brief path or hash binding failed")
      }
    }
    elseif (
      -not [string]::IsNullOrEmpty([string]$manifest.sourceBriefPath) -or
      -not [string]::IsNullOrEmpty([string]$manifest.sourceBriefSha256)
    ) {
      return (Fail-RenderTrust -Reason "render manifest contains an unexpected source brief binding")
    }

    $browserPath = [string]$manifest.browserExecutablePath
    $nodePath = [string]$manifest.nodeExecutablePath
    if (
      -not (Test-Path -LiteralPath $browserPath) -or
      $manifest.browserExecutableSha256 -ne (Get-Sha256Uri -Path $browserPath) -or
      -not (Test-Path -LiteralPath $nodePath) -or
      $manifest.nodeExecutableSha256 -ne (Get-Sha256Uri -Path $nodePath)
    ) {
      return (Fail-RenderTrust -Reason "browser or Node runtime binding failed")
    }

    $snapshot = $manifest.renderSnapshot
    $sourceRoot = (Resolve-Path -LiteralPath ([string]$snapshot.sourceRootPath) -ErrorAction Stop).ProviderPath
    $expectedSourceRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $htmlFullPath) -ErrorAction Stop).ProviderPath
    if ($sourceRoot -ne $expectedSourceRoot) {
      return (Fail-RenderTrust -Reason "snapshot source root does not match the HTML directory")
    }
    $snapshotSourcePath = [System.IO.Path]::GetFullPath(
      (Join-Path $sourceRoot ([string]$snapshot.sourceHtmlRelativePath))
    )
    if (-not (Test-SameExistingFile -Left $snapshotSourcePath -Right $htmlFullPath)) {
      return (Fail-RenderTrust -Reason "snapshot HTML relative path does not resolve to the source HTML")
    }

    $snapshotEntries = @($snapshot.files)
    if (
      $snapshotEntries.Count -le 0 -or
      [int]$snapshot.fileCount -ne $snapshotEntries.Count
    ) {
      return (Fail-RenderTrust -Reason "snapshot inventory count is invalid")
    }
    $snapshotDigestBuilder = New-Object System.Text.StringBuilder
    $snapshotBytes = 0L
    $previousRelativePath = $null
    foreach ($entry in $snapshotEntries) {
      $relativePath = [string]$entry.relativePath
      if (
        [string]::IsNullOrWhiteSpace($relativePath) -or
        [System.IO.Path]::IsPathRooted($relativePath) -or
        $relativePath -match '(^|/)\.\.(/|$)' -or
        ($null -ne $previousRelativePath -and
          [System.StringComparer]::Ordinal.Compare($previousRelativePath, $relativePath) -ge 0)
      ) {
        return (Fail-RenderTrust -Reason "snapshot inventory path is unsafe, duplicated, or unsorted")
      }
      $candidate = [System.IO.Path]::GetFullPath(
        (Join-Path $sourceRoot ($relativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)))
      )
      if (
        -not (Test-PathWithinRoot -Root $sourceRoot -Candidate $candidate) -or
        -not (Test-Path -LiteralPath $candidate -PathType Leaf)
      ) {
        return (Fail-RenderTrust -Reason "snapshot inventory resolves outside the source root or is missing")
      }
      $candidateInfo = Get-Item -LiteralPath $candidate
      $candidateHash = Get-Sha256Uri -Path $candidate
      if (
        [int64]$entry.bytes -ne $candidateInfo.Length -or
        [string]$entry.sha256 -ne $candidateHash
      ) {
        return (Fail-RenderTrust -Reason "snapshot file size or hash does not match the current source")
      }
      $snapshotBytes += $candidateInfo.Length
      [void]$snapshotDigestBuilder.Append($relativePath)
      [void]$snapshotDigestBuilder.Append([char]0)
      [void]$snapshotDigestBuilder.Append($candidateInfo.Length)
      [void]$snapshotDigestBuilder.Append([char]0)
      [void]$snapshotDigestBuilder.Append($candidateHash)
      [void]$snapshotDigestBuilder.Append("`n")
      $previousRelativePath = $relativePath
    }
    if (
      [int64]$snapshot.totalBytes -ne $snapshotBytes -or
      [string]$snapshot.snapshotSha256 -ne
        (Get-StringSha256Uri -Value $snapshotDigestBuilder.ToString())
    ) {
      return (Fail-RenderTrust -Reason "snapshot aggregate byte count or digest is invalid")
    }

    $rawPdfPath = [string]$manifest.rawPdf.path
    if (
      -not (Test-Path -LiteralPath $rawPdfPath -PathType Leaf) -or
      $manifest.rawPdf.sha256 -ne (Get-Sha256Uri -Path $rawPdfPath) -or
      [int64]$manifest.rawPdf.bytes -ne (Get-Item -LiteralPath $rawPdfPath).Length
    ) {
      return (Fail-RenderTrust -Reason "raw PDF evidence is missing or does not match its binding")
    }

    $normalization = $manifest.listTagNormalization
    $invocation = $normalization.invocation
    $normalizerResult = $normalization.result
    $pythonPath = [string]$normalization.pythonExecutablePath
    if (
      [string]$normalization.scriptPath -ne $normalizerScript -or
      $normalization.scriptSha256 -ne (Get-Sha256Uri -Path $normalizerScript) -or
      -not (Test-Path -LiteralPath $pythonPath -PathType Leaf) -or
      $normalization.pythonExecutableSha256 -ne (Get-Sha256Uri -Path $pythonPath) -or
      [string]$invocation.executablePath -ne $pythonPath -or
      [string]$invocation.inputPdfPath -ne $rawPdfPath -or
      [string]$invocation.outputPdfPath -ne $pdfFullPath -or
      [string]$invocation.inputPdfSha256 -ne [string]$manifest.rawPdf.sha256 -or
      [string]$invocation.outputPdfSha256 -ne [string]$manifest.outputPdfSha256 -or
      [int]$invocation.exitCode -ne 0 -or
      [string]$normalization.summary.status -ne "passed" -or
      [string]$normalizerResult.artifactType -ne "pdf_list_tag_normalization_result" -or
      [string]$normalizerResult.status -notin @("normalized", "unchanged") -or
      "sha256:$([string]$normalizerResult.inputSha256)" -ne [string]$manifest.rawPdf.sha256 -or
      [string]$normalization.resultSha256 -ne
        (Get-StringSha256Uri -Value (ConvertTo-StableJson -Value $normalizerResult))
    ) {
      return (Fail-RenderTrust -Reason "normalizer executable, invocation, status, input, or result binding failed")
    }
    if (
      ([string]$normalizerResult.status -eq "normalized" -and
        "sha256:$([string]$normalizerResult.outputSha256)" -ne [string]$manifest.outputPdfSha256) -or
      ([string]$normalizerResult.status -eq "unchanged" -and
        [string]$manifest.rawPdf.sha256 -ne [string]$manifest.outputPdfSha256)
    ) {
      return (Fail-RenderTrust -Reason "normalizer result does not bind the final PDF")
    }

    $expectedArguments = @(
      $normalizerScript,
      "--input",
      $rawPdfPath,
      "--output",
      $pdfFullPath
    )
    $recordedArguments = @($invocation.argumentVector | ForEach-Object { [string]$_ })
    if ($recordedArguments.Count -ne $expectedArguments.Count) {
      return (Fail-RenderTrust -Reason "normalizer argument count is invalid")
    }
    for ($index = 0; $index -lt $expectedArguments.Count; $index++) {
      if ($recordedArguments[$index] -ne $expectedArguments[$index]) {
        return (Fail-RenderTrust -Reason "normalizer argument vector does not match the bound raw and final PDFs")
      }
    }

    $bindings = $manifest.trustChain.bindings
    $expectedBindings = [ordered]@{
      sourceHtmlSha256 = Get-Sha256Uri -Path $htmlFullPath
    }
    if ($briefFullPath) {
      $expectedBindings.sourceBriefSha256 = Get-Sha256Uri -Path $briefFullPath
    }
    $expectedBindings.snapshotSha256 = [string]$snapshot.snapshotSha256
    $expectedBindings.rendererScriptSha256 = Get-Sha256Uri -Path $rendererScript
    $expectedBindings.rawPdfSha256 = Get-Sha256Uri -Path $rawPdfPath
    $expectedBindings.normalizerScriptSha256 = Get-Sha256Uri -Path $normalizerScript
    $expectedBindings.normalizerResultSha256 = Get-StringSha256Uri -Value (ConvertTo-StableJson -Value $normalizerResult)
    $expectedBindings.finalPdfSha256 = Get-Sha256Uri -Path $pdfFullPath
    $recordedBindingNames = @($bindings.PSObject.Properties.Name)
    if ($recordedBindingNames.Count -ne $expectedBindings.Count) {
      return (Fail-RenderTrust -Reason "trust-chain binding count is invalid")
    }
    $chainBuilder = New-Object System.Text.StringBuilder
    foreach ($key in $expectedBindings.Keys) {
      if ([string]$bindings.$key -ne [string]$expectedBindings[$key]) {
        return (Fail-RenderTrust -Reason "trust-chain binding failed for $key")
      }
      [void]$chainBuilder.Append("$key=$($expectedBindings[$key])`n")
    }
    if (
      [string]$manifest.trustChain.algorithm -ne "sha256" -or
      [string]$manifest.trustChain.chainSha256 -ne
        (Get-StringSha256Uri -Value $chainBuilder.ToString())
    ) {
      return (Fail-RenderTrust -Reason "trust-chain digest is invalid")
    }
    return $true
  }
  catch {
    return (Fail-RenderTrust -Reason "render manifest validation raised $($_.Exception.GetType().Name): $($_.Exception.Message)")
  }
}

if (-not $InputHtml.Trim()) {
  $usingReportDirectory = $true
  if (-not $ReportDirectory.Trim()) {
    $ReportDirectory = Join-Path $repoRoot "test-output/sample-report"
  }
  $sourceCandidate = Join-Path $ReportDirectory "source.html"
  if (Test-Path -LiteralPath $sourceCandidate) {
    $InputHtml = $sourceCandidate
  }
  else {
    $InputHtml = Join-Path $ReportDirectory "mindfront-audit-report.html"
  }
}

$inputPath = (Resolve-Path -LiteralPath $InputHtml -ErrorAction Stop).ProviderPath
if (-not $OutputPdf.Trim()) {
  $inputName = [System.IO.Path]::GetFileName($inputPath)
  if ($usingReportDirectory -or $inputName -ieq "source.html" -or $inputName -ieq "mindfront-audit-report.html") {
    $OutputPdf = Join-Path (Split-Path -Parent $inputPath) "mindfront-audit-report.pdf"
  }
  else {
    $OutputPdf = [System.IO.Path]::ChangeExtension($inputPath, ".pdf")
  }
}

$sourcePath = $inputPath
$sourceAliasPath = Join-Path (Split-Path -Parent $inputPath) "source.html"
if ([System.IO.Path]::GetFileName($inputPath) -ine "source.html") {
  Copy-Item -LiteralPath $inputPath -Destination $sourceAliasPath -Force
  $sourcePath = (Resolve-Path -LiteralPath $sourceAliasPath -ErrorAction Stop).ProviderPath
}
$briefPath = if ($InputBrief.Trim()) {
  (Resolve-Path -LiteralPath $InputBrief -ErrorAction Stop).ProviderPath
}
else {
  ""
}

$outputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPdf)
$outputDirectory = Split-Path -Parent $outputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
  New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}
$outputDirectory = (Resolve-Path -LiteralPath $outputDirectory -ErrorAction Stop).ProviderPath

$nodeExe = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
$rendererScript = Join-Path $repoRoot "project-tools\render-html-to-pdf-playwright.js"
if (-not (Test-Path -LiteralPath $nodeExe -PathType Leaf)) {
  throw "Bundled Node.js was not found for trusted rendering: $nodeExe"
}
if (-not (Test-Path -LiteralPath $rendererScript -PathType Leaf)) {
  throw "Trusted renderer was not found: $rendererScript"
}

$stagingDirectory = Join-Path $outputDirectory (".mindfront-render-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stagingDirectory | Out-Null
$stagedPdfPath = Join-Path $stagingDirectory "artifact.pdf"
$stagedRawPdfPath = "$stagedPdfPath.raw.pdf"
$stagedManifestPath = "$stagedPdfPath.render-manifest.json"

$previousNodePath = $env:NODE_PATH
try {
  $env:NODE_PATH = @(
    $nodeModules,
    (Join-Path $nodeModules ".pnpm\node_modules")
  ) -join ";"
  $renderArgs = @($rendererScript, $sourcePath, $stagedPdfPath)
  if ($briefPath) {
    $renderBrowserArgument = if ($BrowserPath.Trim()) { $BrowserPath } else { "-" }
    $renderArgs += @($renderBrowserArgument, "0.35in", $briefPath)
  }
  elseif ($BrowserPath.Trim()) {
    $renderArgs += $BrowserPath
  }

  $previousErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $renderOutput = & $nodeExe @renderArgs 2>&1
    $renderExitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($renderExitCode -ne 0) {
    throw "Trusted Playwright rendering failed: $($renderOutput -join ' ')"
  }
  if (-not (Test-TrustedRenderManifest -PdfPath $stagedPdfPath -HtmlPath $sourcePath -BriefPath $briefPath)) {
    throw "Staged PDF did not pass the independent render-chain validation: $script:RenderTrustFailure."
  }

  $finalRawPdfPath = "$outputPath.raw.pdf"
  Copy-Item -LiteralPath $stagedPdfPath -Destination $outputPath -Force
  Copy-Item -LiteralPath $stagedRawPdfPath -Destination $finalRawPdfPath -Force

  $manifest = Get-Content -LiteralPath $stagedManifestPath -Raw | ConvertFrom-Json
  $manifest.outputPdfPath = $outputPath
  $manifest.rawPdf.path = $finalRawPdfPath
  $manifest.listTagNormalization.invocation.inputPdfPath = $finalRawPdfPath
  $manifest.listTagNormalization.invocation.outputPdfPath = $outputPath
  $manifest.listTagNormalization.invocation.argumentVector = @(
    [string]$manifest.listTagNormalization.scriptPath,
    "--input",
    $finalRawPdfPath,
    "--output",
    $outputPath
  )
  $renderManifestPath = "$outputPath.render-manifest.json"
  $temporaryManifestPath = "$renderManifestPath.$([System.Guid]::NewGuid().ToString('N')).tmp"
  $manifest | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $temporaryManifestPath -Encoding UTF8
  Move-Item -LiteralPath $temporaryManifestPath -Destination $renderManifestPath -Force

  if (-not (Test-TrustedRenderManifest -PdfPath $outputPath -HtmlPath $sourcePath -BriefPath $briefPath)) {
    throw "Promoted PDF did not pass the independent render-chain validation: $script:RenderTrustFailure."
  }
}
finally {
  $env:NODE_PATH = $previousNodePath
  $resolvedStaging = [System.IO.Path]::GetFullPath($stagingDirectory)
  if (
    (Test-PathWithinRoot -Root $outputDirectory -Candidate $resolvedStaging) -and
    [System.IO.Path]::GetFileName($resolvedStaging).StartsWith(
      ".mindfront-render-",
      [System.StringComparison]::Ordinal
    )
  ) {
    Remove-Item -LiteralPath $resolvedStaging -Recurse -Force -ErrorAction SilentlyContinue
  }
}

$pdfInfo = Get-Item -LiteralPath $outputPath -ErrorAction Stop
$renderManifestPath = "$($pdfInfo.FullName).render-manifest.json"
$renderManifest = Get-Content -LiteralPath $renderManifestPath -Raw | ConvertFrom-Json

$result = [ordered]@{
  artifactType = "mindfront_documentation_flow_result"
  editableSourcePath = $sourcePath
  sourceBriefPath = if ($briefPath) { $briefPath } else { $null }
  sourceBriefSha256 = if ($briefPath) { Get-Sha256Uri -Path $briefPath } else { $null }
  finalPdfPath = $pdfInfo.FullName
  rawPdfEvidencePath = "$($pdfInfo.FullName).raw.pdf"
  pdfStatus = "rendered_nonempty"
  visualQaStatus = if ($VisualQaPassed) { "passed_by_caller" } else { "pending_visual_qa" }
  sourceAliasCreated = ($sourcePath -ne $inputPath)
  originalInputHtmlPath = $inputPath
  fileSizeBytes = $pdfInfo.Length
  renderManifestPath = $renderManifestPath
  renderManifestSha256 = Get-Sha256Uri -Path $renderManifestPath
  renderProfileStatus = "passed"
  renderTrustChainStatus = "passed"
  listTagNormalizationStatus = $renderManifest.listTagNormalization.summary.status
  generatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  evidenceBoundary = "PDF rendering does not create market evidence or upgrade recommendation confidence."
}

$resultPath = Join-Path (Split-Path -Parent $sourcePath) "mindfront-documentation-flow-result.json"
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output $resultPath
