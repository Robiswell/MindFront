param(
  [string]$Python = "python",
  [string]$OutputRoot = "test-output/mindfront-skill-check",
  [string]$DbPath = "",
  [switch]$RenderPdf
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (($Python -eq "python" -or [string]::IsNullOrWhiteSpace($Python)) -and (Test-Path -LiteralPath $bundledPython)) {
  $Python = $bundledPython
}
Push-Location $repoRoot
try {
  & powershell -NoProfile -ExecutionPolicy Bypass -File ".\project-tools\validate-mindfront-skill.ps1" -SkillPath "skills/mindfront"
  if ($LASTEXITCODE -ne 0) {
    throw "Mindfront skill validation failed with exit code $LASTEXITCODE."
  }
  if (-not $DbPath.Trim()) {
    $DbPath = Join-Path $OutputRoot "mindfront.sqlite"
  }
  $workflowArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "skills/mindfront/scripts/run_mindfront_workflow.ps1",
    "-BriefPath",
    "examples/briefs/sample-message-brief.json",
    "-ConfigRoot",
    "config",
    "-OutputRoot",
    $OutputRoot,
    "-DbPath",
    $DbPath,
    "-Python",
    $Python
  )
  if ($RenderPdf) {
    $workflowArgs += "-RenderPdf"
  }
  & powershell @workflowArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Mindfront skill workflow failed with exit code $LASTEXITCODE."
  }

  if ($RenderPdf) {
    $reportDir = Join-Path $OutputRoot "report"
    $sourceHtml = Join-Path $reportDir "source.html"
    $plannedPdf = Join-Path $reportDir "mindfront-audit-report.pdf"
    $renderResultPath = Join-Path $reportDir "mindfront-documentation-flow-result.json"

    foreach ($path in @($sourceHtml, $plannedPdf, $renderResultPath)) {
      if (-not (Test-Path -LiteralPath $path)) {
        throw "Expected PDF workflow artifact is missing: $path"
      }
    }

    $pdfInfo = Get-Item -LiteralPath $plannedPdf
    if ($pdfInfo.Length -le 0) {
      throw "Rendered PDF is empty: $plannedPdf"
    }

    $renderResult = Get-Content -LiteralPath $renderResultPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([System.IO.Path]::GetFileName([string]$renderResult.editableSourcePath) -ne "source.html") {
      throw "PDF render result must use source.html as editableSourcePath."
    }
    if ([System.IO.Path]::GetFileName([string]$renderResult.finalPdfPath) -ne "mindfront-audit-report.pdf") {
      throw "PDF render result must use mindfront-audit-report.pdf as finalPdfPath."
    }
    if ($renderResult.pdfStatus -ne "rendered_nonempty") {
      throw "PDF render result did not report rendered_nonempty status."
    }
    if ($renderResult.visualQaStatus -notin @("pending_visual_qa", "passed_by_caller")) {
      throw "PDF render result must expose visual QA status."
    }
  }

  $taskValidationRoot = Join-Path $OutputRoot "task-validation-check"
  $taskValidationDb = Join-Path $taskValidationRoot "mindfront.sqlite"
  $taskWorkflowArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "skills/mindfront/scripts/run_mindfront_workflow.ps1",
    "-BriefPath",
    "examples/briefs/specialist-documentation-brief.json",
    "-ConfigRoot",
    "config",
    "-OutputRoot",
    $taskValidationRoot,
    "-DbPath",
    $taskValidationDb,
    "-TaskValidationInput",
    "examples/task-validation/specialist-documentation-task-validation.json",
    "-Python",
    $Python
  )
  if ($RenderPdf) {
    $taskWorkflowArgs += "-RenderPdf"
  }
  & powershell @taskWorkflowArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Mindfront task-validation workflow failed with exit code $LASTEXITCODE."
  }

  $taskValidationResultPath = Join-Path $taskValidationRoot "task-validation/documentation-task-validation-result.json"
  $taskProtocolPath = Join-Path $taskValidationRoot "task-protocol/documentation-task-observation-protocol.json"
  $taskProtocolMarkdownPath = Join-Path $taskValidationRoot "task-protocol/documentation-task-observation-protocol.md"
  $taskProtocolCsvPath = Join-Path $taskValidationRoot "task-protocol/documentation-task-session-template.csv"
  $taskValidationReportPath = Join-Path $taskValidationRoot "report/mindfront-audit-report.json"
  $taskValidationDashboardPath = Join-Path $taskValidationRoot "dashboard/mindfront-dashboard.json"
  $taskValidationImprovementPath = Join-Path $taskValidationRoot "improvement-plan/mindfront-improvement-plan.json"
  $taskValidationImprovementMarkdownPath = Join-Path $taskValidationRoot "improvement-plan/mindfront-improvement-plan.md"
  foreach ($path in @($taskValidationResultPath, $taskProtocolPath, $taskProtocolMarkdownPath, $taskProtocolCsvPath, $taskValidationReportPath, $taskValidationDashboardPath, $taskValidationImprovementPath, $taskValidationImprovementMarkdownPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
      throw "Expected task-validation artifact is missing: $path"
    }
  }

  $taskProtocol = Get-Content -LiteralPath $taskProtocolPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if ($taskProtocol.artifactType -ne "documentation_task_observation_protocol") {
    throw "Task protocol artifactType is incorrect."
  }
  if ($taskProtocol.marketEvidenceCreated -ne $false) {
    throw "Task protocol must not create market evidence."
  }
  if ($taskProtocol.observationSource -ne "real_task_observation") {
    throw "Task protocol must be a real task-observation collection handoff."
  }
  if (-not ($taskProtocol.sessionTemplateColumns -contains "participantToken")) {
    throw "Task protocol must publish the no-PII session template columns."
  }

  $taskValidationResult = Get-Content -LiteralPath $taskValidationResultPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if ($taskValidationResult.marketEvidenceCreated -ne $false) {
    throw "Task-validation result must not create market evidence."
  }
  if ($taskValidationResult.observationSource -ne "synthetic_fixture") {
    throw "Bundled task-validation fixture must declare observationSource synthetic_fixture."
  }
  if ($taskValidationResult.evidenceBasis -ne "synthetic_task_fixture") {
    throw "Bundled task-validation fixture must keep evidenceBasis synthetic_task_fixture."
  }
  if ($taskValidationResult.evidenceGrade -ne "synthetic_fixture_only") {
    throw "Bundled task-validation fixture must keep synthetic_fixture_only evidence grade."
  }
  if ($taskValidationResult.realTaskEvidenceCreated -ne $false) {
    throw "Bundled task-validation fixture must not create real task evidence."
  }

  $taskValidationReportRaw = Get-Content -LiteralPath $taskValidationReportPath -Raw
  if ($taskValidationReportRaw -match "validated_for_exact_context") {
    throw "Task-validation report must not upgrade confidence to validated_for_exact_context."
  }
  $taskValidationReport = $taskValidationReportRaw | ConvertFrom-Json -ErrorAction Stop
  if ($taskValidationReport.sections.taskValidation.included -ne $true) {
    throw "Task-validation report section was not included."
  }
  if ($taskValidationReport.sections.taskProtocol.included -ne $true) {
    throw "Task protocol report section was not included."
  }
  if ($taskValidationReport.sections.taskProtocol.marketEvidenceCreated -ne $false) {
    throw "Task protocol report section must not create market evidence."
  }
  if ($taskValidationReport.includedArtifactIds -notcontains $taskProtocol.protocolId) {
    throw "Task-validation report did not include the task protocol artifact id."
  }
  if ($taskValidationReport.includedArtifactIds -notcontains $taskValidationResult.validationResultId) {
    throw "Task-validation report did not include the task-validation artifact id."
  }
  if ($taskValidationReport.sections.taskValidation.evidenceBasis -ne "synthetic_task_fixture") {
    throw "Task-validation report must preserve synthetic_task_fixture evidence basis for the bundled fixture."
  }
  if ($taskValidationReport.sections.taskValidation.realTaskEvidenceCreated -ne $false) {
    throw "Task-validation report must not promote the bundled fixture into real task evidence."
  }
  if ($taskValidationReport.sections.taskValidation.marketEvidenceCreated -ne $false) {
    throw "Task-validation report section must not create market evidence."
  }

  $taskValidationDashboard = Get-Content -LiteralPath $taskValidationDashboardPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if ([int]$taskValidationDashboard.summary.taskValidationRunCount -lt 1) {
    throw "Dashboard did not surface stored task-validation evidence."
  }
  if ([int]$taskValidationDashboard.summary.taskProtocolCount -lt 1) {
    throw "Dashboard did not surface stored task-observation protocols."
  }
  if ([int]$taskValidationDashboard.summary.taskValidationSignalCount -ne 0) {
    throw "Synthetic task-validation fixture must not create exact-context task signals in the dashboard."
  }
  if ($taskValidationDashboard.taskValidations[0].observationSource -ne "synthetic_fixture") {
    throw "Dashboard task-validation row must preserve observationSource synthetic_fixture."
  }
  if ($taskValidationDashboard.taskValidations[0].realTaskEvidenceCreated -ne $false) {
    throw "Dashboard task-validation row must not promote the synthetic fixture into real task evidence."
  }
  $taskValidationEvidenceRow = $taskValidationDashboard.evidenceSeparation |
    Where-Object { $_.label -eq "documentation_task_validation" } |
    Select-Object -First 1
  if (-not $taskValidationEvidenceRow) {
    throw "Dashboard evidence-separation manifest is missing documentation_task_validation."
  }
  $taskProtocolEvidenceRow = $taskValidationDashboard.evidenceSeparation |
    Where-Object { $_.label -eq "documentation_task_observation_protocol" } |
    Select-Object -First 1
  if (-not $taskProtocolEvidenceRow) {
    throw "Dashboard evidence-separation manifest is missing documentation_task_observation_protocol."
  }
  $taskValidationImprovement = Get-Content -LiteralPath $taskValidationImprovementPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if ($taskValidationImprovement.artifactType -ne "mindfront_improvement_plan") {
    throw "Improvement plan artifactType is incorrect."
  }
  if ($taskValidationImprovement.marketEvidenceCreated -ne $false) {
    throw "Improvement plan must not create market evidence."
  }
  if ($taskValidationImprovement.notMarketEvidence -ne $true) {
    throw "Improvement plan must remain marked notMarketEvidence."
  }
  $taskValidationImprovementActionTypes = @($taskValidationImprovement.priorityActions | ForEach-Object { $_.actionType })
  if ($taskValidationImprovementActionTypes -contains "reduce_documentation_task_friction") {
    throw "Synthetic task-validation fixture must not create real task-friction improvement actions."
  }
  if ($taskValidationImprovementActionTypes -notcontains "collect_task_sessions_from_protocol") {
    throw "Task protocol handoff should create a collect_task_sessions_from_protocol improvement action."
  }
  $improvementEvidenceRow = $taskValidationDashboard.evidenceSeparation |
    Where-Object { $_.label -eq "mindfront_improvement_plan" } |
    Select-Object -First 1
  if (-not $improvementEvidenceRow) {
    throw "Dashboard evidence-separation manifest is missing mindfront_improvement_plan."
  }

  $taskSessionsRoot = Join-Path $OutputRoot "task-sessions-check"
  $taskSessionsDb = Join-Path $taskSessionsRoot "mindfront.sqlite"
  $filledSessionsCsv = Join-Path $OutputRoot "filled-task-session-template.csv"
  $sessionRows = @()
  for ($i = 0; $i -lt 5; $i++) {
    $task = $taskProtocol.tasks[$i % $taskProtocol.tasks.Count]
    $sessionRows += [pscustomobject][ordered]@{
      sessionId = ("session_{0:000}" -f ($i + 1))
      participantToken = ("participant_{0:000}" -f ($i + 1))
      roleSegment = "target_reader"
      taskId = [string]$task.taskId
      completed = if ($i -lt 4) { "true" } else { "false" }
      skimToAnswerSeconds = [string](45 + $i)
      followUpQuestionCount = if ($i -lt 3) { "0" } else { "1" }
      skippedSectionCount = if ($i -lt 4) { "0" } else { "2" }
      expertRespectRating = "4"
      reuseIntentRating = "4"
      trustObjectionCodes = if ($i -lt 4) { "" } else { "owner_field_missing" }
    }
  }
  $sessionRows | Export-Csv -LiteralPath $filledSessionsCsv -NoTypeInformation -Encoding UTF8

  $taskSessionsWorkflowArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "skills/mindfront/scripts/run_mindfront_workflow.ps1",
    "-BriefPath",
    "examples/briefs/specialist-documentation-brief.json",
    "-ConfigRoot",
    "config",
    "-OutputRoot",
    $taskSessionsRoot,
    "-DbPath",
    $taskSessionsDb,
    "-TaskSessionsCsv",
    $filledSessionsCsv,
    "-Python",
    $Python
  )
  & powershell @taskSessionsWorkflowArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Mindfront task-session CSV workflow failed with exit code $LASTEXITCODE."
  }

  $taskSessionsInputPath = Join-Path $taskSessionsRoot "task-input/documentation-task-validation-input.json"
  $taskSessionsResultPath = Join-Path $taskSessionsRoot "task-validation/documentation-task-validation-result.json"
  $taskSessionsDashboardPath = Join-Path $taskSessionsRoot "dashboard/mindfront-dashboard.json"
  $taskSessionsImprovementPath = Join-Path $taskSessionsRoot "improvement-plan/mindfront-improvement-plan.json"
  foreach ($path in @($taskSessionsInputPath, $taskSessionsResultPath, $taskSessionsDashboardPath, $taskSessionsImprovementPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
      throw "Expected task-session CSV workflow artifact is missing: $path"
    }
  }

  $taskSessionsInput = Get-Content -LiteralPath $taskSessionsInputPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if (-not $taskSessionsInput.sourceProtocolId) {
    throw "Task-session input must carry sourceProtocolId."
  }
  if (-not $taskSessionsInput.sourceSessionsHash) {
    throw "Task-session input must carry sourceSessionsHash."
  }
  if ($taskSessionsInput.observationSource -ne "synthetic_fixture") {
    throw "Generated task-session CSV fixture must default to observationSource synthetic_fixture."
  }

  $taskSessionsResult = Get-Content -LiteralPath $taskSessionsResultPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if ($taskSessionsResult.observationSource -ne "synthetic_fixture") {
    throw "Generated task-session CSV fixture must produce synthetic_fixture results unless real observations are explicitly declared."
  }
  if ($taskSessionsResult.evidenceBasis -ne "synthetic_task_fixture") {
    throw "Generated task-session CSV fixture must produce synthetic_task_fixture evidence basis."
  }
  if ($taskSessionsResult.realTaskEvidenceCreated -ne $false) {
    throw "Generated task-session CSV fixture must not create exact-context real task evidence."
  }
  if ($taskSessionsResult.marketEvidenceCreated -ne $false) {
    throw "Filled task-session CSV workflow must not create market evidence."
  }

  $taskSessionsDashboard = Get-Content -LiteralPath $taskSessionsDashboardPath -Raw | ConvertFrom-Json -ErrorAction Stop
  if ([int]$taskSessionsDashboard.summary.taskValidationSignalCount -ne 0) {
    throw "Generated task-session CSV dashboard must not surface exact-context task signals."
  }
  $taskSessionsImprovement = Get-Content -LiteralPath $taskSessionsImprovementPath -Raw | ConvertFrom-Json -ErrorAction Stop
  $taskSessionsImprovementActionTypes = @($taskSessionsImprovement.priorityActions | ForEach-Object { $_.actionType })
  if ($taskSessionsImprovementActionTypes -contains "reduce_documentation_task_friction") {
    throw "Generated task-session CSV fixture must not create a real task-friction improvement action."
  }
  if ($taskSessionsImprovementActionTypes -notcontains "collect_task_sessions_from_protocol") {
    throw "Generated task-session CSV fixture should still prompt real no-PII task-session collection."
  }
  if ($taskSessionsImprovement.marketEvidenceCreated -ne $false) {
    throw "Task-session improvement plan must not create market evidence."
  }
}
finally {
  Pop-Location
}
