# Complete CI/CD Pipeline
# This script runs the full pipeline: build -> deploy -> verify

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("staging", "production")]
    [string]$Environment = "staging",
    
    [switch]$SkipTests = $false,
    [switch]$SkipBackup = $false,
    [switch]$SkipGit = $false,
    [switch]$Force = $false,
    
    [Parameter(Mandatory = $false)]
    [string]$CommitMessage = "",
    
    [Parameter(Mandatory = $false)]
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"

# Get the root directory
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $RootDir "scripts\cicd\logs"
$PipelineLog = Join-Path $LogDir "pipeline-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

# Create logs directory
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Ensure we're in the root directory
Push-Location $RootDir

function Write-Log {
    param($Message, $Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "SUCCESS" { "Green" }
        "PIPELINE" { "Cyan" }
        default { "White" }
    }
    
    Write-Host $logMessage -ForegroundColor $color
    Add-Content -Path $PipelineLog -Value $logMessage
}

function Exit-WithError {
    param($Message)
    Write-Log $Message "ERROR"
    Write-Log "Pipeline failed. Check log: $PipelineLog" "ERROR"
    exit 1
}

Write-Log "╔════════════════════════════════════════════════════════════╗" "PIPELINE"
Write-Log "║          CI/CD Pipeline - myAdmin Application              ║" "PIPELINE"
Write-Log "║          Environment: $($Environment.PadRight(37))║" "PIPELINE"
Write-Log "╚════════════════════════════════════════════════════════════╝" "PIPELINE"

$startTime = Get-Date

# Stage -1: Environment Validation (NEW)
Write-Log "" "INFO"
Write-Log "═══ STAGE -1: ENVIRONMENT VALIDATION ═══" "PIPELINE"
Write-Log "Validating environment configuration..." "INFO"

& "scripts/cicd/validate-environment.ps1" -Environment $Environment

if ($LASTEXITCODE -ne 0) {
    Exit-WithError "Environment validation failed. Fix the errors and try again."
}

Write-Log "Environment validation passed" "SUCCESS"

# Stage 0: Git Operations
if (-not $SkipGit) {
    Write-Log "" "INFO"
    Write-Log "═══ STAGE 0: GIT OPERATIONS ═══" "PIPELINE"
    
    # Check if git is available
    try {
        git --version | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Git is not available, skipping git operations" "WARN"
        }
        else {
            Write-Log "Checking git status..." "INFO"
            
            # Check if there are changes
            $gitStatus = git status --porcelain
            
            if ($gitStatus) {
                Write-Log "Uncommitted changes detected" "INFO"
                
                # ═══ GITGUARDIAN SECURITY SCAN ═══
                Write-Log "" "INFO"
                Write-Log "Running GitGuardian security scan..." "INFO"
                
                # Use shared GitGuardian scanning module
                . "$PSScriptRoot/../security/Invoke-GitGuardianScan.ps1"
                $scanResult = Invoke-GitGuardianScan -AllowSkip $false -UseWriteLog $true
                
                if ($scanResult -ne 0) {
                    if (-not $Force) {
                        $override = Read-Host "Override security check and continue anyway? (type 'OVERRIDE' to continue)"
                        if ($override -ne "OVERRIDE") {
                            Exit-WithError "Pipeline stopped due to security scan failure"
                        }
                        Write-Log "⚠ Security check overridden by user" "WARN"
                    }
                    else {
                        Write-Log "⚠ Force mode: Continuing despite security scan failure" "WARN"
                    }
                }
                
                Write-Log "" "INFO"
                # ═══ END GITGUARDIAN SCAN ═══
                
                # Show what will be committed
                Write-Log "Changes to be committed:" "INFO"
                git status --short | ForEach-Object { Write-Log "  $_" "INFO" }
                
                # Determine commit message
                if (-not $CommitMessage) {
                    if ($Environment -eq "production") {
                        $CommitMessage = "Production deployment $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
                    }
                    else {
                        $CommitMessage = "Deployment $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
                    }
                }
                
                # Confirm commit
                if (-not $Force) {
                    Write-Host ""
                    Write-Host "Commit message: $CommitMessage" -ForegroundColor Yellow
                    $confirm = Read-Host "Commit these changes? (yes/no)"
                    
                    if ($confirm -ne "yes") {
                        Write-Log "Git commit cancelled by user" "WARN"
                        Write-Log "Continuing without committing..." "INFO"
                    }
                    else {
                        # Add all changes (excluding submodules)
                        Write-Log "Adding all changes to git..." "INFO"
                        git add --all
                        
                        # Check if there are actually changes to commit
                        $stagedChanges = git diff --cached --name-only
                        if ($stagedChanges) {
                            # Commit
                            Write-Log "Committing changes..." "INFO"
                            git commit -m $CommitMessage
                        }
                        else {
                            Write-Log "No changes to commit (only submodule changes detected)" "WARN"
                            Write-Log "Continuing without committing..." "INFO"
                            $LASTEXITCODE = 0
                        }
                        
                        if ($LASTEXITCODE -eq 0) {
                            Write-Log "✓ Changes committed successfully" "SUCCESS"
                            
                            # Create tag if specified
                            if ($Tag) {
                                Write-Log "Creating tag: $Tag" "INFO"
                                git tag -a $Tag -m "Release $Tag - $CommitMessage"
                                
                                if ($LASTEXITCODE -eq 0) {
                                    Write-Log "✓ Tag created: $Tag" "SUCCESS"
                                }
                                else {
                                    Write-Log "Failed to create tag" "WARN"
                                }
                            }
                            
                            # Ask about pushing
                            if (-not $Force) {
                                Write-Host ""
                                $pushConfirm = Read-Host "Push to remote? (yes/no)"
                                
                                if ($pushConfirm -eq "yes") {
                                    Write-Log "Pushing to remote..." "INFO"
                                    git push
                                    
                                    if ($LASTEXITCODE -eq 0) {
                                        Write-Log "✓ Pushed to remote" "SUCCESS"
                                        
                                        # Push tag if created
                                        if ($Tag) {
                                            git push origin $Tag
                                            if ($LASTEXITCODE -eq 0) {
                                                Write-Log "✓ Tag pushed to remote" "SUCCESS"
                                            }
                                        }
                                    }
                                    else {
                                        Write-Log "Failed to push to remote" "WARN"
                                    }
                                }
                            }
                        }
                        else {
                            Write-Log "Failed to commit changes" "ERROR"
                            Exit-WithError "Git commit failed"
                        }
                    }
                }
                else {
                    # Force mode - commit without asking
                    Write-Log "Force mode: Committing without confirmation" "INFO"
                    git add --all
                    
                    # Check if there are changes to commit
                    $stagedChanges = git diff --cached --name-only
                    if ($stagedChanges) {
                        git commit -m $CommitMessage
                    }
                    else {
                        Write-Log "No changes to commit (only submodule changes detected)" "WARN"
                        $LASTEXITCODE = 0
                    }
                    
                    if ($LASTEXITCODE -eq 0) {
                        Write-Log "✓ Changes committed" "SUCCESS"
                        
                        if ($Tag) {
                            git tag -a $Tag -m "Release $Tag - $CommitMessage"
                            Write-Log "✓ Tag created: $Tag" "SUCCESS"
                        }
                    }
                }
            }
            else {
                Write-Log "✓ No uncommitted changes" "SUCCESS"
                
                # Still create tag if specified
                if ($Tag) {
                    Write-Log "Creating tag: $Tag" "INFO"
                    git tag -a $Tag -m "Release $Tag"
                    
                    if ($LASTEXITCODE -eq 0) {
                        Write-Log "✓ Tag created: $Tag" "SUCCESS"
                    }
                }
            }
        }
    }
    catch {
        Write-Log "Git operations failed: $_" "WARN"
        Write-Log "Continuing without git operations..." "INFO"
    }
    
    Write-Log "Git operations completed" "SUCCESS"
}
else {
    Write-Log "Git operations skipped" "INFO"
}

# Stage 1: Build
Write-Log "" "INFO"
Write-Log "═══ STAGE 1: BUILD ═══" "PIPELINE"
Write-Log "Running build script..." "INFO"

# Capture build script output and log it to pipeline log
$buildScriptPath = "scripts/cicd/build.ps1"
if ($SkipTests) {
    Write-Log "Build parameters: -SkipTests" "INFO"
    & $buildScriptPath -SkipTests 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Add-Content -Path $PipelineLog -Value $line
        Write-Host $line
    }
}
else {
    & $buildScriptPath 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Add-Content -Path $PipelineLog -Value $line
        Write-Host $line
    }
}

if ($LASTEXITCODE -ne 0) {
    Exit-WithError "Build stage failed"
}

Write-Log "Build stage completed successfully" "SUCCESS"

# Stage 2: Deploy
Write-Log "" "INFO"
Write-Log "═══ STAGE 2: DEPLOY ═══" "PIPELINE"
Write-Log "Running deployment script..." "INFO"

$deployParams = @{
    Environment = $Environment
}
if ($SkipBackup) { $deployParams.SkipBackup = $true }
if ($Force) { $deployParams.Force = $true }

Write-Log "Deployment parameters: Environment=$Environment, SkipBackup=$SkipBackup, Force=$Force" "INFO"

# Capture deployment script output and log it to pipeline log
& "scripts/cicd/deploy.ps1" @deployParams 2>&1 | ForEach-Object {
    $line = $_.ToString()
    Add-Content -Path $PipelineLog -Value $line
    Write-Host $line
}

if ($LASTEXITCODE -ne 0) {
    Exit-WithError "Deployment stage failed"
}

Write-Log "Deployment stage completed successfully" "SUCCESS"

# Stage 3: Post-Deployment Verification
Write-Log "" "INFO"
Write-Log "═══ STAGE 3: POST-DEPLOYMENT VERIFICATION ═══" "PIPELINE"

Write-Log "Waiting for services to stabilize..." "INFO"
Start-Sleep -Seconds 5

# Verify all services are running
Write-Log "Checking service status..." "INFO"
$services = docker-compose ps --format json | ConvertFrom-Json

$allHealthy = $true
foreach ($service in $services) {
    if ($service.State -ne "running") {
        Write-Log "Service $($service.Service) is not running (State: $($service.State))" "ERROR"
        $allHealthy = $false
    }
    else {
        Write-Log "✓ Service $($service.Service) is running" "SUCCESS"
    }
}

if (-not $allHealthy) {
    Exit-WithError "Some services are not running properly"
}

# Final verification
Write-Log "Running final verification..." "INFO"

try {
    $healthCheck = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -TimeoutSec 10 -UseBasicParsing
    if ($healthCheck.StatusCode -eq 200) {
        Write-Log "✓ Application health check passed" "SUCCESS"
    }
}
catch {
    Exit-WithError "Final health check failed"
}

# Pipeline Summary
$endTime = Get-Date
$duration = $endTime - $startTime

Write-Log "" "INFO"
Write-Log "╔════════════════════════════════════════════════════════════╗" "PIPELINE"
Write-Log "║              PIPELINE COMPLETED SUCCESSFULLY               ║" "PIPELINE"
Write-Log "╚════════════════════════════════════════════════════════════╝" "PIPELINE"
Write-Log "" "INFO"
Write-Log "Environment: $Environment" "INFO"
Write-Log "Duration: $($duration.ToString('mm\:ss'))" "INFO"
Write-Log "Pipeline log: $PipelineLog" "INFO"
Write-Log "" "INFO"
Write-Log "Application URLs:" "INFO"
Write-Log "  Frontend: http://localhost:5000" "SUCCESS"
Write-Log "  Backend API: http://localhost:5000/api" "SUCCESS"
Write-Log "  Health Check: http://localhost:5000/api/health" "SUCCESS"

# Return to original directory
Pop-Location

exit 0
