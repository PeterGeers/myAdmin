#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Migrate users from legacy groups to module-based groups

.DESCRIPTION
    This script migrates all users from legacy groups (Administrators, Accountants, Viewers)
    to the new module-based group structure and then deletes the legacy groups.

.PARAMETER UserPoolId
    The Cognito User Pool ID (default: eu-west-1_Hdp40eWmu)

.PARAMETER Region
    AWS Region (default: eu-west-1)

.PARAMETER DryRun
    If specified, shows what would be done without making changes

.EXAMPLE
    # Dry run to see what will happen
    .\migrate-to-module-groups.ps1 -DryRun

.EXAMPLE
    # Perform actual migration
    .\migrate-to-module-groups.ps1
#>

param(
    [string]$UserPoolId = "eu-west-1_Hdp40eWmu",
    [string]$Region = "eu-west-1",
    [switch]$DryRun
)

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Migrate to Module-Based Groups" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "User Pool: $UserPoolId" -ForegroundColor Gray
Write-Host "Region: $Region" -ForegroundColor Gray
if ($DryRun) {
    Write-Host "Mode: DRY RUN (no changes will be made)" -ForegroundColor Yellow
} else {
    Write-Host "Mode: LIVE (changes will be applied)" -ForegroundColor Red
}
Write-Host ""

# Migration mapping
$migrations = @{
    "peter@pgeers.nl" = @{
        OldGroups = @("Administrators")
        NewGroups = @("Finance_CRUD", "Finance_Export", "STR_CRUD", "STR_Export", "SysAdmin")
        Reason = "Full system access → All module permissions + SysAdmin"
    }
    "accountant@test.com" = @{
        OldGroups = @("Accountants")
        NewGroups = @("Finance_CRUD", "Finance_Export")
        Reason = "Accountant → Finance CRUD + Export"
    }
    "viewer@test.com" = @{
        OldGroups = @("Viewers")
        NewGroups = @("Finance_Read")
        Reason = "Viewer → Finance Read-only"
    }
}

# Legacy groups to delete
$legacyGroups = @("Administrators", "Accountants", "Viewers")

Write-Host "Migration Plan:" -ForegroundColor Cyan
Write-Host ""

foreach ($email in $migrations.Keys) {
    $migration = $migrations[$email]
    Write-Host "User: $email" -ForegroundColor Yellow
    Write-Host "  Reason: $($migration.Reason)" -ForegroundColor Gray
    Write-Host "  Remove from: $($migration.OldGroups -join ', ')" -ForegroundColor Red
    Write-Host "  Add to: $($migration.NewGroups -join ', ')" -ForegroundColor Green
    Write-Host ""
}

Write-Host "Groups to Delete:" -ForegroundColor Cyan
foreach ($group in $legacyGroups) {
    Write-Host "  • $group" -ForegroundColor Red
}
Write-Host ""

if ($DryRun) {
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "DRY RUN COMPLETE - No changes were made" -ForegroundColor Yellow
    Write-Host "Run without -DryRun to apply changes" -ForegroundColor Yellow
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    exit 0
}

# Confirm before proceeding
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "WARNING: This will modify user group assignments!" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
$confirmation = Read-Host "Type 'YES' to proceed"

if ($confirmation -ne "YES") {
    Write-Host "Migration cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Starting migration..." -ForegroundColor Cyan
Write-Host ""

# Step 1: Migrate users to new groups
foreach ($email in $migrations.Keys) {
    $migration = $migrations[$email]
    
    Write-Host "Migrating: $email" -ForegroundColor Yellow
    
    # Add to new groups
    foreach ($group in $migration.NewGroups) {
        try {
            aws cognito-idp admin-add-user-to-group `
                --user-pool-id $UserPoolId `
                --username $email `
                --group-name $group `
                --region $Region 2>&1 | Out-Null
            
            Write-Host "  ✅ Added to: $group" -ForegroundColor Green
        } catch {
            if ($_.Exception.Message -like "*MemberExistsException*") {
                Write-Host "  ⚠️  Already in: $group" -ForegroundColor Yellow
            } else {
                Write-Host "  ❌ Error adding to $group : $_" -ForegroundColor Red
            }
        }
    }
    
    # Remove from old groups
    foreach ($group in $migration.OldGroups) {
        try {
            aws cognito-idp admin-remove-user-from-group `
                --user-pool-id $UserPoolId `
                --username $email `
                --group-name $group `
                --region $Region 2>&1 | Out-Null
            
            Write-Host "  ✅ Removed from: $group" -ForegroundColor Green
        } catch {
            Write-Host "  ⚠️  Error removing from $group : $_" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
}

# Step 2: Verify no users are in legacy groups
Write-Host "Verifying legacy groups are empty..." -ForegroundColor Cyan
$canDelete = $true

foreach ($group in $legacyGroups) {
    try {
        $groupInfo = aws cognito-idp get-group `
            --user-pool-id $UserPoolId `
            --group-name $group `
            --region $Region 2>&1 | ConvertFrom-Json
        
        # Try to list users in group (this will fail if group doesn't exist)
        $usersInGroup = aws cognito-idp list-users-in-group `
            --user-pool-id $UserPoolId `
            --group-name $group `
            --region $Region 2>&1 | ConvertFrom-Json
        
        if ($usersInGroup.Users.Count -gt 0) {
            Write-Host "  ⚠️  $group still has $($usersInGroup.Users.Count) users" -ForegroundColor Yellow
            $canDelete = $false
        } else {
            Write-Host "  ✅ $group is empty" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠️  Could not verify $group : $_" -ForegroundColor Yellow
    }
}
Write-Host ""

# Step 3: Delete legacy groups
if ($canDelete) {
    Write-Host "Deleting legacy groups..." -ForegroundColor Cyan
    
    foreach ($group in $legacyGroups) {
        try {
            aws cognito-idp delete-group `
                --user-pool-id $UserPoolId `
                --group-name $group `
                --region $Region 2>&1 | Out-Null
            
            Write-Host "  ✅ Deleted: $group" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ Error deleting $group : $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "⚠️  Skipping group deletion - some groups still have users" -ForegroundColor Yellow
    Write-Host "   Please manually verify and delete groups if needed" -ForegroundColor Gray
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Migration Complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Show final group structure
Write-Host "Current Groups:" -ForegroundColor Cyan
try {
    $allGroups = aws cognito-idp list-groups `
        --user-pool-id $UserPoolId `
        --region $Region | ConvertFrom-Json
    
    $allGroups.Groups | Sort-Object Precedence | ForEach-Object {
        Write-Host "  [$($_.Precedence)] $($_.GroupName)" -ForegroundColor White
        Write-Host "      $($_.Description)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ❌ Error listing groups: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Verify user assignments:" -ForegroundColor Cyan
foreach ($email in $migrations.Keys) {
    Write-Host "  $email" -ForegroundColor Yellow
    try {
        $userGroups = aws cognito-idp admin-list-groups-for-user `
            --user-pool-id $UserPoolId `
            --username $email `
            --region $Region | ConvertFrom-Json
        
        $userGroups.Groups | Sort-Object Precedence | ForEach-Object {
            Write-Host "    • $($_.GroupName)" -ForegroundColor White
        }
    } catch {
        Write-Host "    ❌ Error: $_" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Test login with each user to verify access" -ForegroundColor White
Write-Host "2. Update frontend code to remove references to legacy groups" -ForegroundColor White
Write-Host "3. Update backend code to remove references to legacy groups" -ForegroundColor White
Write-Host "4. Update documentation" -ForegroundColor White
Write-Host ""
