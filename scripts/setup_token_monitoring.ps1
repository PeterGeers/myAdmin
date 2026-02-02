# Setup Google Drive Token Monitoring
# This script creates a Windows scheduled task to monitor Google Drive token health

$ErrorActionPreference = "Stop"

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "🔧 Setting up Google Drive Token Monitoring" -ForegroundColor Cyan
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# Get the current directory (project root)
$ProjectRoot = (Get-Location).Path
$ScriptPath = Join-Path $ProjectRoot "backend\check_google_token_health.py"
$PythonPath = "python"  # Assumes python is in PATH

# Check if script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Host "❌ Error: Script not found at $ScriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "📍 Project root: $ProjectRoot" -ForegroundColor Yellow
Write-Host "📄 Health check script: $ScriptPath" -ForegroundColor Yellow
Write-Host ""

# Task configuration
$TaskName = "GoogleDriveTokenHealthCheck"
$TaskDescription = "Monitors Google Drive OAuth token health and alerts if tokens are expired or expiring soon"
$TaskAction = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`"" -WorkingDirectory $ProjectRoot

# Run daily at 9 AM
$TaskTrigger = New-ScheduledTaskTrigger -Daily -At 9am

# Run whether user is logged on or not
$TaskPrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest

# Task settings
$TaskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Write-Host "📋 Task Configuration:" -ForegroundColor Cyan
Write-Host "   Name: $TaskName" -ForegroundColor White
Write-Host "   Schedule: Daily at 9:00 AM" -ForegroundColor White
Write-Host "   Action: $PythonPath `"$ScriptPath`"" -ForegroundColor White
Write-Host ""

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "⚠️  Task '$TaskName' already exists" -ForegroundColor Yellow
    $Response = Read-Host "Do you want to update it? (Y/N)"
    
    if ($Response -ne "Y" -and $Response -ne "y") {
        Write-Host "❌ Cancelled" -ForegroundColor Red
        exit 0
    }
    
    Write-Host "🔄 Updating existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the scheduled task
try {
    Register-ScheduledTask -TaskName $TaskName `
        -Description $TaskDescription `
        -Action $TaskAction `
        -Trigger $TaskTrigger `
        -Principal $TaskPrincipal `
        -Settings $TaskSettings | Out-Null
    
    Write-Host "✅ Scheduled task created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Task Details:" -ForegroundColor Cyan
    Write-Host "   - Runs daily at 9:00 AM" -ForegroundColor White
    Write-Host "   - Checks token expiry for all tenants" -ForegroundColor White
    Write-Host "   - Warns if tokens expire within 7 days" -ForegroundColor White
    Write-Host ""
    Write-Host "🔍 To view task status:" -ForegroundColor Cyan
    Write-Host "   Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "▶️  To run task manually:" -ForegroundColor Cyan
    Write-Host "   Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "🗑️  To remove task:" -ForegroundColor Cyan
    Write-Host "   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Yellow
    Write-Host ""
    
    # Ask if user wants to run it now
    $RunNow = Read-Host "Do you want to run the health check now? (Y/N)"
    if ($RunNow -eq "Y" -or $RunNow -eq "y") {
        Write-Host ""
        Write-Host "🏃 Running health check..." -ForegroundColor Cyan
        Write-Host ""
        & $PythonPath $ScriptPath
    }
    
} catch {
    Write-Host "❌ Error creating scheduled task: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
