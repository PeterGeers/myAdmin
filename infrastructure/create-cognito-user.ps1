# Create User in AWS Cognito User Pool

param(
    [Parameter(Mandatory = $true)]
    [string]$Email,
    
    [Parameter(Mandatory = $true)]
    [string]$Name,
    
    [Parameter(Mandatory = $false)]
    [ValidateSet("Tenant_Admin", "Finance_Read", "Finance_CRUD", "Finance_Export", "STR_Read", "STR_CRUD", "STR_Export", "SysAdmin")]
    [string[]]$Groups = @(),
    
    [string]$TenantId = "",
    [string]$TenantName = "",
    
    [Parameter(Mandatory = $false)]
    [string[]]$Tenants = @()
)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          Create Cognito User                               ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Get User Pool ID from Terraform output
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Getting User Pool ID..." -ForegroundColor Yellow
try {
    $userPoolId = terraform output -raw cognito_user_pool_id
    Write-Host "✓ User Pool ID: $userPoolId" -ForegroundColor Green
}
catch {
    Write-Host "✗ Failed to get User Pool ID" -ForegroundColor Red
    Write-Host "  Make sure Cognito is deployed: .\setup-cognito.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Build user attributes
$attributes = @(
    "Name=email,Value=$Email",
    "Name=email_verified,Value=true",
    "Name=name,Value=$Name"
)

if ($TenantId) {
    $attributes += "Name=custom:tenant_id,Value=$TenantId"
}

if ($TenantName) {
    $attributes += "Name=custom:tenant_name,Value=$TenantName"
}

# Add tenants as JSON array
if ($Tenants.Count -gt 0) {
    $tenantsJson = $Tenants | ConvertTo-Json -Compress
    $attributes += "Name=custom:tenants,Value=$tenantsJson"
}

# Add role (use first group as role for backward compatibility)
if ($Groups.Count -gt 0) {
    $attributes += "Name=custom:role,Value=$($Groups[0])"
}

# Create user
Write-Host "Creating user: $Email" -ForegroundColor Yellow
try {
    aws cognito-idp admin-create-user `
        --user-pool-id $userPoolId `
        --username $Email `
        --user-attributes $attributes `
        --message-action SUPPRESS
    
    Write-Host "✓ User created" -ForegroundColor Green
}
catch {
    Write-Host "✗ Failed to create user: $_" -ForegroundColor Red
    exit 1
}

# Add to groups
if ($Groups.Count -gt 0) {
    foreach ($Group in $Groups) {
        Write-Host "Adding to group: $Group" -ForegroundColor Yellow
        try {
            aws cognito-idp admin-add-user-to-group `
                --user-pool-id $userPoolId `
                --username $Email `
                --group-name $Group
            
            Write-Host "✓ Added to group: $Group" -ForegroundColor Green
        }
        catch {
            Write-Host "✗ Failed to add to group $Group : $_" -ForegroundColor Red
        }
    }
}
else {
    Write-Host "⚠ No groups specified - user will have no role assignments" -ForegroundColor Yellow
}

# Set password
Write-Host ""
Write-Host "Set password for user:" -ForegroundColor Cyan
$password = Read-Host "Enter password (min 8 chars, uppercase, lowercase, number, symbol)" -AsSecureString
$passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
)

try {
    aws cognito-idp admin-set-user-password `
        --user-pool-id $userPoolId `
        --username $Email `
        --password $passwordPlain `
        --permanent
    
    Write-Host "✓ Password set" -ForegroundColor Green
}
catch {
    Write-Host "✗ Failed to set password: $_" -ForegroundColor Red
    Write-Host "  User will receive a temporary password via email" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          User Created Successfully                         ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Email:       $Email" -ForegroundColor Cyan
Write-Host "Name:        $Name" -ForegroundColor Cyan
if ($Groups.Count -gt 0) {
    Write-Host "Groups:      $($Groups -join ', ')" -ForegroundColor Cyan
}
if ($Tenants.Count -gt 0) {
    Write-Host "Tenants:     $($Tenants -join ', ')" -ForegroundColor Cyan
}
if ($TenantId) {
    Write-Host "Tenant ID:   $TenantId" -ForegroundColor Cyan
}
if ($TenantName) {
    Write-Host "Tenant Name: $TenantName" -ForegroundColor Cyan
}
Write-Host ""

exit 0
