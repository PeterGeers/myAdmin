#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Assign users to Cognito groups

.DESCRIPTION
    Helper script to assign users to module-based groups and manage group memberships.

.PARAMETER UserPoolId
    The Cognito User Pool ID (default: eu-west-1_Hdp40eWmu)

.PARAMETER Region
    AWS Region (default: eu-west-1)

.PARAMETER Email
    User email address

.PARAMETER Groups
    Comma-separated list of groups to assign

.PARAMETER Action
    Action to perform: add, remove, list (default: list)

.EXAMPLE
    # List user's current groups
    .\assign-user-groups.ps1 -Email "accountant@test.com"

.EXAMPLE
    # Add user to multiple groups
    .\assign-user-groups.ps1 -Email "accountant@test.com" -Groups "Finance_CRUD,Finance_Export" -Action add

.EXAMPLE
    # Remove user from a group
    .\assign-user-groups.ps1 -Email "accountant@test.com" -Groups "Accountants" -Action remove
#>

param(
    [string]$UserPoolId = "eu-west-1_Hdp40eWmu",
    [string]$Region = "eu-west-1",
    [Parameter(Mandatory = $true)]
    [string]$Email,
    [string]$Groups = "",
    [ValidateSet("add", "remove", "list")]
    [string]$Action = "list"
)

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Cognito User Group Management" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "User Pool: $UserPoolId" -ForegroundColor Gray
Write-Host "Region: $Region" -ForegroundColor Gray
Write-Host "User: $Email" -ForegroundColor Gray
Write-Host ""

# Function to list user's groups
function Get-UserGroups {
    param([string]$Email)
    
    try {
        $result = aws cognito-idp admin-list-groups-for-user `
            --user-pool-id $UserPoolId `
            --username $Email `
            --region $Region | ConvertFrom-Json
        
        return $result.Groups
    }
    catch {
        Write-Host "❌ Error listing groups: $_" -ForegroundColor Red
        return @()
    }
}

# Function to add user to group
function Add-UserToGroup {
    param([string]$Email, [string]$GroupName)
    
    try {
        aws cognito-idp admin-add-user-to-group `
            --user-pool-id $UserPoolId `
            --username $Email `
            --group-name $GroupName `
            --region $Region | Out-Null
        
        Write-Host "  ✅ Added to: $GroupName" -ForegroundColor Green
        return $true
    }
    catch {
        if ($_.Exception.Message -like "*MemberExistsException*") {
            Write-Host "  ⚠️  Already in: $GroupName" -ForegroundColor Yellow
        }
        else {
            Write-Host "  ❌ Error adding to $GroupName : $_" -ForegroundColor Red
        }
        return $false
    }
}

# Function to remove user from group
function Remove-UserFromGroup {
    param([string]$Email, [string]$GroupName)
    
    try {
        aws cognito-idp admin-remove-user-from-group `
            --user-pool-id $UserPoolId `
            --username $Email `
            --group-name $GroupName `
            --region $Region | Out-Null
        
        Write-Host "  ✅ Removed from: $GroupName" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "  ❌ Error removing from $GroupName : $_" -ForegroundColor Red
        return $false
    }
}

# List current groups
Write-Host "Current Groups for $Email :" -ForegroundColor Cyan
$currentGroups = Get-UserGroups -Email $Email

if ($currentGroups.Count -eq 0) {
    Write-Host "  (No groups assigned)" -ForegroundColor Gray
}
else {
    $currentGroups | Sort-Object Precedence | ForEach-Object {
        Write-Host "  [$($_.Precedence)] $($_.GroupName)" -ForegroundColor White
        Write-Host "      $($_.Description)" -ForegroundColor Gray
    }
}
Write-Host ""

# Perform action
if ($Action -eq "add" -and $Groups) {
    Write-Host "Adding user to groups..." -ForegroundColor Yellow
    $groupList = $Groups -split ","
    foreach ($group in $groupList) {
        $group = $group.Trim()
        Add-UserToGroup -Email $Email -GroupName $group
    }
    Write-Host ""
    
    # Show updated groups
    Write-Host "Updated Groups:" -ForegroundColor Cyan
    $updatedGroups = Get-UserGroups -Email $Email
    $updatedGroups | Sort-Object Precedence | ForEach-Object {
        Write-Host "  [$($_.Precedence)] $($_.GroupName)" -ForegroundColor White
    }
}
elseif ($Action -eq "remove" -and $Groups) {
    Write-Host "Removing user from groups..." -ForegroundColor Yellow
    $groupList = $Groups -split ","
    foreach ($group in $groupList) {
        $group = $group.Trim()
        Remove-UserFromGroup -Email $Email -GroupName $group
    }
    Write-Host ""
    
    # Show updated groups
    Write-Host "Updated Groups:" -ForegroundColor Cyan
    $updatedGroups = Get-UserGroups -Email $Email
    if ($updatedGroups.Count -eq 0) {
        Write-Host "  (No groups assigned)" -ForegroundColor Gray
    }
    else {
        $updatedGroups | Sort-Object Precedence | ForEach-Object {
            Write-Host "  [$($_.Precedence)] $($_.GroupName)" -ForegroundColor White
        }
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Available Groups:" -ForegroundColor Cyan
Write-Host ""
Write-Host "System Roles:" -ForegroundColor Yellow
Write-Host "  • Administrators - Full system access" -ForegroundColor White
Write-Host "  • SysAdmin - System admin (no user data)" -ForegroundColor White
Write-Host "  • Viewers - Read-only access" -ForegroundColor White
Write-Host ""
Write-Host "Finance Module:" -ForegroundColor Yellow
Write-Host "  • Finance_Read - Read-only financial data" -ForegroundColor White
Write-Host "  • Finance_CRUD - Full financial data access" -ForegroundColor White
Write-Host "  • Finance_Export - Export financial reports" -ForegroundColor White
Write-Host ""
Write-Host "STR Module:" -ForegroundColor Yellow
Write-Host "  • STR_Read - Read-only STR data" -ForegroundColor White
Write-Host "  • STR_CRUD - Full STR data access" -ForegroundColor White
Write-Host "  • STR_Export - Export STR reports" -ForegroundColor White
Write-Host ""
Write-Host "Legacy (for backward compatibility):" -ForegroundColor Yellow
Write-Host "  • Accountants - Maps to Finance_CRUD + Finance_Export" -ForegroundColor White
Write-Host ""
