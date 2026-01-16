# Stop myAdmin Docker containers
Write-Host "Stopping myAdmin Docker containers..." -ForegroundColor Yellow

docker-compose down

Write-Host "Docker containers stopped" -ForegroundColor Green