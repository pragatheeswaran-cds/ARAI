param([switch]$Execute)
$ErrorActionPreference = 'Stop'

$taskRoot = [IO.Path]::GetFullPath('E:\Druva Exclude\Pragatheeswaran\XHackathon\final_1')
$taskArchive = [IO.Path]::GetFullPath('E:\Druva Exclude\Pragatheeswaran\XHackathon\final_1-archive-2026-09-25')
$planPath = Join-Path $PSScriptRoot 'archive-plan.json'
$names = @(
    'Adaptive-Return-Abuse-Intelligence-Architecture-and-Plan.docx',
    'Adaptive-Return-Abuse-Intelligence-Architecture-and-Plan.pdf',
    'Adaptive-Return-Abuse-Intelligence-Dataset-Build-Steps.docx',
    'Adaptive-Return-Abuse-Intelligence-Dataset-Build-Steps.pdf',
    'Adaptive-Return-Abuse-Intelligence-HLD.docx',
    'Adaptive-Return-Abuse-Intelligence-HLD.pdf',
    'Adaptive-Return-Abuse-Intelligence-LLD.docx',
    'Adaptive-Return-Abuse-Intelligence-LLD.pdf',
    'Adaptive-Return-Abuse-Intelligence-Judge-Pitch.pptx',
    'Adaptive-Return-Abuse-Intelligence-Team-Kickoff.pptx',
    'Return-Abuse-Data-Dictionary.html',
    'Return-Abuse-HLD-LLD-Summary.html',
    'Return-Abuse-HLD-LLD-Summary.md',
    'web-judge-pitch.html',
    'web-kickoff.html',
    'final_1.zip',
    'return-abuse-synthetic-data.zip',
    'figures',
    'datasets',
    'synthdata'
)

function Assert-Within([string]$Path, [string]$Boundary) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($Boundary + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path outside intended boundary: $full"
    }
    return $full
}

function Get-SafeFiles([string]$Path) {
    $full = Assert-Within $Path $taskRoot
    $item = Get-Item -LiteralPath $full -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point requires separate review: $full" }
    if ($item.PSIsContainer) {
        foreach ($child in (Get-ChildItem -LiteralPath $full -Force)) { Get-SafeFiles $child.FullName }
    } else { $item }
}

if (([IO.Path]::GetDirectoryName($taskArchive) -ne [IO.Path]::GetDirectoryName($taskRoot)) -or
    ([IO.Path]::GetFileName($taskArchive) -ne 'final_1-archive-2026-09-25')) {
    throw 'Archive must be the explicitly named sibling directory.'
}
if (Test-Path -LiteralPath $taskArchive) { throw "Archive already exists; refusing to merge or overwrite: $taskArchive" }

$moves = @()
$files = @()
foreach ($name in $names) {
    $source = Assert-Within (Join-Path $taskRoot $name) $taskRoot
    $destination = Assert-Within (Join-Path $taskArchive $name) $taskArchive
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing planned source: $source" }
    $moves += [pscustomobject]@{ name = $name; source = $source; destination = $destination }
    foreach ($file in (Get-SafeFiles $source)) {
        $files += [pscustomobject]@{
            relative_path = $file.FullName.Substring($taskRoot.Length + 1)
            length = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        }
    }
}

if (-not $Execute) {
    [pscustomobject]@{ source_root = $taskRoot; archive_root = $taskArchive; moves = $moves; files = $files } |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $planPath -Encoding UTF8
    Write-Output "Plan ready: $($moves.Count) top-level items, $($files.Count) files."
    Write-Output "Source: $taskRoot"
    Write-Output "Archive: $taskArchive"
    Write-Output "Bytes: $(($files | Measure-Object -Property length -Sum).Sum)"
    exit 0
}

if (-not (Test-Path -LiteralPath $planPath)) { throw 'Run without -Execute to create the reviewed plan first.' }
$plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
if ($plan.source_root -ne $taskRoot -or $plan.archive_root -ne $taskArchive) { throw 'Plan roots changed.' }
if (($plan.moves.name -join '|') -ne ($names -join '|')) { throw 'Planned move list changed.' }
if ($plan.files.Count -ne $files.Count) { throw 'Source file inventory changed.' }
foreach ($file in $files) {
    $previous = @($plan.files | Where-Object { $_.relative_path -eq $file.relative_path })
    if ($previous.Count -ne 1 -or $previous[0].sha256 -ne $file.sha256 -or $previous[0].length -ne $file.length) {
        throw "Source changed after planning: $($file.relative_path)"
    }
}

New-Item -ItemType Directory -Path $taskArchive | Out-Null
Copy-Item -LiteralPath $planPath -Destination (Join-Path $taskArchive 'archive-manifest.json')
$completed = @()
foreach ($move in $moves) {
    # Every source/destination has been resolved and checked against named boundaries.
    Move-Item -LiteralPath $move.source -Destination $move.destination
    $completed += $move.name
    $completed | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskArchive 'completed-moves.json') -Encoding UTF8
}
foreach ($file in $files) {
    $destination = Assert-Within (Join-Path $taskArchive $file.relative_path) $taskArchive
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $file.sha256) {
        throw "Post-move hash mismatch: $destination"
    }
}
foreach ($move in $moves) {
    if (Test-Path -LiteralPath $move.source) { throw "Original still exists: $($move.source)" }
}
Write-Output "Moved $($moves.Count) top-level items; verified $($files.Count) file hashes."
Write-Output "Archive: $taskArchive"
