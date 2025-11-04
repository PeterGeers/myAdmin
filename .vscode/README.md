# myAdmin VSCode Configuration

## 🚀 Quick Start (New Developer)
1. **Clone repository**: `git clone <repo-url>`
2. **Open in VSCode**: VSCode will prompt to install recommended extensions
3. **Set environment**: Create `.env` file with `DB_USER=your_username`
4. **Run setup**: `Ctrl+Shift+P` → "Tasks: Run Task" → "Setup: Install Dependencies"
5. **Start servers**: `Ctrl+Shift+P` → "Tasks: Run Task" → "Start: Both Servers"

## 📁 Configuration Files
- **settings.json**: Project settings, theme, database connections
- **extensions.json**: 42 recommended extensions for full functionality
- **launch.json**: Debug configurations for Python/React
- **tasks.json**: Common development tasks
- **snippets.code-snippets**: Code templates for Flask/React/MySQL

## 🔧 Available Tasks
- **Setup: Install Dependencies**: Install Python/Node dependencies
- **Start: Both Servers**: Launch backend (5000) + frontend (3000)
- **Test: Run Backend Tests**: Execute Python test suite

## 🎨 Theme & Layout
- **Theme**: Default Dark Modern
- **Font**: Cascadia Code with ligatures
- **Icons**: VS Seti
- **Rulers**: 80/120 characters
- **No preview tabs**: Direct file opening

## 🗄️ Database Connections
- **MyAdmin**: Production database (finance)
- **MyAdmin Test**: Test database (testfinance)
- Uses `${env:DB_USER}` environment variable

## 📝 Code Snippets
- `route`: Flask route template
- `rfc`: React functional component
- `mysql`: MySQL query template

## 🔄 Synchronization
- **Project settings**: Synced via Git
- **Personal settings**: Enable VSCode Settings Sync
- **Extensions**: Auto-installed on project open

## 🐛 Debugging
- **F5**: Start Python backend debugger
- **Attach to Chrome**: Debug React frontend
- **Breakpoints**: Full support in Python/TypeScript