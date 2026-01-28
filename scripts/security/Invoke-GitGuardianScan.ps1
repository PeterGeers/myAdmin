# Shared GitGuardian Scanning Module
# This module provides a reusable function for GitGuardian secret scanning
# Used by: pipeline.ps1, git-upload.ps1, gitUpdate.ps1

<#
.SYNOPSIS
    Runs GitGuardian secret scan on staged changes

.DESCRIPTION
    Checks if GitGuardian CLI (ggshield) is installed and authenticated,
    then runs a secret scan on staged git changes. Returns exit code 0 if
    scan passes or is skipped, exit code 1 if secrets are detected.

.PARAMETER AllowSkip
    If true, continues without scanning if GitGuardian is not available.
    If false, treats missing GitGuardian as an error.

.PARAMETER UseWriteLog
    If true, uses Write-Log function for output (for pipeline.ps1).
    If false, uses Write-Host for output (for standalone scripts).

.EXAMPLE
    # In pipeline with Write-Log
    . scripts/security/Invoke-GitGuardianScan.ps1
    Invoke-GitGuardianScan -UseWriteLog $true -AllowSkip $false

.EXAMPLE
    # In standalone script with Write-Host
    . scripts/security/Invoke-GitGuardianScan.ps1
    Invoke-GitGuardianScan -AllowSkip $true

.OUTPUTS
    Returns 0 if scan passes or is skipped
    Returns 1 if secrets are detected
#>

function Invoke-GitGuardianScan {
    param(
        [bool]$AllowSkip = $true,
        [bool]$UseWriteLog = $false
    )

    # Helper function for output
    function Write-Output-Message {
        param($Message, $Level = "INFO")
        
        if ($UseWriteLog) {
            # Use Write-Log if available (pipeline.ps1)
            if (Get-Command Write-Log -ErrorAction SilentlyContinue) {
                Write-Log $Message $Level
            }
            else {
                Write-Host $Message
            }
        }
        else {
            # Use Write-Host with colors (standalone scripts)
            $color = switch ($Level) {
                "ERROR" { "Red" }
                "WARN" { "Yellow" }
                "SUCCESS" { "Green" }
                "INFO" { "Cyan" }
                default { "White" }
            }
            Write-Host $Message -ForegroundColor $color
        }
    }

    Write-Output-Message "🔍 Scanning for secrets with GitGuardian..." "INFO"

    # Check if ggshield is installed
    try {
        ggshield --version | Out-Null
        $ggInstalled = $true
    }
    catch {
        $ggInstalled = $false
    }

    if (-not $ggInstalled) {
        Write-Output-Message "⚠️  GitGuardian CLI (ggshield) not installed" "WARN"
        Write-Output-Message "   Install with: pip install ggshield" "WARN"
        Write-Output-Message "   Or run: scripts/security/install-gitguardian.ps1" "WARN"
        
        if ($AllowSkip) {
            Write-Output-Message "   Continuing without secret scan..." "WARN"
            return 0
        }
        else {
            Write-Output-Message "   GitGuardian is required for this operation" "ERROR"
            return 1
        }
    }

    # Check if ggshield is authenticated
    try {
        $configCheck = ggshield config list 2>&1 | Select-String "token:"
        $isAuthenticated = $null -ne $configCheck
    }
    catch {
        $isAuthenticated = $false
    }

    if (-not $isAuthenticated) {
        Write-Output-Message "⚠️  GitGuardian not authenticated" "WARN"
        Write-Output-Message "   Run: ggshield auth login" "WARN"
        Write-Output-Message "   Or run: scripts/security/install-gitguardian.ps1" "WARN"
        
        if ($AllowSkip) {
            Write-Output-Message "   Continuing without secret scan..." "WARN"
            return 0
        }
        else {
            Write-Output-Message "   GitGuardian authentication is required" "ERROR"
            return 1
        }
    }

    # Run ggshield scan on staged files
    Write-Output-Message "Scanning staged changes for secrets..." "INFO"
    ggshield secret scan pre-commit

    if ($LASTEXITCODE -ne 0) {
        Write-Output-Message "" "ERROR"
        Write-Output-Message "❌ GitGuardian detected secrets in your code!" "ERROR"
        Write-Output-Message "" "ERROR"
        Write-Output-Message "Actions required:" "WARN"
        Write-Output-Message "1. Review the secrets detected above" "INFO"
        Write-Output-Message "2. Remove or replace them with environment variables" "INFO"
        Write-Output-Message "3. Run this script again" "INFO"
        Write-Output-Message "" "ERROR"
        Write-Output-Message "Common secrets to check:" "WARN"
        Write-Output-Message "  • API keys (OpenRouter, AWS, Google)" "INFO"
        Write-Output-Message "  • Database passwords" "INFO"
        Write-Output-Message "  • JWT secrets" "INFO"
        Write-Output-Message "  • Cognito credentials" "INFO"
        Write-Output-Message "" "ERROR"
        
        return 1
    }

    Write-Output-Message "✅ No secrets detected - safe to commit" "SUCCESS"
    return 0
}

# Export the function
Export-ModuleMember -Function Invoke-GitGuardianScan
