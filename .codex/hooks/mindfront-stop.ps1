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

if ($event.stop_hook_active -eq $true) {
  exit 0
}

try {
  . (Join-Path $PSScriptRoot "mindfront-common.ps1")
}
catch {
  exit 0
}

$completionPattern = '(?i)\b(done|completed|implemented|generated|created|finished|verified|updated|improved|polished|edited|drafted|refined|packaged|wrote|written|report written|audit report|dashboard written|workflow complete|here\s+(?:are|is)|revised|rewritten|variants?|recommendations?)\b'
$artifactPattern = '(?i)\b(message-analysis-report\.json|copy-variants\.json|variant-comparison\.json|reader-stress-test\.json|research-plan\.json|documentation-task-observation-protocol\.(?:json|md)|documentation-task-session-template\.csv|documentation-task-validation-input\.json|documentation-task-validation-result\.json|source\.html|mindfront-audit-report(?:\.json|\.md|\.html|\.pdf)?|mindfront-audit-scorecard\.csv|mindfront-dashboard\.json|mindfront-improvement-plan\.(?:json|md)|mindfront-document-workflow-handoff\.md|mindfront-documentation-flow-result\.json|test-output[\\/][^\s,;:]+|report\s+path\s*[:=]|dashboard\s+path\s*[:=])\b'
$boundaryPattern = '(?i)\b(marketEvidenceCreated\s*[:=]?\s*false|notMarketEvidence|not\s+market\s+evidence|evidence\s+boundary|synthetic\s+reader(?:\s+stress\s+test)?|synthetic\s+task(?:-|\s+)validation|realTaskEvidenceCreated\s*[:=]?\s*false|exact-context\s+task\s+evidence|task[- ]observation\s+protocol\s+handoff|collection\s+handoff|heuristic\s+hypothes(?:is|es)|unsupported\s+claims?|research\s+handoff|what\s+to\s+test\s+next)\b'
$skipPattern = '(?i)\b(read-only/non-artifact|read-only\s+answer|non-artifact\s+answer|full\s+workflow\s+was\s+not\s+needed|no\s+artifact\s+was\s+needed)\b'
$reportRequestPattern = '(?i)\b(audit\s+reports?|documentation\s+deliverable|document\s+deliverable|polished\s+documentation\s+deliverable|package\s+(?:this|it|that)\s+as\s+a\s+report|report\s+and\s+dashboard|report\s+package|create\s+a\s+(?:polished\s+)?report)\b'
$pdfRequestPattern = '(?i)\b(pdf|report\s+as\s+a\s+pdf|render\s+(?:this|the|a)?\s*report\s+as\s+a\s+pdf|documentation\s+deliverable|document\s+deliverable|polished\s+documentation\s+deliverable)\b'
$dashboardRequestPattern = '(?i)\b(dashboard|local\s+dashboard|history\s+dashboard|report\s+and\s+dashboard)\b'
$taskProtocolRequestPattern = '(?i)\b(task[- ]observation\s+protocol|task\s+observation\s+kit|observation\s+protocol|observer\s+kit|session\s+template|documentation[- ]task\s+protocol)\b'
$taskValidationRequestPattern = '(?i)\b(task[- ]validation|validation\s+input|documentation[- ]task\s+validation|executive\s+impact\s+loop|measured\s+documentation[- ]use|documentation[- ]use\s+observations?)\b'
$improvementRequestPattern = '(?i)\b(improvement[- ]plan|improvement\s+backlog|next[- ]action\s+backlog|next\s+actions?\s+from\s+(?:the\s+)?(?:mindfront\s+)?history(?:\s+db)?|next\s+actions?\s+from\s+stored\s+mindfront\s+runs|documentation\s+improvement\s+loop|repeat(?:ed)?\s+documentation\s+improvement|history[- ]to[- ]next[- ]run|feedback\s+loop)\b'
$reportArtifactSetPattern = '(?i)\b(source\.html|mindfront-audit-report\.(?:json|md|html)|mindfront-document-workflow-handoff\.md)\b'
$taskProtocolArtifactPattern = '(?i)\b(documentation-task-observation-protocol\.(?:json|md)|documentation-task-session-template\.csv|task-protocol[\\/][^\s,;:]+)\b'
$taskValidationArtifactPattern = '(?i)\b(documentation-task-validation-result\.json|task-validation[\\/][^\s,;:]+)\b'
$pdfArtifactSetPattern = '(?i)\b(mindfront-documentation-flow-result\.json)\b'
$pdfFilePattern = '(?i)\b([A-Za-z0-9][A-Za-z0-9._-]*\.pdf|docs-deliverables[\\/][^\s,;:]+\.pdf|test-output[\\/][^\s,;:]+\.pdf)\b'
$dashboardArtifactPattern = '(?i)\b(mindfront-dashboard\.json|dashboard\s+path\s*[:=]|dashboard[\\/][^\s,;:]+)\b'
$improvementArtifactPattern = '(?i)\b(mindfront-improvement-plan\.json)\b'
$improvementOperationalPattern = '(?i)\b(operational\s+backlog|operational\s+next\s+actions?|improvement\s+plans?\s+(?:are|is)\s+operational|rank(?:ed|s)?\s+operational)\b'
$improvementNonEvidencePattern = '(?i)\b(marketEvidenceCreated\s*[:=]?\s*false|notMarketEvidence\s*[:=]?\s*true|not\s+market\s+evidence|not\s+(?:preference|conversion|adoption|performance|c-suite|company-wide)\s+proof|does\s+not\s+prove)\b'
$visualQaPattern = '(?i)\b(visual\s*qa|visualQaStatus|inspected\s+the\s+rendered\s+pdf|inspected\s+the\s+pdf|rendered_nonempty|passed_by_caller)\b'
$workplaceCompletionPattern = '(?i)\b(here(?:''s|\s+is|\s+are)|recommend(?:ed|ation)?|draft(?:ed)?|prepared|preflight|debrief|interpretation|next\s+(?:step|action)|30[- ]second|career\s+evidence|authority\s+state|credit\s+framing)\b'
$workplaceConcreteGuidancePattern = '(?i)\b(observed\s+facts?|facts?|possible\s+interpretations?|alternative\s+interpretations?|unknowns?|recommended\s+move|recommended\s+next\s+step|next\s+action|clarifying\s+question|30[- ]second\s+version|if[- ]interrupted|draft(?:ed)?\s+(?:response|message)|suggested\s+wording|authority\s+state|credit\s+framing|meeting\s+opening|debrief|reply|respond|say|ask)\b'
$workplaceEvidenceBoundaryPattern = '(?i)\b(possible\s+interpretation|alternative\s+interpretation|unknown|uncertain|cannot\s+know|do\s+not\s+know|don''t\s+know|not\s+psychological\s+truth|not\s+a\s+prediction|directional|one\s+plausible\s+reading|could\s+mean|may\s+mean)\b'
$workplaceDraftRequestPattern = '(?i)\b(reword|rewrite|wording|compose|draft|write|refine|polish|make\s+(?:this|it)\s+sound\s+better|help\s+me\s+(?:respond|reply)|how\s+should\s+i\s+(?:respond|reply)|response\s+to|reply\s+to)\b'
$workplaceExplanatoryRequestPattern = '(?i)\b(what\s+does|what\s+might|interpret|interpretation|debrief|career[- ]review|assess|evaluate|why\s+(?:did|does|would))\b'
$workplaceDraftMetaPattern = '(?im)(?:^|\n)\s*(?:draft\s+for\s+(?:your\s+)?review|note\s*:|mindfront(?:''s)?\s+(?:private|stored|profile)|human\s+review\s+(?:is\s+)?required|review\s+before\s+(?:sending|using))\b'
$workplaceNeedsInputPattern = '(?i)\b(please\s+(?:paste|share|provide)|need\s+(?:the|more)\s+(?:message|context|text|details)|cannot\s+assess\s+without|can\s+help\s+once)\b'
$workplaceInternalStateCertaintyPattern = '(?i)\b(?:they|he|she|the\s+(?:leader|manager|stakeholder|coworker|colleague))\s+(?:definitely|obviously|clearly)\s+(?:thinks?|feels?|wants?|intends?|is\s+trying)\b'
$workplaceDirectInternalStateAssertionPattern = '(?im)(?:^|[.!?]\s+)(?:they|he|she|the\s+(?:leader|manager|stakeholder|coworker|colleague))\s+(?:hates?|resents?|is\s+jealous|is\s+threatened|wants?\s+you\s+to\s+fail|is\s+trying\s+to\s+(?:block|undermine|embarrass))\b'
$workplaceCoworkerEvaluationPattern = '(?i)\b(?:your\s+)?(?:coworker|colleague|manager|stakeholder|candidate|he|she|they)\s+(?:is|are|was|were)\s+(?:incompetent|unqualified|lazy|clueless|bad\s+at\s+(?:their|the)\s+job|worse\s+than)\b'
$workplaceManipulationPattern = '(?i)\b(?:use|exploit)\s+(?:their|his|her)\s+(?:fear|insecurity|weakness|anxiety)|\bmake\s+(?:them|him|her)\s+feel\s+(?:afraid|insecure|dependent)|\bwithhold\s+(?:information|credit)\s+to\s+(?:pressure|control|force)\b'
$workplaceOutcomeGuaranteePattern = '(?i)\b(?:you|the\s+user)\s+(?:will|are\s+guaranteed\s+to)\s+(?:be\s+promoted|get\s+approval|win\s+approval|become\s+an?\s+fte)\b'
$workplaceMonopolyRecommendationPattern = '(?i)\b(?:(?:position|make)\s+(?:yourself|the\s+user)\s+as|you\s+should\s+(?:be|become))\s+(?:the\s+)?sole\s+(?:source|owner|expert)\b'
$workplaceNegatedMonopolyPattern = '(?i)\b(?:(?:do\s+not|don''t|never|avoid)\s+(?:position|make)\s+(?:yourself|the\s+user)\s+as|(?:you|the\s+user)\s+(?:should\s+not|shouldn''t)\s+(?:be|become))\s+(?:the\s+)?sole\s+(?:source|owner|expert)\b'
$workplaceSentClaimPattern = '(?i)\b(?:I|Mindfront)\s+(?:sent|posted|emailed|messaged)\b'

function Get-ContentText {
  param($Content)

  if ($null -eq $Content) {
    return $null
  }

  if ($Content -is [string]) {
    return [string]$Content
  }

  $parts = @()
  foreach ($item in @($Content)) {
    if ($item.text) {
      $parts += [string]$item.text
      continue
    }

    if ($item.content) {
      $nested = Get-ContentText $item.content
      if (-not [string]::IsNullOrWhiteSpace($nested)) {
        $parts += $nested
      }
    }
  }

  if ($parts.Count -eq 0) {
    return $null
  }

  return ($parts -join "`n")
}

function Get-LatestTranscriptMessage {
  param(
    [string]$TranscriptPath,
    [string]$Role
  )

  if ([string]::IsNullOrWhiteSpace($TranscriptPath) -or -not (Test-Path -LiteralPath $TranscriptPath)) {
    return $null
  }

  $latest = $null
  $stream = $null
  $reader = $null

  try {
    $stream = [System.IO.File]::Open($TranscriptPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    $reader = New-Object System.IO.StreamReader($stream)

    while (-not $reader.EndOfStream) {
      $line = $reader.ReadLine()
      if ([string]::IsNullOrWhiteSpace($line)) {
        continue
      }

      try {
        $record = $line | ConvertFrom-Json -ErrorAction Stop
      }
      catch {
        continue
      }

      if ($record.type -eq "event_msg" -and $Role -eq "user" -and $record.payload.type -eq "user_message") {
        $latest = [string]$record.payload.message
        continue
      }

      if ($record.type -eq "event_msg" -and $Role -eq "assistant" -and $record.payload.type -in @("assistant_message", "agent_message")) {
        $latest = [string]$record.payload.message
        continue
      }

      if ($record.type -eq "response_item" -and $record.payload.type -eq "message" -and $record.payload.role -eq $Role) {
        $message = Get-ContentText $record.payload.content
        if (-not [string]::IsNullOrWhiteSpace($message)) {
          $latest = $message
        }
      }
    }
  }
  finally {
    if ($reader) { $reader.Dispose() }
    if ($stream) { $stream.Dispose() }
  }

  return $latest
}

$lastUserPrompt = Get-LatestTranscriptMessage ([string]$event.transcript_path) "user"
if ([string]::IsNullOrWhiteSpace($lastUserPrompt)) {
  $lastUserPrompt = [string]$event.prompt
}

$route = Get-MindfrontPromptRoute $lastUserPrompt
if ($route -eq "none") {
  exit 0
}
if ($route -eq "mindfront_reference") {
  exit 0
}

$lastAssistant = [string]$event.last_assistant_message
if ([string]::IsNullOrWhiteSpace($lastAssistant)) {
  $lastAssistant = Get-LatestTranscriptMessage ([string]$event.transcript_path) "assistant"
}
if ([string]::IsNullOrWhiteSpace($lastAssistant)) {
  $lastAssistant = [string]$event.final_response
}
if ([string]::IsNullOrWhiteSpace($lastAssistant)) {
  $lastAssistant = [string]$event.response
}
if ([string]::IsNullOrWhiteSpace($lastAssistant)) {
  exit 0
}

$hasMindfrontArtifact = $lastAssistant -match $artifactPattern
$hasEvidenceBoundary = $lastAssistant -match $boundaryPattern
$hasExplicitSkip = $lastAssistant -match $skipPattern
$requiresReportArtifacts = $lastUserPrompt -match $reportRequestPattern
$requiresPdfArtifacts = $lastUserPrompt -match $pdfRequestPattern
$requiresDashboardArtifacts = $lastUserPrompt -match $dashboardRequestPattern
$requiresTaskProtocolArtifacts = $lastUserPrompt -match $taskProtocolRequestPattern
$requiresTaskValidationArtifacts = $lastUserPrompt -match $taskValidationRequestPattern
$requiresImprovementArtifacts = $lastUserPrompt -match $improvementRequestPattern
$hasReportArtifactSet = $lastAssistant -match $reportArtifactSetPattern
$hasTaskProtocolArtifact = $lastAssistant -match $taskProtocolArtifactPattern
$hasTaskValidationArtifact = $lastAssistant -match $taskValidationArtifactPattern
$hasPdfArtifactSet = ($lastAssistant -match $pdfArtifactSetPattern) -and ($lastAssistant -match $pdfFilePattern)
$hasDashboardArtifact = $lastAssistant -match $dashboardArtifactPattern
$hasImprovementArtifact = $lastAssistant -match $improvementArtifactPattern
$hasImprovementEvidenceBoundary = (
  ($lastAssistant -match $improvementOperationalPattern) -and
  ($lastAssistant -match $improvementNonEvidencePattern)
)
$hasVisualQa = $lastAssistant -match $visualQaPattern

function Write-MindfrontBlock {
  param([string]$Reason)

  [ordered]@{
    decision = "block"
    reason = $Reason
  } | ConvertTo-Json -Depth 4 -Compress
}

if ($route -eq "workplace_assistance") {
  $workplaceSafetyScanText = [regex]::Replace(
    $lastAssistant,
    $workplaceNegatedMonopolyPattern,
    ""
  )
  if (
    $lastAssistant -match $workplaceInternalStateCertaintyPattern -or
    $lastAssistant -match $workplaceDirectInternalStateAssertionPattern -or
    $lastAssistant -match $workplaceOutcomeGuaranteePattern -or
    $workplaceSafetyScanText -match $workplaceMonopolyRecommendationPattern
  ) {
    Write-MindfrontBlock "This workplace-assistance response presents an internal state, career outcome, or sole-source position with unsupported certainty. Separate facts from possible interpretations, preserve distributed ownership, and keep outcomes unpredicted."
    exit 0
  }

  if ($lastAssistant -match $workplaceSentClaimPattern) {
    Write-MindfrontBlock "Mindfront workplace assistance is draft-only and must never claim to have sent, posted, emailed, or messaged the assisted content."
    exit 0
  }

  if ($lastAssistant -match $workplaceCoworkerEvaluationPattern) {
    Write-MindfrontBlock "Mindfront workplace assistance must not evaluate a coworker or candidate. Describe observable work, the concrete impact, and the requested correction without labeling the person."
    exit 0
  }

  if ($lastAssistant -match $workplaceManipulationPattern) {
    Write-MindfrontBlock "Mindfront workplace assistance must not recommend exploiting fear, insecurity, weakness, dependence, or withheld information or credit. Use transparent requests and preserve the other person's agency."
    exit 0
  }

  if ($lastAssistant -match $workplaceNeedsInputPattern) {
    exit 0
  }

  $isPasteReadyDraftRequest = (
    $lastUserPrompt -match $workplaceDraftRequestPattern -and
    $lastUserPrompt -notmatch $workplaceExplanatoryRequestPattern
  )
  if ($isPasteReadyDraftRequest) {
    if ($lastAssistant -match $workplaceDraftMetaPattern) {
      Write-MindfrontBlock "This response appends Mindfront, profile, coverage, or review meta-commentary to a paste-ready workplace draft. Return only the intended message text; preserve human review structurally by never auto-sending."
    }
    exit 0
  }

  $hasConcreteGuidance = $lastAssistant -match $workplaceConcreteGuidancePattern
  $hasWorkplaceEvidenceBoundary = $lastAssistant -match $workplaceEvidenceBoundaryPattern
  if (-not ($hasConcreteGuidance -and $hasWorkplaceEvidenceBoundary)) {
    Write-MindfrontBlock "This workplace-assistance response does not include concrete guidance and an uncertainty or interpretation boundary. Complete the inline assistance contract; a report file is not required. Human review is enforced by the draft-only, no-auto-send workflow and does not require an appended disclaimer."
  }
  exit 0
}

if (-not $hasExplicitSkip) {
  if ($requiresPdfArtifacts -and -not ($hasReportArtifactSet -and $hasPdfArtifactSet -and $hasVisualQa -and $hasEvidenceBoundary)) {
    Write-MindfrontBlock "This looks like a completed Mindfront PDF/documentation deliverable, but the final response does not mention source.html, the final .pdf artifact, mindfront-documentation-flow-result.json, rendered-PDF inspection or visual QA status, and the evidence boundary. Continue the documentation workflow before finalizing."
    exit 0
  }

  if ($requiresDashboardArtifacts -and -not ($hasDashboardArtifact -and $hasEvidenceBoundary -and ((-not $requiresReportArtifacts) -or $hasReportArtifactSet))) {
    Write-MindfrontBlock "This looks like a completed Mindfront dashboard workflow, but the final response does not mention the required dashboard artifacts, evidence boundary, and report artifacts when a report was also requested. Continue the repo-local Mindfront workflow before finalizing."
    exit 0
  }

  if ($requiresTaskProtocolArtifacts -and -not ($hasTaskProtocolArtifact -and $hasEvidenceBoundary)) {
    Write-MindfrontBlock "This looks like a completed Mindfront task-observation protocol workflow, but the final response does not mention documentation-task-observation-protocol.json, documentation-task-session-template.csv, and the protocol evidence boundary. Continue the repo-local Mindfront workflow before finalizing."
    exit 0
  }

  if ($requiresTaskValidationArtifacts -and -not ($hasTaskValidationArtifact -and $hasEvidenceBoundary)) {
    Write-MindfrontBlock "This looks like a completed Mindfront task-validation workflow, but the final response does not mention documentation-task-validation-result.json and the task-validation evidence boundary. Continue the repo-local Mindfront workflow before finalizing."
    exit 0
  }

  if ($requiresImprovementArtifacts -and -not ($hasImprovementArtifact -and $hasImprovementEvidenceBoundary)) {
    Write-MindfrontBlock "This looks like a completed Mindfront improvement-loop workflow, but the final response does not mention mindfront-improvement-plan.json and the improvement-plan evidence boundary: operational backlog plus explicit not-market-evidence/no-proof language. Continue the repo-local Mindfront workflow before finalizing."
    exit 0
  }

  if ($requiresReportArtifacts -and -not ($hasReportArtifactSet -and $hasEvidenceBoundary)) {
    Write-MindfrontBlock "This looks like a completed Mindfront report workflow, but the final response does not mention the report source/handoff artifacts and the evidence boundary. Continue the repo-local Mindfront workflow before finalizing."
    exit 0
  }
}

if ($lastAssistant -match $completionPattern -and -not $hasExplicitSkip) {
  if (-not ($hasMindfrontArtifact -and $hasEvidenceBoundary)) {
    Write-MindfrontBlock "This looks like a completed message-quality or pre-research workflow, but the final response does not mention both concrete Mindfront artifacts and evidence boundaries. Continue with the repo-local Mindfront workflow, or explicitly state that this was only a read-only/non-artifact answer and why the full workflow was not needed."
  }
}
