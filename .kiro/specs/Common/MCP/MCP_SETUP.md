# MCP Configuration Guide

## Overview

Your MCP setup consists of two parts:

1. **User-level configuration** - Shared across all projects
2. **Custom myAdmin server** - Project-specific tools

## User-Level MCP Servers

Location: `~/.kiro/settings/mcp.json`

### Active Servers

1. **fetch** ✅
   - Download files from URLs
   - Get Belastingdienst documentation, XBRL schemas
   - Auto-approved for convenience

2. **filesystem** ✅
   - Advanced file operations in your `~/aws` directory
   - Useful for processing downloaded schemas
   - Fixed: Now using `npx` with `@modelcontextprotocol/server-filesystem`

3. **aws-docs** ✅
   - AWS documentation access
   - Helpful for Cognito, infrastructure work

4. **brave-search** ✅
   - Web search capabilities
   - Fixed: Now using `npx` with `@modelcontextprotocol/server-brave-search`
   - API key configured

### Disabled Servers (Enable when needed)

5. **postgres** ⏸️
   - Direct database queries via MCP
   - Update connection string: `postgresql://user:password@localhost/finance`
   - Change `"disabled": false` to enable

## Custom myAdmin MCP Server

Location: `./mcp-server.js`

### Available Tools

1. **get_env_config**
   - Read environment configuration
   - Automatically masks sensitive values
   - Usage: `location: "backend" | "frontend" | "root"`

2. **validate_xbrl_structure**
   - Validate XBRL file structure
   - Check for required elements
   - Usage: `file_path: "path/to/file.xml"`

3. **get_tax_calculation_info**
   - Get tax calculation formulas and logic
   - Usage: `tax_type: "btw" | "ib" | "toeristenbelasting"`

4. **get_database_schema**
   - Database schema information
   - Usage: `table_name: "optional_table_name"`

5. **get_api_endpoints**
   - List API endpoints with auth requirements
   - Usage: `module: "banking" | "str" | "tax" | etc.`

## Prerequisites

### For uvx-based servers (fetch, aws-docs, etc.)

Install `uv` Python package manager:

```powershell
# Using pip
pip install uv

# Or using Homebrew (if available)
brew install uv

# Or download from https://docs.astral.sh/uv/getting-started/installation/
```

Once `uv` is installed, `uvx` is automatically available.

### For npx-based servers (filesystem, brave-search)

Node.js must be installed (which you already have). The `npx` command comes with Node.js and will automatically download and run the packages.

### For custom myAdmin server

Already installed! Dependencies are in `package.json`.

## Usage

### In Kiro

MCP servers connect automatically when Kiro starts. You can:

1. **View MCP servers**: Open MCP Server view in Kiro feature panel
2. **Reconnect servers**: Use command palette → "MCP: Reconnect Servers"
3. **Test tools**: Just ask me to use them!

### Testing Custom Server

Try asking:

- "Get the backend environment configuration"
- "What are the BTW calculation formulas?"
- "List all API endpoints"
- "Show me the database schema"

## Configuration Updates

### Enable brave-search

Already enabled! The correct configuration is now in place:

- Command: `npx -y @modelcontextprotocol/server-brave-search`
- API key is already set
- Should work after reconnecting MCP servers

Note: These are Node.js packages, so they use `npx` instead of `uvx`.

### Enable postgres

1. Edit `~/.kiro/settings/mcp.json`
2. Update connection string with your credentials
3. Change `"disabled": false`
4. Reconnect MCP servers in Kiro

### Add more servers

Edit `~/.kiro/settings/mcp.json` and add to `mcpServers` object. Common servers:

- `mcp-server-sqlite` - SQLite database access
- `mcp-server-github` - GitHub API access
- `mcp-server-google-drive` - Google Drive access

## Troubleshooting

### Server won't connect

1. For Python servers (uvx): Check if `uv` is installed: `uv --version`
2. For Node.js servers (npx): Check if Node.js is installed: `node --version`
3. Check Kiro MCP Server view for error messages
4. Try reconnecting servers from command palette
5. Check Kiro MCP Server view for error messages
6. Try reconnecting servers from command palette

### Custom server errors

1. Check Node.js is installed: `node --version`
2. Verify dependencies: `npm install` in project root
3. Check server logs in Kiro MCP Server view

### Update configuration

After editing `~/.kiro/settings/mcp.json`:

- Use command palette → "MCP: Reconnect Servers"
- Or restart Kiro

## Next Steps

1. ✅ Install `uv` if not already installed
2. ✅ Fixed brave-search and filesystem package names
3. ✅ Restart Kiro to load MCP servers
4. ✅ Test by asking me to use MCP tools
5. ⏸️ Enable postgres when you need database access

## Resources

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Available MCP Servers](https://github.com/modelcontextprotocol/servers)
- [uv Installation](https://docs.astral.sh/uv/getting-started/installation/)
