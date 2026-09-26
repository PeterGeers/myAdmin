---
inclusion: always
---

# Shell Environment

## Critical: This is a WSL workspace

The workspace lives at `/home/peter/projects/myAdmin` on **WSL Ubuntu**. The paths appear as `\\wsl.localhost\Ubuntu\...` in the editor but the terminal runs **bash on Linux**.

### Tool path split (UNC vs POSIX) — do not cross them

Two different path forms are required depending on which tool you use:

- **File / read / list / validate tools** (read_file, list_directory, format validators,
  diagnostics) need the **UNC** path: `\\wsl.localhost\Ubuntu\home\peter\projects\myAdmin\...`.
- **The bash / terminal tool** needs the **POSIX** path: `/home/peter/projects/myAdmin/...`.

Crossing them fails: a POSIX path handed to a file tool will not resolve, and the UNC path
handed to bash breaks. (Diagnostics / format validators have also been seen to mis-parse the
UNC path character-by-character — if a validator emits per-character "policy" noise, that is
the path artifact, not a real defect.)

## Shell rules

- **Always use bash/Linux commands** — `wc -l`, `cat`, `grep`, `find`, etc.
- **Never use** `wsl -d Ubuntu`, `Get-Content`, `Measure-Object`, PowerShell cmdlets, or Windows cmd commands
- **Working directory** for terminal commands: `/home/peter/projects/myAdmin`
- **Never use the `cwd` parameter.** It emits Windows-style backslash paths
  (`cd "\home\..."`) that do not resolve on Linux. **Always** put an **inline POSIX `cd`**
  inside the command: `bash -lc 'cd /home/peter/projects/myAdmin && <cmd>'`.
- Python virtual env is at `backend/.venv` — activate with `source backend/.venv/bin/activate`
- Use `wc -l <file>` to count lines, `cat <file>` to view files in terminal
- **Empty / absent output does NOT mean failure — and does NOT mean the command stopped.**
  Many commands are still running when the terminal shows no output yet. Wait for the in-band
  `<<<DONE marker=$?>>>` marker before concluding anything. Do **not** blindly re-run — a
  mutating command may still be in flight. Piping to `tail`/`head`/`grep` can also swallow
  output; if you truly need it, redirect to a file under `.agent-output/` and read that.
- **Long-running processes** (dev servers, `sam local`, `docker compose up`, watchers) must
  **never** run in the foreground — run them in the background / via `control_bash_process`,
  not a blocking terminal call. See `42-local-dynamodb-testing.md`.

## Common patterns

```bash
# Count lines
wc -l backend/src/services/some_file.py

# Run tests
cd backend && source .venv/bin/activate && pytest tests/unit/test_something.py -v

# Run single Python file
cd backend && source .venv/bin/activate && python src/some_script.py
```

## Database connections (local Docker vs Railway) — see `#database` skill

Connection details are NOT in this file — the single source is the **`#database`
skill** (`.kiro/skills/database.md`: hosts, ports, the `finance`/`testfinance`
schemas, the migration runner). Load it whenever a task touches a DB connection,
migration, or a query against real data. Just enough to know when to reach for it:

- **Local dev** targets Docker MySQL via the `DB_*` vars in `.env` — never edit
  those to point elsewhere.
- **Railway (production/ops)** connection facts live in `.env` under `RAILWAY_DB_*`
  (gitignored; Railway can rotate the proxy host/port). Real credentials never go
  in steering or skills — placeholders only.
- **To run anything against Railway from WSL**, use the wrapper — it maps
  `RAILWAY_DB_*` onto `DB_*` for one command so local dev config is untouched:
  ```bash
  PYTHONPATH=backend/src backend/scripts/railway-db.sh python <script.py>
  ```
  Defaults to production `finance`; pass `TEST_MODE=true` for `testfinance`.

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

# AWS CLI: use --output json; belt-and-suspenders --no-cli-pager (pagers are
# already disabled globally — see "Pagers are disabled globally" below):
cd /home/peter/projects/myAdmin && aws <svc> <cmd> \
  --profile personal --region eu-west-1 --output json
# then append the marker:  ; printf '\n<<<DONE marker=%s>>>\n' "$?"
```

### Pagers are disabled globally (do not let a pager block the shell)

The WSL terminal integration **hangs** if a command opens an interactive pager
(`less`/`more`) — it sits at a `HELP -- Press RETURN` prompt and hijacks every later
command. This is now prevented at the environment level (set once, persists across
sessions):

- `~/.bashrc` exports `PAGER=cat`, `GIT_PAGER=cat`, `AWS_PAGER=""`.
- `~/.aws/config` sets `cli_pager =` for the `default`, `personal`, and
  `nonprofit-deploy` profiles.

So `aws`, `git`, `man`, etc. no longer page by default. If you ever add a new AWS
profile, add `cli_pager =` to it (`aws configure set cli_pager "" --profile <name>`).
Passing `--no-cli-pager` / piping to `| cat` remains a harmless belt-and-suspenders.

### AWS accounts (see 23-aws-accounts.md)
- Cognito/identity: profile `personal`, account `344561557829`, region `eu-west-1`.
- Infra/data (DynamoDB/API GW/Lambda): profile `nonprofit-deploy`, account `506221081911`.

### ⚠️ `.env` credentials override `AWS_PROFILE` — strip them for `nonprofit-deploy`

The repo-root `.env` (auto-loaded by many scripts, and often `source`d into the shell)
exports **static `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for the `personal`
account** plus `AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000`. boto3's credential
chain ranks **static env keys ABOVE `AWS_PROFILE`**, so a plain
`AWS_PROFILE=nonprofit-deploy python …` **silently runs against the WRONG account
(`personal` 344561557829)** — surfacing as `ResourceNotFoundException` on tables that
only exist in `nonprofit-deploy` (e.g. `sam-members`, `governance_projection`). The
endpoint var likewise silently redirects DynamoDB to the local emulator.

So for ANY script/CLI that must hit the `nonprofit-deploy` account, **strip both** and
let the profile resolve:

```bash
env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy <command>
```

**Always sanity-check identity first** — with the strip, this MUST print
`506221081911` (NonprofitDeployRole), not `344561557829`:

```bash
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json
```

(The `personal` account is the DEFAULT the raw `.env` keys give you, so `personal`-account
work needs no strip — but never assume; check the identity when it matters.)

## Task output & log files — reduce read-approval friction

Reading a file is a gated tool action (each read is an untrusted-content boundary), so
task-generated `.log`/`.txt` output can trigger per-file read approvals. Minimise that:

- **Prefer streaming stdout over the log-file round-trip.** Run the command and read its
  stdout directly (append the `<<<DONE marker=$?>>>` marker) instead of
  `cmd > out.log` then reading `out.log`. Most verification (pytest summaries, build
  output) needs no file at all — judge success from the streamed output.
- **When a scratch file is genuinely needed, write it under the repo-root
  `.agent-output/`.** The canonical location is
  `/home/peter/projects/myAdmin/.agent-output/` for the bash/terminal tool and
  `\\wsl.localhost\Ubuntu\home\peter\projects\myAdmin\.agent-output\` for file
  tools — always resolve it against the repo root, never against the current
  working directory (a relative `.agent-output/` from inside `backend/` lands in
  the wrong place, e.g. a stray `backend/.agent-output/`). It is the one
  conventional, git-ignored home for task logs / command dumps / temporary output
  (`.gitignore` line: `.agent-output/`). Keeping scratch in one known place avoids
  new-path surprises and keeps logs out of commits. Clean it up when done.
- **Keep approvals meaningful for sensitive files.** Reads of `.env`, credential stores,
  keys, and anything under `**/*secret*` / `**/*credential*` should still prompt — the
  gate earns its keep there, not on your own build logs.
