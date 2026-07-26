# Reads products/_series-roadmap.json for the next pending cuisines and asks
# Claude Code to run world-cuisine-meal-planner-pipeline's batch mode on them.
# This does NOT bypass Claude Code's permission system -- it uses whatever
# permission mode/settings are already configured for this machine/project.
# Double-click run-next-batch.bat (in this same folder) to launch this.

param(
    [int]$Count = 5
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$roadmapPath = Join-Path $repoRoot "products\_series-roadmap.json"

if (-not (Test-Path $roadmapPath)) {
    Write-Host "Could not find $roadmapPath -- is this script still inside digital-product-agent\scripts\?"
    exit 1
}

$roadmap = Get-Content $roadmapPath -Raw | ConvertFrom-Json
$pending = $roadmap.cuisines | Where-Object { $_.status -eq "pending" }

if ($pending.Count -eq 0) {
    Write-Host "No pending cuisines left in _series-roadmap.json -- every planned cuisine is already done."
    exit 0
}

$next = $pending | Select-Object -First $Count
$names = ($next | ForEach-Object { $_.name }) -join ", "

Write-Host "$($pending.Count) cuisines still pending. Asking Claude Code to build the next $($next.Count): $names"
Write-Host ""

Set-Location $repoRoot

$prompt = "world-cuisine-meal-planner-pipeline 스킬의 배치 모드를 실행해줘. products/_series-roadmap.json에서 status가 pending인 항목을 순서대로 $Count 개 가져와서 국가당 8개 요리를 정하고, 병렬로 draft-en.md 작성, 웹검색 사실확인, 사진 소싱, recipes.json, 시각적 카드, Notion 템플릿, 가격조사 워크시트까지 전체 파이프라인을 처리해줘. 다 끝나면 로드맵의 status를 done으로 갱신하고 모든 국가의 footer 문구를 확인한 뒤 git commit + push까지 해줘."

# -p runs a single non-interactive prompt to completion (supports the full
# Task/Agent/MCP/file-edit tool set). No permission-bypass flags are used --
# this follows whatever Claude Code permission mode is already configured.
claude -p $prompt
