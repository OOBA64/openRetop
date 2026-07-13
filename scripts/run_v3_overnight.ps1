param(
    [int]$StartTask = 75,
    [int]$EndTask = 82,
    [string]$Model = "gpt-5.6-sol",
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TaskDirectory = Join-Path $RepoRoot "docs\v3\tasks"
$ExpectedBranch = "v3-refactor"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogRoot = Join-Path $env:USERPROFILE "openRetop-v3-logs\$Timestamp"

$TaskTitles = @{
    75 = "V3 architecture baseline and application core"
    76 = "Extract remaining workflow controllers"
    77 = "Viewport scene camera and framing rework"
    78 = "Persistence settings import export and bootstrap boundaries"
    79 = "Reusable standalone workbench UI framework"
    80 = "Implement openRetop UI V3"
    81 = "Remove legacy shell and compatibility scaffolding"
    82 = "Full-system verification and V3 release candidate"
}

function Fail-Task {
    param([int]$TaskNumber, [string]$Reason)
    $Dir = Join-Path $LogRoot "task-$TaskNumber"
    New-Item -ItemType Directory -Force $Dir | Out-Null
    $Reason | Out-File -Encoding utf8 (Join-Path $Dir "failure.txt")
    git -C $RepoRoot status --short | Out-File -Encoding utf8 (Join-Path $Dir "git-status.txt")
    git -C $RepoRoot diff --binary | Out-File -Encoding utf8 (Join-Path $Dir "uncommitted.patch")
    Write-Host ""
    Write-Host "Task $TaskNumber failed. The runner stopped." -ForegroundColor Red
    Write-Host "No commit was created for the failed task."
    Write-Host "Previous passing commits are preserved."
    Write-Host "Logs: $Dir"
}

New-Item -ItemType Directory -Force $LogRoot | Out-Null

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "Codex is not installed or not on PATH. Open a new PowerShell and run: codex --version"
}

codex --version
if ($LASTEXITCODE -ne 0) { throw "Codex CLI check failed." }

$Branch = (git -C $RepoRoot branch --show-current).Trim()
if ($Branch -ne $ExpectedBranch) {
    throw "Expected branch '$ExpectedBranch'; current branch is '$Branch'."
}

$Dirty = git -C $RepoRoot status --porcelain
if (-not [string]::IsNullOrWhiteSpace(($Dirty -join "`n"))) {
    throw "Repository must be clean before starting. Commit current changes first."
}

if ($StartTask -lt 75 -or $EndTask -gt 82 -or $StartTask -gt $EndTask) {
    throw "Valid task range is 75 through 82."
}

for ($Task = $StartTask; $Task -le $EndTask; $Task++) {
    $TaskFile = Join-Path $TaskDirectory "task-$Task.md"
    if (-not (Test-Path $TaskFile)) { throw "Missing task file: $TaskFile" }

    $Dir = Join-Path $LogRoot "task-$Task"
    New-Item -ItemType Directory -Force $Dir | Out-Null
    $Stdout = Join-Path $Dir "codex-stdout.log"
    $Stderr = Join-Path $Dir "codex-stderr.log"
    $LastMessage = Join-Path $Dir "last-message.md"
    $Tests = Join-Path $Dir "tests.log"
    $StartSha = (git -C $RepoRoot rev-parse HEAD).Trim()

    $Prompt = Get-Content $TaskFile -Raw
    $Prompt += @"

# Overnight execution contract

- You are running unattended.
- Complete Task $Task only.
- Read all applicable AGENTS.md instructions before editing.
- Inspect the repository state produced by prior tasks.
- Do not begin Task $($Task + 1).
- Do not commit, push, merge, rebase, reset, tag, or switch branches.
- Do not ask routine questions. Make conservative architecture-preserving decisions.
- Stop and clearly report a blocker rather than bypassing a failed compatibility or test requirement.
- Leave the worktree reviewable. The external runner will test and commit.
"@

    $Prompt | Out-File -Encoding utf8 (Join-Path $Dir "prompt.md")

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "Task ${Task}: $($TaskTitles[$Task])"
    Write-Host "Base: $StartSha"
    Write-Host "Logs: $Dir"
    Write-Host "============================================================"

    try {
        Push-Location $RepoRoot
        try {
            $CodexArgs = @(
                "exec",
                "--model", $Model,
                "--sandbox", "workspace-write",
                "--cd", $RepoRoot,
                "--output-last-message", $LastMessage,
                "-"
            )

            $PreviousErrorActionPreference = $ErrorActionPreference

try {
    # Codex writes normal startup information to stderr.
    # Do not treat that output as a terminating PowerShell error.
    $ErrorActionPreference = "Continue"

    $Prompt |
        & codex @CodexArgs `
            1>> $Stdout `
            2>> $Stderr

    $Code = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}
        }
        finally { Pop-Location }

        if ($Code -ne 0) { throw "Codex exited with code $Code." }

        Push-Location $RepoRoot
        try {
            $env:PYTHONPATH = Join-Path $RepoRoot "src"

            "=== compileall ===" | Out-File -Encoding utf8 $Tests
            python -m compileall -q src *>> $Tests
            if ($LASTEXITCODE -ne 0) { throw "Compile check failed." }

            "`r`n=== unittest ===" | Out-File -Encoding utf8 -Append $Tests
            python -m unittest discover -s tests -p "test_*.py" *>> $Tests
            if ($LASTEXITCODE -ne 0) { throw "Full test suite failed." }

            git diff --check *>> $Tests
            if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }

            $Status = git status --porcelain
            if ([string]::IsNullOrWhiteSpace(($Status -join "`n"))) {
                throw "Task produced no repository changes."
            }

            git add -A
            if ($LASTEXITCODE -ne 0) { throw "git add failed." }

            git diff --cached --check *>> $Tests
            if ($LASTEXITCODE -ne 0) { throw "Staged diff validation failed." }

            git commit -m "Task ${Task}: $($TaskTitles[$Task])" *>> $Tests
            if ($LASTEXITCODE -ne 0) { throw "Commit failed." }

            $Sha = (git rev-parse HEAD).Trim()
            $Tag = "v3-task-$Task"
            git tag $Tag
            if ($LASTEXITCODE -ne 0) { throw "Tag creation failed." }

            if (-not $NoPush) {
                git push *>> $Tests
                if ($LASTEXITCODE -ne 0) { throw "Branch push failed." }
                git push origin $Tag *>> $Tests
                if ($LASTEXITCODE -ne 0) { throw "Tag push failed." }
            }

            $After = git status --porcelain
            if (-not [string]::IsNullOrWhiteSpace(($After -join "`n"))) {
                throw "Worktree is not clean after commit."
            }

            "Task $Task completed at $Sha" | Out-File -Encoding utf8 (Join-Path $Dir "success.txt")
            Write-Host "Task $Task committed: $Sha" -ForegroundColor Green
        }
        finally { Pop-Location }
    }
    catch {
        Fail-Task -TaskNumber $Task -Reason $_.Exception.Message
        exit 1
    }
}

Write-Host ""
Write-Host "Tasks $StartTask through $EndTask completed." -ForegroundColor Green
Write-Host "Final commit: $(git -C $RepoRoot rev-parse HEAD)"
Write-Host "Logs: $LogRoot"




