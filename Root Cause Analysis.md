Root Cause Analysis
The issue is likely:

Corrupted VSCode installation

Extension conflicts causing startup failures

Profile corruption

Multiple startup attempts creating zombie processes

Immediate Fixes

1. Reset VSCode completely:

# Kill all processes

Get-Process _code_ | Stop-Process -Force

# Clear all VSCode data

Remove-Item "$env:APPDATA\Code" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\.vscode" -Recurse -Force -ErrorAction SilentlyContinue

Copy

Insert at cursor
powershell 2. Reinstall VSCode:

Uninstall VSCode from Windows Settings

Download fresh copy from https://code.visualstudio.com/

Install clean

3. Test with single instance:

# Start ONE instance only

code --new-window

Copy

Insert at cursor
powershell
The 41 instances suggest VSCode is crashing on startup and your system keeps trying to restart it. This is why disabling Copilot helped - it was likely the extension causing the crashes.

Do the cleanup first, then we can reinstall cleanly.

@Pin Context
Active file

Rules

Claude Sonnet 4
