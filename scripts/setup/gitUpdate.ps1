param([string]$message)

Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

if (-not (Test-Path ".git")) {
    Write-Error "Not in git repository"
    exit 1
}

Write-Host "🔍 Checking for credentials..." -ForegroundColor Yellow

$files = git diff --name-only HEAD 2>$null | Where-Object { $_ -and (Test-Path $_) }
$blocked = $false

foreach ($file in $files) {
    if ($file -like "*gitUpdate*.ps1" -or $file -like "*requirements*.txt") { continue }
    
    $content = Get-Content $file -ErrorAction SilentlyContinue
    if ($content -and ($content | Select-String "sk-or-v1-[a-f0-9]{64}" -Quiet)) {
        Write-Host "❌ BLOCKED: API key in $file" -ForegroundColor Red
        $blocked = $true
    }
}

if ($blocked) { exit 1 }

if (-not $message) { $message = "Auto commit - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" }

Write-Host "✅ Safe to commit" -ForegroundColor Green
git add .
git commit -m "$message"
git push origin main
Write-Host "✅ Done" -ForegroundColor Green