# Install Terraform to PATH
# Run this script as Administrator

$terraformPath = "C:\Users\peter\Downloads\terraform_1.14.3_windows_amd64"
$terraformExe = Join-Path $terraformPath "terraform.exe"

Write-Host "Terraform Installation Helper" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# Check if terraform.exe exists
if (Test-Path $terraformExe) {
    Write-Host "✓ Found terraform.exe at: $terraformExe" -ForegroundColor Green
}
else {
    Write-Host "✗ terraform.exe not found at: $terraformExe" -ForegroundColor Red
    Write-Host "Please update the path in this script" -ForegroundColor Yellow
    exit 1
}

# Option 1: Copy to Windows directory (requires admin)
Write-Host ""
Write-Host "Option 1: Copy to C:\Windows\System32 (requires admin)" -ForegroundColor Cyan
$choice1 = Read-Host "Do you want to copy terraform.exe to System32? (yes/no)"

if ($choice1 -eq "yes") {
    try {
        Copy-Item $terraformExe "C:\Windows\System32\" -Force
        Write-Host "✓ Terraform copied to System32" -ForegroundColor Green
        Write-Host "  You can now run 'terraform' from anywhere" -ForegroundColor Gray
    }
    catch {
        Write-Host "✗ Failed to copy. Run PowerShell as Administrator" -ForegroundColor Red
    }
}

# Option 2: Add to User PATH
Write-Host ""
Write-Host "Option 2: Add to User PATH" -ForegroundColor Cyan
$choice2 = Read-Host "Do you want to add Terraform folder to PATH? (yes/no)"

if ($choice2 -eq "yes") {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    if ($currentPath -notlike "*$terraformPath*") {
        $newPath = "$currentPath;$terraformPath"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "✓ Added to PATH" -ForegroundColor Green
        Write-Host "  Restart PowerShell to use 'terraform' command" -ForegroundColor Yellow
    }
    else {
        Write-Host "✓ Already in PATH" -ForegroundColor Green
    }
}

# Option 3: Create alias for current session
Write-Host ""
Write-Host "Option 3: Create alias for current session" -ForegroundColor Cyan
Write-Host "Run this command in your PowerShell:" -ForegroundColor Gray
Write-Host "Set-Alias terraform '$terraformExe'" -ForegroundColor Yellow

Write-Host ""
Write-Host "Test Terraform:" -ForegroundColor Cyan
Write-Host "terraform version" -ForegroundColor Gray
Write-Host ""
