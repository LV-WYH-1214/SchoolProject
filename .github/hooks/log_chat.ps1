param(
    [Parameter(Mandatory = $true)]
    [string]$Event,
    [string]$Text = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$outDir = Join-Path $root "AI-Chat-Logs"
$stateDir = Join-Path $outDir ".state"
$pendingFile = Join-Path $stateDir "pending_user.json"
$roundsFile = Join-Path $stateDir "rounds.jsonl"
$indexFile = Join-Path $stateDir "next_index.txt"
$invocationFile = Join-Path $stateDir "hook_invocations.log"
$roundsPerFile = 5

function Ensure-Dirs {
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
    if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir | Out-Null }
    if (-not (Test-Path $indexFile)) { Set-Content -Path $indexFile -Value "1" -Encoding UTF8 }
}

function Now-Iso {
    (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
}

function Get-Index {
    if (-not (Test-Path $indexFile)) { return 1 }
    $raw = (Get-Content -Path $indexFile -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($raw)) { return 1 }
    return [int]$raw
}

function Set-Index([int]$value) {
    Set-Content -Path $indexFile -Value ([string]$value) -Encoding UTF8
}

function Save-PendingUser([string]$text) {
    $obj = @{ time = (Now-Iso); text = $text }
    $json = $obj | ConvertTo-Json -Depth 5
    Set-Content -Path $pendingFile -Value $json -Encoding UTF8
}

function Load-PendingUser {
    if (-not (Test-Path $pendingFile)) { return $null }
    $raw = Get-Content -Path $pendingFile -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Clear-PendingUser {
    if (Test-Path $pendingFile) { Remove-Item $pendingFile -Force }
}

function Append-Round($userObj, $aiObj) {
    $round = @{ user = $userObj; ai = $aiObj }
    $line = ($round | ConvertTo-Json -Compress -Depth 8)
    Add-Content -Path $roundsFile -Value $line -Encoding UTF8
}

function Read-Rounds {
    if (-not (Test-Path $roundsFile)) { return @() }
    $lines = Get-Content -Path $roundsFile -Encoding UTF8
    $items = New-Object System.Collections.ArrayList
    foreach ($line in $lines) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            $null = $items.Add(($line | ConvertFrom-Json))
        }
    }
    return @($items)
}

function Write-Rounds($rounds) {
    if (@($rounds).Count -eq 0) {
        if (Test-Path $roundsFile) { Remove-Item $roundsFile -Force }
        return
    }

    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($r in $rounds) {
        $lines.Add(($r | ConvertTo-Json -Compress -Depth 8))
    }
    Set-Content -Path $roundsFile -Value $lines -Encoding UTF8
}

function Write-ChatFile($rounds) {
    $index = Get-Index
    $fileName = ("chat-{0:D4}.md" -f $index)
    $target = Join-Path $outDir $fileName

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Chat Log {0:D4}" -f $index)
    $lines.Add("")
    $lines.Add("Generated: $(Now-Iso)")
    $lines.Add("Rounds: $(@($rounds).Count)")
    $lines.Add("")

    $i = 1
    foreach ($r in $rounds) {
        $u = $r.user
        $a = $r.ai
        $lines.Add("## Round $i")
        $lines.Add("")
        $lines.Add("### User @ $($u.time)")
        $lines.Add("")
        $lines.Add([string]$u.text)
        $lines.Add("")
        $lines.Add("### AI @ $($a.time)")
        $lines.Add("")
        $lines.Add([string]$a.text)
        $lines.Add("")
        $i++
    }

    Set-Content -Path $target -Value ($lines -join "`n") -Encoding UTF8
    Set-Index ($index + 1)
    return $fileName
}

function Flush-IfReady {
    $rounds = Read-Rounds
    if (@($rounds).Count -lt $roundsPerFile) { return $null }

    $chunk = @($rounds[0..($roundsPerFile - 1)])
    if (@($rounds).Count -gt $roundsPerFile) {
        $rest = @($rounds[$roundsPerFile..(@($rounds).Count - 1)])
        Write-Rounds $rest
    }
    else {
        Write-Rounds @()
    }

    return (Write-ChatFile $chunk)
}

function Flush-AllRemaining {
    $rounds = Read-Rounds
    if (@($rounds).Count -eq 0) { return $null }
    Write-Rounds @()
    return (Write-ChatFile $rounds)
}

function Normalize-Role([string]$ev) {
    $e = $ev.ToLowerInvariant()
    if ($e.Contains("user") -or $e.Contains("prompt")) { return "user" }
    if ($e.Contains("assistant") -or $e.Contains("response") -or $e.Contains("ai")) { return "ai" }
    return "system"
}

function Resolve-Text([string]$provided) {
    if (-not [string]::IsNullOrWhiteSpace($provided)) { return $provided }

    try {
        $raw = [Console]::In.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($raw)) { return "" }

        try {
            $obj = $raw | ConvertFrom-Json
            $candidates = @($obj.text, $obj.message, $obj.content, $obj.prompt, $obj.response, $obj.output)
            foreach ($c in $candidates) {
                if ($null -ne $c -and -not [string]::IsNullOrWhiteSpace([string]$c)) {
                    return [string]$c
                }
            }
            return $raw.Trim()
        }
        catch {
            return $raw.Trim()
        }
    }
    catch {
        return ""
    }
}

function Write-Invocation([string]$eventName, [string]$roleName, [string]$textValue) {
    $shortText = $textValue
    if ($shortText.Length -gt 60) {
        $shortText = $shortText.Substring(0, 60) + "..."
    }
    $line = "$(Now-Iso)`tevent=$eventName`trole=$roleName`ttextLen=$($textValue.Length)`ttext=$shortText"
    Add-Content -Path $invocationFile -Value $line -Encoding UTF8
}

Ensure-Dirs
$role = Normalize-Role $Event
$eventLower = $Event.ToLowerInvariant()
$Text = Resolve-Text $Text
Write-Invocation $Event $role $Text

if ($eventLower -eq "sessionstart") {
    Write-Output "session_started"
    exit 0
}

if ($role -eq "user") {
    $previousPending = Load-PendingUser
    if ($null -ne $previousPending) {
        $userObj = @{ time = $previousPending.time; text = [string]$previousPending.text }
        $aiObj = @{ time = (Now-Iso); text = "(AI response hook not triggered)" }
        Append-Round $userObj $aiObj

        $writtenFromFallback = Flush-IfReady
        if ($null -ne $writtenFromFallback) {
            Write-Output "written:$writtenFromFallback"
        }
    }

    Save-PendingUser $Text
    Write-Output "ok"
    exit 0
}

if ($role -eq "ai") {
    $pending = Load-PendingUser
    if ($null -ne $pending) {
        $userObj = @{ time = $pending.time; text = [string]$pending.text }
        Clear-PendingUser
    }
    else {
        $userObj = @{ time = (Now-Iso); text = "(missing user message)" }
    }

    $aiObj = @{ time = (Now-Iso); text = $Text }
    Append-Round $userObj $aiObj

    $written = Flush-IfReady
    if ($null -ne $written) {
        Write-Output "written:$written"
    }
    else {
        Write-Output "ok"
    }
    exit 0
}

if ($eventLower -eq "sessionend" -or $eventLower -eq "conversationend") {
    $pendingAtEnd = Load-PendingUser
    if ($null -ne $pendingAtEnd) {
        $userObj = @{ time = $pendingAtEnd.time; text = [string]$pendingAtEnd.text }
        $aiObj = @{ time = (Now-Iso); text = "(AI response hook not triggered)" }
        Append-Round $userObj $aiObj
        Clear-PendingUser
    }

    $written = Flush-AllRemaining
    if ($null -ne $written) {
        Write-Output "written:$written"
    }
    else {
        Write-Output "ok"
    }
    exit 0
}

Write-Output "ok"
