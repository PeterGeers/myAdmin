# PowerShell script to update all report components to use useTypedTranslation
$files = @(
    "frontend/src/components/reports/AangifteIbReport.tsx",
    "frontend/src/components/reports/ActualsReport.tsx",
    "frontend/src/components/reports/BnbActualsReport.tsx",
    "frontend/src/components/reports/BnbCountryBookingsReport.tsx",
    "frontend/src/components/reports/BnbFutureReport.tsx",
    "frontend/src/components/reports/BnbReportsGroup.tsx",
    "frontend/src/components/reports/BnbReturningGuestsReport.tsx",
    "frontend/src/components/reports/BnbRevenueReport.tsx",
    "frontend/src/components/reports/BnbViolinsReport.tsx",
    "frontend/src/components/reports/BtwReport.tsx",
    "frontend/src/components/reports/MutatiesReport.tsx",
    "frontend/src/components/reports/ReferenceAnalysisReport.tsx",
    "frontend/src/components/reports/ToeristenbelastingReport.tsx"
)

foreach ($file in $files) {
    $content = Get-Content $file -Raw
    $content = $content -replace "import \{ useTranslation \} from 'react-i18next';", "import { useTypedTranslation } from '../../hooks/useTypedTranslation';"
    $content = $content -replace "const \{ t \} = useTranslation\('reports'\);", "const { t } = useTypedTranslation('reports');"
    $content = $content -replace "const \{ t, i18n \} = useTranslation\('reports'\);", "const { t, i18n } = useTypedTranslation('reports');"
    Set-Content $file -Value $content -NoNewline
    Write-Host "Updated: $file"
}

Write-Host "`nAll files updated successfully!"
