#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create module-based Cognito groups for RBAC

.DESCRIPTION
    Creates Finance and STR module groups with Read, CRUD, and Export permissions.
    Also creates SysAdmin group for system administration.

.PARAMETER UserPoolId
    The Cognito User Pool ID (default: eu-west-1_Hdp40eWmu)

.PARAMETER Region
    AWS Region (default: eu-west-1)

.EXAMPLE
    .\create-module-groups.ps1
    .\create-module-groups.ps1 -UserPoolId "eu-west-1_XXXXXXX" -Region "eu-west-1"
#>

param(
    [string]$UserPoolId = "eu-west-1_Hdp40eWmu",
    [string]$Region = "eu-west-1"
)

Write-Host "Creating Module-Based Cognito Groups..." -ForegroundColor Cyan
Write-Host "User Pool ID: $UserPoolId" -ForegroundColor Gray
Write-Host "Region: $Region" -ForegroundColor Gray
Write-Host ""

# Define groups to create
$groups = @(
    @{
        Name        = "Finance_Read"
        Description = "Read-only access to financial data (invoices, transactions, reports)"
        Precedence  = 10
    },
    @{
        Name        = "Finance_CRUD"
        Description = "Full access to financial data - create, read, update, delete"
        Precedence  = 9
    },
    @{
        Name        = "Finance_Export"
        Description = "Permission to export financial data and reports"
        Precedence  = 11
    },
    @{
        Name        = "STR_Read"
        Description = "Read-only access to short-term rental data (bookings, pricing, reports)"
        Precedence  = 20
    },
    @{
        Name        = "STR_CRUD"
        Description = "Full access to STR data - create, read, update, delete bookings and pricing"
        Precedence  = 19
    },
    @{
        Name        = "STR_Export"
        Description = "Permission to export STR data and reports"
        Precedence  = 21
    },
    @{
        Name        = "SysAdmin"
        Description = "System administration - logs, config, templates (no user data access)"
        Precedence  = 5
    }
)

$successCount = 0
$skipCount = 0
$errorCount = 0

foreach ($group in $groups) {
    Write-Host "Creating group: $($group.Name)..." -ForegroundColor Yellow
    
    try {
        # Check if group already exists
        $existingGroup = aws cognito-idp get-group `
            --user-pool-id $UserPoolId `
            --group-name $group.Name `
            --region $Region `
            2>$null | ConvertFrom-Json
        
        if ($existingGroup) {
            Write-Host "  ⚠️  Group '$($group.Name)' already exists - skipping" -ForegroundColor DarkYellow
            $skipCount++
            continue
        }
    }
    catch {
        # Group doesn't exist, continue with creation
    }
    
    try {
        # Create the group
        $result = aws cognito-idp create-group `
            --user-pool-id $UserPoolId `
            --group-name $group.Name `
            --description $group.Description `
            --precedence $group.Precedence `
            --region $Region | ConvertFrom-Json
        
        Write-Host "  ✅ Created: $($group.Name)" -ForegroundColor Green
        Write-Host "     Description: $($group.Description)" -ForegroundColor Gray
        Write-Host "     Precedence: $($group.Precedence)" -ForegroundColor Gray
        $successCount++
    }
    catch {
        Write-Host "  ❌ Error creating group: $_" -ForegroundColor Red
        $errorCount++
    }
    
    Write-Host ""
}

# Summary
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  ✅ Created: $successCount groups" -ForegroundColor Green
Write-Host "  ⚠️  Skipped: $skipCount groups (already exist)" -ForegroundColor Yellow
Write-Host "  ❌ Errors: $errorCount groups" -ForegroundColor Red
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# List all groups
Write-Host "Current Cognito Groups:" -ForegroundColor Cyan
try {
    $allGroups = aws cognito-idp list-groups `
        --user-pool-id $UserPoolId `
        --region $Region | ConvertFrom-Json
    
    $allGroups.Groups | Sort-Object Precedence | ForEach-Object {
        Write-Host "  [$($_.Precedence)] $($_.GroupName)" -ForegroundColor White
        Write-Host "      $($_.Description)" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  ❌ Error listing groups: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Assign users to appropriate groups using:" -ForegroundColor White
Write-Host "   aws cognito-idp admin-add-user-to-group --user-pool-id $UserPoolId --username <email> --group-name <group-name> --region $Region" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Example: Assign accountant to Finance_CRUD and Finance_Export:" -ForegroundColor White
Write-Host "   aws cognito-idp admin-add-user-to-group --user-pool-id $UserPoolId --username accountant@test.com --group-name Finance_CRUD --region $Region" -ForegroundColor Gray
Write-Host "   aws cognito-idp admin-add-user-to-group --user-pool-id $UserPoolId --username accountant@test.com --group-name Finance_Export --region $Region" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Remove user from old group if needed:" -ForegroundColor White
Write-Host "   aws cognito-idp admin-remove-user-from-group --user-pool-id $UserPoolId --username accountant@test.com --group-name Accountants --region $Region" -ForegroundColor Gray
Write-Host ""
