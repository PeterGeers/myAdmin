<<<<<<< HEAD
# PDF Transaction Processor

A ReactJS SPA with Python backend for processing PDF files, extracting transactions, and storing them in MySQL.

## Setup

### Frontend
```bash
cd frontend
npm install
npm start
```

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your database credentials
python app.py
```

### Google Drive Setup
1. Create a Google Cloud project
2. Enable Google Drive API
3. Download credentials.json to backend folder
4. Run the app and authenticate when prompted

### Database Setup
```sql
CREATE DATABASE transactions_db;
```

## Features
- PDF file upload to Google Drive
- Automatic PDF parsing and transaction extraction
- Editable transaction data before saving
- MySQL storage with transaction metadata
=======
# myAdmin
My new administrative tooling Frontend (reactjs) and Backend (python and mysql)

Perfect! I've set up MCP servers for your myAdmin project. Here's what I've created:

MCP Configuration Complete ✅
1. Claude Desktop Config - %APPDATA%\Claude\claude_desktop_config.json

Filesystem server - Access to your entire myAdmin project

Sequential thinking server - Enhanced reasoning capabilities

Custom myAdmin server - Project-specific tools

2. Custom MCP Server - mcp-server.js

check_database_status - Reads your .env database config

list_pdf_files - Lists PDFs in storage folders

3. Installed Servers:

@modelcontextprotocol/sdk - Core MCP functionality

@modelcontextprotocol/server-sequential-thinking - Advanced reasoning

Next Steps
Restart Claude Desktop to load the new MCP configuration

Test the connection by asking Claude to list files in your project

Use the tools - Ask Claude to check your database status or list PDF files

The MCP servers will give Claude direct access to your project files and custom tools for managing your PDF transaction processor.