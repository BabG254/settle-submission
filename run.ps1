<#
.SYNOPSIS
  Windows replacement for the Makefile. Same target names.

.EXAMPLE
  .\run.ps1 offline
  .\run.ps1 baseline-a agent ablations report
  .\run.ps1 all

.NOTES
  PowerShell 5.1 has no '&&'. Pass several targets as arguments instead;
  they run in order and the script stops on the first failure.
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Targets = @('help')
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

# --- find a Python -----------------------------------------------------------
$PY = $null
foreach ($c in @('python', 'py', 'python3')) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $v = & $c --version 2>&1
        if ($v -match 'Python 3\.(\d+)' -and [int]$Matches[1] -ge 10) { $PY = $c; break }
    }
}
if (-not $PY) {
    Write-Host "No Python 3.10+ found on PATH." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
    exit 1
}

# --- load .env into this process --------------------------------------------
if (Test-Path '.env') {
    Get-Content '.env' | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $k, $v = $line.Split('=', 2)
            $k = $k.Trim(); $v = $v.Trim().Trim('"').Trim("'")
            if ($k) { Set-Item -Path "Env:$k" -Value $v }
        }
    }
}

# Paid targets resume by default: an interrupted run must not pay twice for
# cases it already completed. Set SETTLE_FRESH=1 to force everything to re-run.
$RESUME = if ($env:SETTLE_FRESH -eq '1') { @() } else { @('--resume') }

$DATA = 'data'
$RES  = 'results'
if (-not $env:SETTLE_MODEL) { $env:SETTLE_MODEL = 'claude-sonnet-4-6' }
$MODEL = $env:SETTLE_MODEL

function Invoke-Py {
    param([string[]]$PyArgs)
    Write-Host ">> $PY $($PyArgs -join ' ')" -ForegroundColor DarkGray
    & $PY @PyArgs
    if ($LASTEXITCODE -ne 0) { throw "command failed with exit code $LASTEXITCODE" }
}

function Require-Key {
    if ($env:SETTLE_PROVIDER -eq 'openai') {
        if (-not $env:SETTLE_API_KEY) {
            throw "SETTLE_API_KEY is not set. SETTLE_PROVIDER=openai needs it in .env."
        }
        if (-not $env:SETTLE_BASE_URL) {
            throw "SETTLE_BASE_URL is not set. SETTLE_PROVIDER=openai needs it in .env."
        }
        return
    }
    if (-not $env:ANTHROPIC_API_KEY) {
        throw "ANTHROPIC_API_KEY is not set. Put it in .env, or run: `$env:ANTHROPIC_API_KEY = 'sk-ant-...'"
    }
}

function Score {
    param([string]$PredDir, [string]$OutFile, [string]$Data = $DATA)
    Invoke-Py @('-m', 'settle.score', '--pred-dir', $PredDir, '--data', $Data, '--out', $OutFile)
}

# --- targets -----------------------------------------------------------------
function Target-Help {
    Write-Host ""
    Write-Host "Settle -- mobile-money reconciliation agent" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  .\run.ps1 offline       data + the three runs needing no API key + report"
    Write-Host "  .\run.ps1 all           everything, including the model runs"
    Write-Host ""
    Write-Host "  estimate      project the cost before running anything" -ForegroundColor Green
    Write-Host "  doctor        check key, workspace and model before paying" -ForegroundColor Green
    Write-Host "  models        list models your key can actually use" -ForegroundColor Green
    Write-Host "  data          regenerate the corpus (seed 42)"
    Write-Host "  baseline-b    deterministic script matcher       (no key)"
    Write-Host "  core          Settle tool layer, no model        (no key)"
    Write-Host "  ceiling       perfect-identity headroom run      (no key)"
    Write-Host "  baseline-a    one direct prompt                  (needs key)"
    Write-Host "  agent         full Settle                        (needs key)"
    Write-Host "  ablations     the changelog runs                 (needs key)"
    Write-Host "  demo-memory   month 1 of the alias memory demo   (needs key)"
    Write-Host "  trajectories  render agent logs to markdown"
    Write-Host "  report        rebuild results\RESULTS.md"
    Write-Host "  clean         delete generated artefacts"
    Write-Host ""
    Write-Host "Python in use: $PY" -ForegroundColor DarkGray
    Write-Host "Model:         $MODEL" -ForegroundColor DarkGray
    if ($env:ANTHROPIC_WORKSPACE_ID) {
        Write-Host "Workspace:     $env:ANTHROPIC_WORKSPACE_ID" -ForegroundColor DarkGray
    } else {
        Write-Host "Workspace:     not set (only needed for multi-workspace keys)" -ForegroundColor DarkGray
    }
    if ($env:ANTHROPIC_API_KEY) {
        Write-Host "API key:       set" -ForegroundColor DarkGray
    } else {
        Write-Host "API key:       NOT SET (offline targets still work)" -ForegroundColor Yellow
    }
    Write-Host ""
}

function Target-Estimate {
    Invoke-Py @('-m', 'settle.estimate')
}

function Target-Doctor {
    Invoke-Py @('-m', 'settle.doctor')
}

function Target-Models {
    Invoke-Py @('-m', 'settle.doctor', '--list-models')
}

function Target-Data {
    Invoke-Py @('-m', 'settle.gen', '--seed', '42', '--out', $DATA)
}

function Target-BaselineB {
    Invoke-Py @('-m', 'settle.baselines', '--which', 'b', '--data', $DATA,
                '--out', "$RES\pred_baseline_b")
    Score "$RES\pred_baseline_b" "$RES\score_baseline_b.json"
}

function Target-Core {
    Invoke-Py @('-m', 'settle.agent', '--data', $DATA, '--out', "$RES\pred_settle_core",
                '--outputs', 'outputs\core', '--no-adjudicator', '--no-memory',
                '--trace', 'trajectories\core')
    Score "$RES\pred_settle_core" "$RES\score_settle_core.json"
}

function Target-Ceiling {
    Invoke-Py @('-m', 'settle.agent', '--data', $DATA, '--out', "$RES\pred_settle_ceiling",
                '--outputs', 'outputs\ceiling', '--identity-oracle', '--no-memory')
    Score "$RES\pred_settle_ceiling" "$RES\score_settle_ceiling.json"
}

function Target-BaselineA {
    Require-Key
    $a = @('-m', 'settle.baselines', '--which', 'a', '--data', $DATA,
           '--out', "$RES\pred_baseline_a", '--model', $MODEL) + $RESUME
    Invoke-Py $a
    Score "$RES\pred_baseline_a" "$RES\score_baseline_a.json"
}

function Target-Agent {
    Require-Key
    $a = @('-m', 'settle.agent', '--data', $DATA, '--out', "$RES\pred_settle_full",
           '--outputs', 'outputs\full', '--model', $MODEL, '--reset-memory',
           '--trace', 'trajectories\full') + $RESUME
    Invoke-Py $a
    Score "$RES\pred_settle_full" "$RES\score_settle_full.json"
}

function Target-Ablations {
    Require-Key
    $a = @('-m', 'settle.agent', '--data', $DATA, '--out', "$RES\pred_settle_fullctx",
           '--outputs', 'outputs\fullctx', '--model', $MODEL, '--full-context', '--no-memory') + $RESUME
    Invoke-Py $a
    Score "$RES\pred_settle_fullctx" "$RES\score_settle_fullctx.json"

    $a = @('-m', 'settle.agent', '--data', $DATA, '--out', "$RES\pred_settle_noverify",
           '--outputs', 'outputs\noverify', '--model', $MODEL, '--no-verifier', '--no-memory') + $RESUME
    Invoke-Py $a
    Score "$RES\pred_settle_noverify" "$RES\score_settle_noverify.json"

    $a = @('-m', 'settle.agent', '--data', $DATA, '--out', "$RES\pred_settle_nomem",
           '--outputs', 'outputs\nomem', '--model', $MODEL, '--no-memory') + $RESUME
    Invoke-Py $a
    Score "$RES\pred_settle_nomem" "$RES\score_settle_nomem.json"
}

function Target-DemoMemory {
    Require-Key
    if (Test-Path 'state\demo.db') { Remove-Item 'state\demo.db' -Force }
    Invoke-Py @('-m', 'settle.agent', '--data', "$DATA\memory_demo", '--cases', 'month01',
                '--out', "$RES\pred_demo", '--outputs', 'outputs\demo', '--model', $MODEL,
                '--memory-db', 'state\demo.db', '--trace', 'trajectories\demo')
    Write-Host ""
    Write-Host "--- month 01 exception queue (cold memory) ---" -ForegroundColor Cyan
    Invoke-Py @('-m', 'settle.show', 'queue', '--pred', "$RES\pred_demo\month01.json",
                '--data', "$DATA\memory_demo")
}

function Target-Trajectories {
    foreach ($d in @('full', 'core', 'demo')) {
        if (Test-Path "trajectories\$d") {
            Invoke-Py @('-m', 'settle.trajectory', '--in', "trajectories\$d",
                        '--out', 'trajectories\rendered')
        }
    }
}

function Target-Report {
    Invoke-Py @('-m', 'settle.report', '--results', $RES, '--out', "$RES\RESULTS.md")
}

function Target-Clean {
    foreach ($p in @($DATA, 'outputs', 'state', 'trajectories\core', 'trajectories\full',
                     'trajectories\demo', 'trajectories\rendered')) {
        if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
    Get-ChildItem $RES -Filter 'pred_*' -Directory -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Get-ChildItem $RES -Filter 'score_*.json' -ErrorAction SilentlyContinue |
        Remove-Item -Force
    Get-ChildItem -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Write-Host "cleaned" -ForegroundColor Green
}

# --- dispatch ----------------------------------------------------------------
$map = @{
    'help'         = { Target-Help }
    'estimate'     = { Target-Estimate }
    'doctor'       = { Target-Doctor }
    'models'       = { Target-Models }
    'data'         = { Target-Data }
    'baseline-b'   = { Target-BaselineB }
    'core'         = { Target-Core }
    'ceiling'      = { Target-Ceiling }
    'baseline-a'   = { Target-BaselineA }
    'agent'        = { Target-Agent }
    'ablations'    = { Target-Ablations }
    'demo-memory'  = { Target-DemoMemory }
    'trajectories' = { Target-Trajectories }
    'report'       = { Target-Report }
    'eval'         = { Target-Report }
    'clean'        = { Target-Clean }
    'offline'      = { Target-Data; Target-BaselineB; Target-Core; Target-Ceiling; Target-Report }
    'all'          = { Target-Data; Target-BaselineB; Target-Core; Target-Ceiling;
                       Target-Doctor; Target-BaselineA; Target-Agent; Target-Ablations;
                       Target-Trajectories; Target-Report }
}

foreach ($t in $Targets) {
    $key = $t.ToLower()
    if (-not $map.ContainsKey($key)) {
        Write-Host "Unknown target '$t'." -ForegroundColor Red
        Target-Help
        exit 1
    }
    Write-Host ""
    Write-Host "=== $key ===" -ForegroundColor Cyan
    try {
        & $map[$key]
    } catch {
        Write-Host ""
        Write-Host "FAILED at target '$key': $_" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "done" -ForegroundColor Green
