Failed to connect to MCP server "power-terraform-terraform": MCP error -32000: Connection closed


---

## Analysis

### Issue Summary

The Terraform MCP server (power-terraform-terraform) fails to connect with error:

```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

### Root Cause

The Terraform power is configured to run as a Docker container (`docker run -i --rm hashicorp/terraform-mcp-server`), which creates a Docker-in-Docker scenario. The container is trying to access the host's Docker daemon but:

1. The container is looking for the wrong pipe path: `npipe:////./pipe/dockerDesktopLinuxEngine`
2. Docker Desktop on Windows uses: `npipe://\\.\pipe\docker_engine` or `npipe://\\.\pipe\docker_cli`
3. The Docker socket is not mounted into the container

### Docker Status

Docker Desktop is running correctly:

- Server Version: 29.2.0
- Containers: 12 (2 running, 10 stopped)
- Images: 5
- Docker Root Dir: /var/lib/docker
- Address: `npipe://\\.\pipe\docker_cli`

### Impact

- **Severity**: Low
- **Affected**: Only the Terraform power functionality
- **Working**: All other MCP servers loaded successfully:
  - ✅ fetch
  - ✅ filesystem
  - ✅ brave-search
  - ✅ aws-docs
  - ✅ myAdmin
  - ✅ power-aws-infrastructure-as-code
  - ✅ power-cloud-architect (awspricing, awsknowledge, awsapi, context7, fetch)
  - ✅ power-postman
  - ❌ power-terraform

### Solutions

#### Option 1: Disable the Terraform Power (Recommended)

Since Docker-in-Docker on Windows has limitations, disable the power if not actively needed:

1. Open Kiro command palette
2. Run "MCP: Open Server View"
3. Find "power-terraform-terraform" and disable it

#### Option 2: Fix Docker Socket Mounting (Advanced)

Update the MCP configuration at `~/.kiro/settings/mcp.json`:

```json
"power-terraform-terraform": {
  "command": "docker",
  "args": [
    "run",
    "-i",
    "--rm",
    "-v",
    "//./pipe/docker_engine://./pipe/docker_engine",
    "hashicorp/terraform-mcp-server"
  ],
  "env": {
    "DOCKER_HOST": "npipe:////./pipe/docker_engine"
  },
  "disabled": false
}
```

**Note**: Docker-in-Docker on Windows with named pipes is complex and may still have issues.

#### Option 3: Use Native Terraform MCP Server

Instead of running in Docker, install and run the Terraform MCP server natively:

```json
"power-terraform-terraform": {
  "command": "terraform-mcp-server",
  "args": [],
  "env": {},
  "disabled": false
}
```

This requires installing the Terraform MCP server binary on the host system.

### Recommendation

**Leave as-is or disable the power.** The error is harmless and doesn't affect other functionality. Only address if Terraform power features are actively needed.

### Status

- **Date**: 2026-02-24
- **Resolution**: Known limitation - Docker-in-Docker on Windows
- **Action Required**: None (unless Terraform functionality is needed)
