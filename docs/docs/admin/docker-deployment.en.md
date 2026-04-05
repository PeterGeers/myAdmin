# Docker Deployment

> Manage, start, stop, and update Docker containers.

## Overview

myAdmin runs in Docker containers: a MySQL database and a Flask backend. This page describes how to manage the containers.

## Architecture

| Container   | Image        | Port | Resources           |
| ----------- | ------------ | ---- | ------------------- |
| **mysql**   | MySQL 8.0    | 3306 | 2 GB RAM, 1 CPU     |
| **backend** | Flask/Python | 5000 | 512 MB RAM, 1.5 CPU |

MySQL data is stored in `./mysql_data/` on the host, so data persists across container restarts.

## Step by Step

### Start all services

```bash
docker-compose up -d
```

### Stop all services

```bash
docker-compose down
```

### View logs

```bash
docker-compose logs -f backend    # Backend logs
docker-compose logs -f mysql      # Database logs
```

### Rebuild after code changes

```bash
docker-compose up -d --build
```

### Check status

```bash
docker-compose ps
```

## Health check

The backend has a built-in health check:

- **Endpoint**: `http://localhost:5000/api/health`
- **Interval**: Every 30 seconds
- **Timeout**: 10 seconds
- **Retries**: 3 attempts
- **Start period**: 40 seconds wait on startup

## Environment variables

The backend reads configuration from `backend/.env`. Key variables:

| Variable               | Description                        |
| ---------------------- | ---------------------------------- |
| `DB_HOST`              | Database host (in Docker: `mysql`) |
| `DB_USER`              | Database user                      |
| `DB_PASSWORD`          | Database password                  |
| `DB_NAME`              | Database name                      |
| `TEST_MODE`            | `true` or `false`                  |
| `AWS_REGION`           | AWS region for Cognito             |
| `COGNITO_USER_POOL_ID` | AWS Cognito User Pool ID           |

!!! warning
Don't change `DB_HOST` in the Docker configuration — it's automatically overridden to `mysql` (the container name).

## Volumes

| Volume         | Host path          | Container path        | Purpose           |
| -------------- | ------------------ | --------------------- | ----------------- |
| MySQL data     | `./mysql_data`     | `/var/lib/mysql`      | Database files    |
| Backend code   | `./backend`        | `/app`                | Application code  |
| Frontend build | `./frontend/build` | `/app/frontend/build` | Static frontend   |
| Reports        | Configurable       | `/app/reports`        | Generated reports |

## Tips

!!! tip
Use `docker-compose logs -f backend` to see what the backend is doing in real-time. This is useful for debugging.

- Always start MySQL before the backend (docker-compose handles this automatically via `depends_on`)
- MySQL data survives container restarts thanks to the host directory mapping
- Use `--build` after changing Python dependencies

## Troubleshooting

| Problem             | Cause                            | Solution                                                            |
| ------------------- | -------------------------------- | ------------------------------------------------------------------- |
| Backend won't start | MySQL not ready yet              | Wait 40 seconds (start_period) or restart the backend               |
| Port 5000 in use    | Another application on port 5000 | Stop the other application or change the port in docker-compose.yml |
| MySQL data lost     | Volume not correctly mounted     | Check that `./mysql_data/` exists and is writable                   |
| Out of memory       | Container exceeds memory limit   | Increase `mem_limit` in docker-compose.yml                          |
