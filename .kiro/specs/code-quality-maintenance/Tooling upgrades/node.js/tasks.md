# Implementation Plan: Upgrade Node.js (CVE-2026-111497 Remediation)

## Overview

Upgrade the Node.js runtime in this environment — and every pinned configuration — to a patched release that remediates **CVE-2026-111497** ("Node2Shell"): a buffer overflow in the Brotli decoder that allowed unauthenticated remote code execution.

- **Previous runtime:** v22.22.1 (`/usr/bin/node`)
- **Affected lines:** Node.js 22.x, 24.x, 26.x
- **Patched releases:** 22.23.4 · 24.22.1 · 26.12.1
- **Installed runtime:** **v22.23.5** (user space, `~/.local/node/node-v22.23.5-linux-x64/`)
- **EOL lines:** 20.x, 23.x, 25.x — no updates available; not used in this repo
- **NCSC:** chance of abuse "average", potential damage "major"

No **application code changes** were required — the fix lives inside the Node.js runtime's bundled Brotli library. This work item covered only **tooling/runtime upgrades**: the local runtime and all pinned CI versions.

## Pinned Configs Updated

| Location | Before | After |
|----------|--------|-------|
| Local runtime (`~/.local/bin/node`) | 22.22.1 | **22.23.5** |
| `.github/workflows/deploy-frontend.yml` (Setup Node.js) | `node-version: "22"` | `node-version: "22.23.5"` |
| `.github/workflows/frontend-ci.yml` (lint/test/build jobs) | `node-version: "22"` | `node-version: "22.23.5"` |
| `.github/workflows/full-test-suite.yml` (frontend job) | `node-version: "22"` | `node-version: "22.23.5"` |
| `frontend/tests/e2e/README.md` (example CI workflow) | `node-version: "18"` | `node-version: "22.23.5"` |

No `.nvmrc` or `.node-version` files exist at the repo root.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 1, "tasks": ["1", "2", "3"] },
    { "id": 2, "tasks": ["4"] }
  ]
}
```

## Tasks

### Wave 1: Local runtime upgrade

- [x] 1. Upgrade local Node.js runtime 22.22.1 → 22.23.5
  - [x] 1.1 Install patched Node.js (downloaded official v22.23.5 Linux x64 binary to `~/.local/node/`, symlinked into `~/.local/bin/`)
  - [x] 1.2 Verified `node --version` reports **v22.23.5**
  - [x] 1.3 Verified project still starts and npm resolves correctly

### Wave 2: Sync CI pinned Node versions

- [x] 2. Update pinned Node versions in GitHub Actions workflows + docs
  - [x] 2.1 `.github/workflows/deploy-frontend.yml` — Setup Node.js step: `node-version: "22"` → `"22.23.5"`
  - [x] 2.2 `.github/workflows/frontend-ci.yml` — same change in all 3 jobs (lint, test, build)
  - [x] 2.3 `.github/workflows/full-test-suite.yml` — frontend job: `node-version: "22"` → `"22.23.5"`
  - [x] 2.4 `frontend/tests/e2e/README.md` — example CI workflow: `node-version: "18"` → `"22.23.5"` (Node 18 is EOL)

### Wave 3: Validation & close-out

- [x] 3. Re-verified local runtime version (v22.23.5) and ran validation checks
- [x] 4. Final sweep complete: no remaining pinned Node < 22.23.4; Node 18 EOL reference updated; no EOL-version usage in repo CI configs

## Notes

- Security-only upgrade; **no code changes**.
- Node.js installed in user space (`~/.local/node/node-v22.23.5-linux-x64/`) with symlinks in `~/.local/bin/` (already first on `$PATH`).
- After upgrade: `npm audit` shows no Node.js runtime advisories. Pre-existing dependency advisories in `@hono/node-server` and `@modelcontextprotocol/sdk` are unrelated to CVE-2026-111497.
- When a major-version migration is eventually needed, the EOL lines (20.x, 23.x, 25.x) are not patchable — move to a supported LTS (≥ 22.23.4 / ≥ 24.22.1 / ≥ 26.12.1).
