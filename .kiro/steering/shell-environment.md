---
inclusion: auto
---

# Shell Environment

## Critical: This is a WSL workspace

The workspace lives at `/home/peter/projects/myAdmin` on **WSL Ubuntu**. The paths appear as `\\wsl.localhost\Ubuntu\...` in the editor but the terminal runs **bash on Linux**.

## Shell rules

- **Always use bash/Linux commands** — `wc -l`, `cat`, `grep`, `find`, etc.
- **Never use** `wsl -d Ubuntu`, `Get-Content`, `Measure-Object`, PowerShell cmdlets, or Windows cmd commands
- **Working directory** for terminal commands: `/home/peter/projects/myAdmin`
- Use `cwd` parameter set to `/home/peter/projects/myAdmin` (or subdirectories) when running commands
- Python virtual env is at `backend/.venv` — activate with `source backend/.venv/bin/activate`
- Use `wc -l <file>` to count lines, `cat <file>` to view files in terminal

## Common patterns

```bash
# Count lines
wc -l backend/src/services/some_file.py

# Run tests
cd backend && source .venv/bin/activate && pytest tests/unit/test_something.py -v

# Run single Python file
cd backend && source .venv/bin/activate && python src/some_script.py
```

## AWS CLI & exit codes on this WSL setup (important)

The terminal integration in this environment **always reports `Exit Code: -1`**, even
when a command succeeds. Do **not** treat -1 as failure. Judge success by:

- the command's **stdout/stderr content**, and
- an **in-band success marker** you append yourself.

### Required patterns

```bash
# Always cd with the POSIX path inline (the tool may inject a broken
# Windows-style `cd "\home\..."` prefix — ignore that error line).
cd /home/peter/projects/myAdmin && <your command>

# Judge success by this marker, NOT the tool's exit code:
<your command>; printf '\n<<<DONE marker=%s>>>\n' "$?"
# marker=0 means success. Non-zero means real failure.

# AWS CLI: the pager (less) can block/hang the session. ALWAYS disable it
# both via env and flag, use --output json, and pipe long output to cat:
cd /home/peter/projects/myAdmin && AWS_PAGER="" aws <svc> <cmd> \
  --profile personal --region eu-west-1 --no-cli-pager --output json 2>&1 | cat
# then append the marker:  ; printf '\n<<<DONE marker=%s>>>\n' "$?"
```

### AWS accounts (see aws-accounts.md)
- Cognito/identity: profile `personal`, account `344561557829`, region `eu-west-1`.
- Infra/data (DynamoDB/API GW/Lambda): profile `nonprofit-deploy`, account `506221081911`.
