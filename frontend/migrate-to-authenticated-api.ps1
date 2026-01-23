# PowerShell script to migrate fetch calls to authenticated API calls
# This script updates all report components to use the new authenticated API service

$reportFiles = @(
    "src/components/reports/ToeristenbelastingReport.tsx",
    "src/components/reports/ReferenceAnalysisReport.tsx",
    "src/components/reports/MutatiesReport.tsx",
    "src/components/reports/BtwReport.tsx",
    "src/components/reports/BnbViolinsReport.tsx",
    "src/components/reports/BnbReturningGuestsReport.tsx",
    "src/components/reports/BnbFutureReport.tsx",
    "src/components/reports/BnbActualsReport.tsx",
    "src/components/reports/ActualsReport.tsx",
    "src/components/reports/AangifteIbReport.tsx"
)

foreach ($file in $reportFiles) {
    Write-Host "Processing $file..." -ForegroundColor Cyan
    
    $content = Get-Content $file -Raw
    $modified = $false
    
    # Check if already has the import
    if ($content -notmatch "import.*authenticatedGet.*from.*services/apiService") {
        # Add import after the buildApiUrl import
        $content = $content -replace "(import.*buildApiUrl.*from.*config.*)", "`$1`nimport { authenticatedGet, authenticatedPost } from '../../services/apiService';"
        $modified = $true
        Write-Host "  Added import statement" -ForegroundColor Green
    }
    
    # Replace GET fetch calls
    $getPattern = 'await fetch\(buildApiUrl\(([^)]+)\)\)'
    if ($content -match $getPattern) {
        $content = $content -replace $getPattern, 'await authenticatedGet(buildApiUrl($1))'
        $modified = $true
        Write-Host "  Replaced GET fetch calls" -ForegroundColor Green
    }
    
    # Replace POST fetch calls
    $postPattern = 'await fetch\(buildApiUrl\(([^)]+)\),\s*\{[^}]*method:\s*[''"]POST[''"]'
    if ($content -match $postPattern) {
        # This is more complex, need to handle each case
        $lines = $content -split "`n"
        $newLines = @()
        $i = 0
        
        while ($i -lt $lines.Count) {
            $line = $lines[$i]
            
            if ($line -match 'await fetch\(buildApiUrl\(') {
                # Check if this is a POST request
                $j = $i
                $fetchBlock = ""
                $braceCount = 0
                $inFetch = $false
                
                while ($j -lt $lines.Count) {
                    $fetchBlock += $lines[$j] + "`n"
                    
                    if ($lines[$j] -match 'await fetch') {
                        $inFetch = $true
                    }
                    
                    if ($inFetch) {
                        $braceCount += ($lines[$j].ToCharArray() | Where-Object { $_ -eq '{' }).Count
                        $braceCount -= ($lines[$j].ToCharArray() | Where-Object { $_ -eq '}' }).Count
                        
                        if ($braceCount -eq 0 -and $lines[$j] -match '\)') {
                            break
                        }
                    }
                    
                    $j++
                }
                
                if ($fetchBlock -match 'method:\s*[''"]POST[''"]') {
                    # Extract endpoint and body
                    if ($fetchBlock -match 'buildApiUrl\(([^)]+)\)') {
                        $endpoint = $matches[1]
                        
                        if ($fetchBlock -match 'body:\s*JSON\.stringify\(([^)]+)\)') {
                            $body = $matches[1]
                            $replacement = "await authenticatedPost(buildApiUrl($endpoint), $body)"
                            $newLines += $line -replace 'await fetch\(buildApiUrl\([^)]+\),\s*\{', $replacement
                            $modified = $true
                            
                            # Skip the rest of the fetch block
                            $i = $j
                            continue
                        }
                    }
                }
            }
            
            $newLines += $line
            $i++
        }
        
        if ($modified) {
            $content = $newLines -join "`n"
            Write-Host "  Replaced POST fetch calls" -ForegroundColor Green
        }
    }
    
    if ($modified) {
        Set-Content $file $content -NoNewline
        Write-Host "  File updated successfully" -ForegroundColor Green
    }
    else {
        Write-Host "  No changes needed" -ForegroundColor Yellow
    }
}

Write-Host "`nMigration complete!" -ForegroundColor Green
Write-Host "Please review the changes and test the application." -ForegroundColor Cyan
