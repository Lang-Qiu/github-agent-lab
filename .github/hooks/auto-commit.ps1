$ErrorActionPreference = "Stop"

# 只在 git 仓库中执行
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { exit 0 }

# 没有改动就跳过
$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) { exit 0 }

# 禁止直接在 main/master 自动提交和自动推送
$branch = (git branch --show-current).Trim()
if ($branch -in @("main", "master")) { exit 0 }

# 必须存在远端 upstream 或 origin
$upstream = ""
git rev-parse --abbrev-ref --symbolic-full-name "@{u}" *> $null
if ($LASTEXITCODE -eq 0) {
    $upstream = (git rev-parse --abbrev-ref --symbolic-full-name "@{u}").Trim()
}

$hasOrigin = $false
git remote get-url origin *> $null
if ($LASTEXITCODE -eq 0) { $hasOrigin = $true }

if ([string]::IsNullOrWhiteSpace($upstream) -and -not $hasOrigin) { exit 0 }

git add -A

# 没有暂存差异就跳过
$cached = git diff --cached --name-only
if ([string]::IsNullOrWhiteSpace($cached)) { exit 0 }

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "chore: auto-commit after Copilot task ($timestamp)"

# 优先推到上游分支；若还没有上游但有 origin，则首次用 -u 建立跟踪
if (-not [string]::IsNullOrWhiteSpace($upstream)) {
    git push
} elseif ($hasOrigin) {
    git push -u origin $branch
}