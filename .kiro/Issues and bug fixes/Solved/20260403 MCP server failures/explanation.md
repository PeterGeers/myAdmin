# MCP Server Failures — Explanation

**Date:** 2026-04-03
**Status:** Resolved

## Problem

Two MCP servers fail with timeout errors on every Kiro startup:

1. `power-aws-infrastructure-as-code-awslabs.aws-iac-mcp-server` — MCP error -32001: Request timed out
2. `power-terraform-terraform` — MCP error -32001: Request timed out

## Root cause

- 16 MCP servers start simultaneously on Kiro launch
- The IAC server uses a FastMCP proxy bridge that takes too long to initialize
- The Terraform server runs in a Docker container — container startup + initialization exceeds the timeout
- Both servers are Kiro Powers (installed via the Powers panel), not custom MCP servers

## Fix

Disabled servers not needed for daily development. They can be re-enabled when needed via `~/.kiro/settings/mcp.json` (set `"disabled": false`).

### Servers kept enabled (daily use)

| Server         | Purpose                     |
| -------------- | --------------------------- |
| `fetch`        | Web content fetching        |
| `filesystem`   | Local file access           |
| `brave-search` | Web search                  |
| `aws-docs`     | AWS documentation           |
| `myAdmin`      | Project-specific MCP server |

### Servers disabled (enable when needed)

| Server                             | Why disabled                           | When to enable                   |
| ---------------------------------- | -------------------------------------- | -------------------------------- |
| `power-aws-infrastructure-as-code` | Timeout on startup (proxy bridge slow) | Working on CDK/CloudFormation    |
| `power-cloud-architect-awspricing` | Not used daily                         | Checking AWS pricing             |
| `power-cloud-architect-awsapi`     | Not used daily                         | AWS API calls                    |
| `power-cloud-architect-context7`   | Not used daily                         | Context7 documentation           |
| `power-cloud-architect-fetch`      | Duplicate of `fetch` server            | Never (use main `fetch` instead) |
| `power-terraform-terraform`        | Docker container timeout               | Working on Terraform             |
| `power-postman-postman`            | Not used daily                         | API testing with Postman         |
| `power-aws-sam-*`                  | Not used daily                         | Working on SAM/Lambda            |

### Servers kept enabled (Powers)

| Server                               | Purpose                                    |
| ------------------------------------ | ------------------------------------------ |
| `power-cloud-architect-awsknowledge` | AWS knowledge base (HTTP, no startup cost) |

## How to re-enable a server

Edit `C:\Users\peter\.kiro\settings\mcp.json` and change `"disabled": false` for the server you need, then restart Kiro or use Command Palette → "MCP: Reconnect Servers".
