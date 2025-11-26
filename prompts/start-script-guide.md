# myAdmin Start Script Guide

## Usage
```powershell
.\start.ps1 [mode] [options]
```

## Modes

### `dev` (default)
- Starts Docker containers (backend + database)
- Launches React dev server in new PowerShell window
- **URLs**: Backend `http://localhost:5000`, Frontend `http://localhost:3000`

### `prod`
- Starts Docker containers
- Builds React app (`npm run build`)
- Backend serves built React files
- **URL**: `http://localhost:5000` (single server)

### `containers`
- Only manages Docker containers
- Copies `backend/.env` to root with Docker DB_HOST

## Options
- `--build` - Rebuild Docker containers
- `--lean` - Close resource apps (Copilot, Spotify, ChatGPT, OneDrive)

## Container Logic
1. Check if containers exist → Exit if not found
2. Check if containers running → Start only if stopped
3. Avoids unnecessary restarts

## Examples
```powershell
.\start.ps1                    # Dev mode
.\start.ps1 prod              # Production
.\start.ps1 containers --build # Rebuild containers
.\start.ps1 dev --lean        # Dev with resource cleanup
```