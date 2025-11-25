# View Docker container logs
param(
    [string]$Container = "backend",
    [switch]$Follow,
    [int]$Tail = 50
)

$containerName = if ($Container -eq "backend") { "myadmin-backend-1" } else { "myadmin-mysql-1" }

Write-Host "Viewing logs for $containerName..." -ForegroundColor Green

if ($Follow) {
    docker logs -f --tail $Tail $containerName
} else {
    docker logs --tail $Tail $containerName
}