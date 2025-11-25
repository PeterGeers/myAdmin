# VS Code Build Tasks

These tasks let you quickly start your servers from VS Code's Command Palette or keyboard shortcuts instead of manually running commands in terminals.

## Available Tasks

### "Start Backend" task
- Activates Python virtual environment in backend folder
- Changes to src directory and runs `python app.py`
- Opens in a new terminal panel

### "Start Frontend" task
- Changes to frontend folder and runs `npm start`
- Opens in a new terminal panel

### "Start Both Servers" task
- Runs both backend and frontend tasks in parallel
- Set as the default build task

## Usage

- **Keyboard shortcut**: `Ctrl+Shift+P` → "Tasks: Run Build Task"
- **Command Palette**: Search for "Tasks: Run Task" to see all available tasks