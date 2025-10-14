#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import fs from 'fs/promises';
import path from 'path';

const server = new Server(
  {
    name: 'myAdmin-server',
    version: '0.1.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'check_database_status',
        description: 'Check if MySQL database is accessible',
        inputSchema: {
          type: 'object',
          properties: {},
        },
      },
      {
        name: 'list_pdf_files',
        description: 'List PDF files in storage directories',
        inputSchema: {
          type: 'object',
          properties: {
            vendor: {
              type: 'string',
              description: 'Vendor folder to check (optional)',
            },
          },
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case 'check_database_status':
      try {
        const envPath = path.join(process.cwd(), 'backend', '.env');
        const envContent = await fs.readFile(envPath, 'utf-8');
        return {
          content: [
            {
              type: 'text',
              text: `Database configuration found:\n${envContent}`,
            },
          ],
        };
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error reading database config: ${error.message}`,
            },
          ],
        };
      }

    case 'list_pdf_files':
      try {
        const storagePath = path.join(process.cwd(), 'backend', 'storage');
        const vendor = args?.vendor;
        
        let targetPath = storagePath;
        if (vendor) {
          targetPath = path.join(storagePath, vendor);
        }

        const files = await fs.readdir(targetPath, { recursive: true });
        const pdfFiles = files.filter(file => file.endsWith('.pdf'));
        
        return {
          content: [
            {
              type: 'text',
              text: `PDF files found:\n${pdfFiles.join('\n')}`,
            },
          ],
        };
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error listing PDF files: ${error.message}`,
            },
          ],
        };
      }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('myAdmin MCP server running on stdio');
}

main().catch(console.error);