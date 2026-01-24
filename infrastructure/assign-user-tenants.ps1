#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Assign tenants to Cognito users for multi-tenant support

.DESCRIPTION
    Manages the custom:tenants attribute for users, allowing them to access one or more tenants.
    The custom:tenants attribute stores a JSON array of tenant names.

.PARAMETER UserPoolId
    The Cognito User Pool ID (default: from terraform output)

.PARAMETER Region
    AWS Region (default: eu-west-1)

.PARAMETER Email
    User email address

.PARAMETER Tenants
    Comma-separated list of tenant names (e.g., "GoodwinSolutions,PeterPrive")

.PARAMETER Action
    Action to perform: set, add, remove, list (default: list)
    - set: Replace all tenants with the provided list
    - add: Add tenants to existing list
    - remove: Remove tenants from existing list
    - list: Show current tenant assignments

.EXAMPLE
    # List user's current tenants
    .\assign-user-tenants.ps1 -Email "accountant@test.com"

.EXAMPLE
    # Set user's tenants (replaces existing)
    .\assign-user-tenants.ps1 -Email "accountant@test.com" -Tenants "GoodwinSolutions" -Action set

.EXAMPLE
    # Add additional tenant to user
    .\assign-user-tenants.ps1 -Email "accountant@test.com" -Tenants "PeterPrive" -Action add

.EXAMPLE
    # Remove tenant from user
    .\assign-user-tenants.ps1 -Email "accountant@test.com" -Tenants "InterimManagement" -Action remove

.EXAMPLE
    # Assign multiple tenants
    .\assign-user-tenants.ps1 -Email "admin@test.com" -Tenants "GoodwinSolutions,PeterPrive,InterimManagement" -Action set
#>

param(
    [string]$UserPoolId = "",
    [string]$Region = "eu-west-1",
    [Parameter(Mandatory = $true)]
    [string]$Email,
    [string]$Tenants = "",
    [ValidateSet("set", "add", "remove", "list")]
    [string]$Action = "list"
)

$ErrorActionPreference = "Stop"

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Cognito User Tenant Assignment" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

# Get User Pool ID from Terraform if not provided
if (-not $UserPoolId) {
    Write-Host "Getting User Pool ID from Terraform..." -ForegroundColor Yellow
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    Push-Location $scriptDir
    try {
        $UserPoolId = terraform output -raw cognito_user_pool_id 2>$null
        if (-not $UserPoolId) {
            throw "Failed to get User Pool ID"
        }
        Write-Host "✓ User Pool ID: $UserPoolId" -ForegroundColor Green
    }
    catch {
        Write-Host "✗ Failed to get User Pool ID from Terraform" -ForegroundColor Red
        Write-Host "  Please provide -UserPoolId parameter or run terraform apply first" -ForegroundColor Yellow
        Pop-Location
        exit 1
    }
    Pop-Location
}

Write-Host "User Pool: $UserPoolId" -ForegroundColor Gray
Write-Host "Region: $Region" -ForegroundColor Gray
Write-Host "User: $Email" -ForegroundColor Gray
Write-Host ""

# Function to get user attributes
function Get-UserAttributes {
    param([string]$Email)
    
    try {
        $result = aws cognito-idp admin-get-user `
            --user-pool-id $UserPoolId `
            --username $Email `
            --region $Region | ConvertFrom-Json
        
        return $result.UserAttributes
    }
    catch {
        Write-Host "❌ Error getting user: $_" -ForegroundColor Red
        exit 1
    }
}

# Function to parse tenants from custom:tenants attribute
function Get-CurrentTenants {
    param([array]$Attributes)
    
    $tenantsAttr = $Attributes | Where-Object { $_.Name -eq "custom:tenants" }
    
    if (-not $tenantsAttr -or -not $tenantsAttr.Value) {
        return @()
    }
    
    try {
        # Remove escaped quotes and parse JSON
        $jsonValue = $tenantsAttr.Value -replace '\\\"', '"'
        $tenantList = $jsonValue | ConvertFrom-Json
        return $tenantList
    }
    catch {
        # If not valid JSON, try comma-separated
        if ($tenantsAttr.Value -match ",") {
            return $tenantsAttr.Value -split "," | ForEach-Object { $_.Trim() }
        }
        # Single tenant
        return @($tenantsAttr.Value)
    }
}

# Function to update user tenants
function Set-UserTenants {
    param([string]$Email, [array]$TenantList)
    
    # Build JSON array manually to avoid PowerShell JSON issues
    $tenantStrings = $TenantList | ForEach-Object { "`"$_`"" }
    $tenantsJson = "[" + ($tenantStrings -join ",") + "]"
    
    try {
        aws cognito-idp admin-update-user-attributes `
            --user-pool-id $UserPoolId `
            --username $Email `
            --user-attributes "Name=custom:tenants,Value='$tenantsJson'" `
            --region $Region | Out-Null
        
        return $true
    }
    catch {
        Write-Host "❌ Error updating tenants: $_" -ForegroundColor Red
        return $false
    }
}

# Get current user attributes
$userAttributes = Get-UserAttributes -Email $Email
$currentTenants = Get-CurrentTenants -Attributes $userAttributes

# Display current tenants
Write-Host "Current Tenants for $Email :" -ForegroundColor Cyan
if ($currentTenants.Count -eq 0) {
    Write-Host "  (No tenants assigned)" -ForegroundColor Gray
}
else {
    $currentTenants | ForEach-Object {
        Write-Host "  • $_" -ForegroundColor White
    }
}
Write-Host ""

# Perform action
if ($Action -ne "list") {
    if (-not $Tenants) {
        Write-Host "❌ Error: -Tenants parameter required for action '$Action'" -ForegroundColor Red
        exit 1
    }
    
    $inputTenants = $Tenants -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    
    switch ($Action) {
        "set" {
            Write-Host "Setting tenants to: $($inputTenants -join ', ')" -ForegroundColor Yellow
            $newTenants = $inputTenants
        }
        "add" {
            Write-Host "Adding tenants: $($inputTenants -join ', ')" -ForegroundColor Yellow
            $newTenants = $currentTenants + $inputTenants | Select-Object -Unique
        }
        "remove" {
            Write-Host "Removing tenants: $($inputTenants -join ', ')" -ForegroundColor Yellow
            $newTenants = $currentTenants | Where-Object { $inputTenants -notcontains $_ }
        }
    }
    
    # Update user
    if (Set-UserTenants -Email $Email -TenantList $newTenants) {
        Write-Host "✅ Tenants updated successfully" -ForegroundColor Green
        Write-Host ""
        
        # Show updated tenants
        Write-Host "Updated Tenants:" -ForegroundColor Cyan
        if ($newTenants.Count -eq 0) {
            Write-Host "  (No tenants assigned)" -ForegroundColor Gray
        }
        else {
            $newTenants | ForEach-Object {
                Write-Host "  • $_" -ForegroundColor White
            }
        }
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Available Tenants:" -ForegroundColor Cyan
Write-Host "  • GoodwinSolutions" -ForegroundColor White
Write-Host "  • PeterPrive" -ForegroundColor White
Write-Host "  • InterimManagement" -ForegroundColor White
Write-Host ""
Write-Host "Usage Examples:" -ForegroundColor Cyan
Write-Host "  # Assign single tenant" -ForegroundColor Gray
Write-Host "  .\assign-user-tenants.ps1 -Email user@test.com -Tenants 'GoodwinSolutions' -Action set" -ForegroundColor Gray
Write-Host ""
Write-Host "  # Assign multiple tenants" -ForegroundColor Gray
Write-Host "  .\assign-user-tenants.ps1 -Email user@test.com -Tenants 'GoodwinSolutions,PeterPrive' -Action set" -ForegroundColor Gray
Write-Host ""
Write-Host "  # Add tenant to existing" -ForegroundColor Gray
Write-Host "  .\assign-user-tenants.ps1 -Email user@test.com -Tenants 'InterimManagement' -Action add" -ForegroundColor Gray
Write-Host ""

