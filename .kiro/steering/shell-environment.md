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
