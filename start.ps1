Write-Host "Starting PDF Transaction Processor..." -ForegroundColor Green
Write-Host ""

Write-Host "Installing Backend Dependencies..." -ForegroundColor Yellow
Set-Location backend
pip install -r requirements.txt
Write-Host ""

Write-Host "Starting Backend Server..." -ForegroundColor Yellow
$backend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "python app.py" -PassThru
Set-Location ..

Write-Host "Waiting for backend to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host "Starting Frontend Server..." -ForegroundColor Yellow
Set-Location frontend
$frontend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm start" -PassThru
Set-Location ..

Write-Host ""
Write-Host "Both servers are starting:" -ForegroundColor Green
Write-Host "Backend: http://localhost:5000 (PID: $($backend.Id))" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:3000 (PID: $($frontend.Id))" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")