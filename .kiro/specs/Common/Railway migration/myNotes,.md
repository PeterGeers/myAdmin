Deployed via GitHub

Add Railway IaC configuration with organized structure

PeterGeers/myAdmin

main

/railway/mysql

Configuration


Pretty


Code

Configuration merged from service settings and /railway/mysql/railway.toml

Edit /railway/mysql/railway.toml in GitHub ↗
Format

JSON

{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "backend/Dockerfile",
    "buildEnvironment": "V3"
  },
  "deploy": {
    "runtime": "V2",
    "numReplicas": 1,
    "startCommand": "python start_railway.py",
    "limitOverride": {
      "containers": {
        "memoryBytes": 3000000000
      }
    },
    "healthcheckPath": "/api/health",
    "sleepApplication": false,
    "useLegacyStacker": false,
    "multiRegionConfig": {
      "europe-west4-drams3a": {
        "numReplicas": 1
      }
    },
    "restartPolicyType": "ON_FAILURE",
    "healthcheckTimeout": 300,
    "restartPolicyMaxRetries": 10
  }
}


You reached the start of the range
Feb 13, 2026, 5:30 PM
scheduling build on Metal builder "builder-ogyhxq"
[snapshot] received sha256:390d36dec83198e369584fe7ab694ffcc753b78c115954e40860cd7a5bf49510 md5:e0908a4e3a845a177a517c7c30a9a6bc
receiving snapshot
15.1 MB
2.4s
root directory set as 'railway/mysql'
config-as-code path set as '/railway.toml'
skipping 'Dockerfile' at 'backend/Dockerfile' as it is not rooted at a valid path (root_dir=railway/mysql, fileOpts={acceptChildOfRepoRoot:false})
skipping 'nixpacks.toml' at 'backend/nixpacks.toml' as it is not rooted at a valid path (root_dir=railway/mysql, fileOpts={acceptChildOfRepoRoot:false})
skipping 'railway.json' at 'backend/railway.json' as it is not rooted at a valid path (root_dir=railway/mysql, fileOpts={acceptChildOfRepoRoot:true})
skipping 'railway.toml' at 'backend/railway.toml' as it is not rooted at a valid path (root_dir=railway/mysql, fileOpts={acceptChildOfRepoRoot:true})
found 'Dockerfile' at 'railway/mysql/Dockerfile'
found 'railway.toml' at 'railway/mysql/railway.toml'
root directory sanitized to 'railway/mysql'
config-as-code path sanitized to 'railway.toml'
analyzing snapshot
15.1 MB
360ms
uploading snapshot
15.1 MB
383ms
scheduling build on Metal builder "builder-ogyhxq"

fetched snapshot sha256:390d36dec83198e369584fe7ab694ffcc753b78c115954e40860cd7a5bf49510 (16 MB bytes)
fetching snapshot
15.1 MB
339ms
unpacking archive
52.4 MB
514ms

internal
load build definition from backend/Dockerfile
0ms

internal
load metadata for docker.io/library/python:3.11-slim
236ms

internal
load .dockerignore
0ms

1
FROM docker.io/library/python:3.11-slim@sha256:0b23cfb7425d065008b778022a17b1551c82f8b4866ee5a7a200084b7e2eafbf
11ms

internal
load build context
0ms

2
WORKDIR /app cached
0ms

3
RUN apt-get update && apt-get install -y   curl   && rm -rf /var/lib/apt/lists/* cached
263ms

4
COPY requirements.txt .
0ms
Build Failed: build daemon returned an error < failed to solve: failed to compute cache key: failed to calculate checksum of ref jdyjr6dgvak77nseaw6nf8nz9::rg4auq3nz6cs972xjta5sahqj: "/requirements.txt": not found >
