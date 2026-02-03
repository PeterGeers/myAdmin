#!/usr/bin/env node

/**
 * myAdmin Custom MCP Server
 * 
 * Provides project-specific tools for the myAdmin finance application:
 * - Database queries with domain knowledge
 * - XBRL validation helpers
 * - Tax calculation utilities
 * - Dutch tax authority integration helpers
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { readFile } from 'fs/promises';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Server instance
const server = new Server(
  {
    name: 'myAdmin',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

/**
 * List available tools
 */
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'get_env_config',
        description: 'Get environment configuration from .env files (backend or frontend)',
        inputSchema: {
          type: 'object',
          properties: {
            location: {
              type: 'string',
              enum: ['backend', 'frontend', 'root'],
              description: 'Which .env file to read',
            },
          },
          required: ['location'],
        },
      },
      {
        name: 'validate_xbrl_structure',
        description: 'Validate XBRL file structure and check for required elements',
        inputSchema: {
          type: 'object',
          properties: {
            file_path: {
              type: 'string',
              description: 'Path to XBRL file relative to project root',
            },
          },
          required: ['file_path'],
        },
      },
      {
        name: 'get_tax_calculation_info',
        description: 'Get information about tax calculation logic and formulas',
        inputSchema: {
          type: 'object',
          properties: {
            tax_type: {
              type: 'string',
              enum: ['btw', 'ib', 'toeristenbelasting'],
              description: 'Type of tax calculation',
            },
          },
          required: ['tax_type'],
        },
      },
      {
        name: 'get_database_schema',
        description: 'Get database schema information for finance tables',
        inputSchema: {
          type: 'object',
          properties: {
            table_name: {
              type: 'string',
              description: 'Optional: specific table name, or leave empty for all tables',
            },
          },
        },
      },
      {
        name: 'get_api_endpoints',
        description: 'List available API endpoints with authentication requirements',
        inputSchema: {
          type: 'object',
          properties: {
            module: {
              type: 'string',
              description: 'Optional: filter by module (e.g., "banking", "str", "tax")',
            },
          },
        },
      },
    ],
  };
});

/**
 * Handle tool execution
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'get_env_config': {
        const location = args.location;
        let envPath;
        
        if (location === 'root') {
          envPath = join(__dirname, '.env');
        } else {
          envPath = join(__dirname, location, '.env');
        }

        try {
          const content = await readFile(envPath, 'utf-8');
          const lines = content.split('\n');
          const config = {};
          
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed && !trimmed.startsWith('#')) {
              const [key, ...valueParts] = trimmed.split('=');
              if (key) {
                // Mask sensitive values
                const value = valueParts.join('=');
                if (key.includes('SECRET') || key.includes('PASSWORD') || key.includes('KEY')) {
                  config[key.trim()] = '***MASKED***';
                } else {
                  config[key.trim()] = value.trim();
                }
              }
            }
          }

          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(config, null, 2),
              },
            ],
          };
        } catch (error) {
          return {
            content: [
              {
                type: 'text',
                text: `Error reading .env file: ${error.message}`,
              },
            ],
            isError: true,
          };
        }
      }

      case 'validate_xbrl_structure': {
        const filePath = join(__dirname, args.file_path);
        
        try {
          const content = await readFile(filePath, 'utf-8');
          
          // Basic XBRL validation
          const checks = {
            hasXmlDeclaration: content.startsWith('<?xml'),
            hasXbrlNamespace: content.includes('xmlns:xbrli') || content.includes('xmlns="http://www.xbrl.org'),
            hasContext: content.includes('<context') || content.includes('<xbrli:context'),
            hasUnit: content.includes('<unit') || content.includes('<xbrli:unit'),
            hasFacts: content.includes('contextRef='),
          };

          const isValid = Object.values(checks).every(v => v);

          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  valid: isValid,
                  checks,
                  message: isValid ? 'XBRL structure appears valid' : 'XBRL structure has issues',
                }, null, 2),
              },
            ],
          };
        } catch (error) {
          return {
            content: [
              {
                type: 'text',
                text: `Error validating XBRL: ${error.message}`,
              },
            ],
            isError: true,
          };
        }
      }

      case 'get_tax_calculation_info': {
        const taxType = args.tax_type;
        
        const info = {
          btw: {
            description: 'BTW (VAT) calculation for quarterly tax returns',
            key_files: [
              'backend/src/btw_processor.py',
              'backend/templates/html/btw_aangifte_html_report.html',
            ],
            calculation: 'Omzet * BTW_tarief - Voorbelasting',
            rates: ['21%', '9%', '0%'],
          },
          ib: {
            description: 'Income Tax (Inkomstenbelasting) calculation',
            key_files: [
              'backend/src/services/resultaat_service.py',
              'backend/templates/html/aangifte_ib_html_report.html',
            ],
            calculation: 'Winst uit onderneming - Aftrekposten',
            components: ['Revenue', 'Expenses', 'Deductions'],
          },
          toeristenbelasting: {
            description: 'Tourist tax calculation based on bookings',
            key_files: [
              'backend/src/services/toeristenbelasting_service.py',
            ],
            calculation: 'Aantal nachten * Tarief per nacht',
            data_source: 'STR booking data',
          },
        };

        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(info[taxType] || { error: 'Unknown tax type' }, null, 2),
            },
          ],
        };
      }

      case 'get_database_schema': {
        const schemaInfo = {
          main_tables: [
            'transactions',
            'invoices',
            'bookings',
            'tax_returns',
            'tenants',
            'users',
          ],
          schema_files: [
            'backend/sql/schema.sql',
            'backend/CREATE_TESTDB_COMMANDS.md',
          ],
          note: 'Use MySQL Workbench or check sql/ directory for detailed schema',
        };

        if (args.table_name) {
          schemaInfo.requested_table = args.table_name;
          schemaInfo.suggestion = `Check backend/sql/ directory for ${args.table_name} schema`;
        }

        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(schemaInfo, null, 2),
            },
          ],
        };
      }

      case 'get_api_endpoints': {
        const endpoints = {
          authentication: {
            base: '/api/auth',
            endpoints: [
              'POST /login',
              'POST /logout',
              'POST /refresh',
              'GET /me',
            ],
            auth_required: false,
          },
          banking: {
            base: '/api/banking',
            endpoints: [
              'POST /upload',
              'GET /transactions',
              'POST /categorize',
            ],
            auth_required: true,
          },
          str: {
            base: '/api/str',
            endpoints: [
              'POST /upload',
              'GET /bookings',
              'POST /process',
            ],
            auth_required: true,
          },
          tax: {
            base: '/api/tax',
            endpoints: [
              'GET /btw',
              'GET /ib',
              'GET /toeristenbelasting',
              'POST /generate-report',
            ],
            auth_required: true,
          },
          templates: {
            base: '/api/templates',
            endpoints: [
              'GET /',
              'POST /validate',
              'POST /preview',
              'POST /approve',
              'POST /reject',
            ],
            auth_required: true,
          },
        };

        const filtered = args.module 
          ? { [args.module]: endpoints[args.module] }
          : endpoints;

        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(filtered, null, 2),
            },
          ],
        };
      }

      default:
        return {
          content: [
            {
              type: 'text',
              text: `Unknown tool: ${name}`,
            },
          ],
          isError: true,
        };
    }
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Error executing tool: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

/**
 * Start the server
 */
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('myAdmin MCP Server running on stdio');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});
