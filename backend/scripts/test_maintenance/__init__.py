"""
Test Maintenance Framework
==========================

A suite of tools for maintaining test health across the myAdmin project.

This package provides:

- **Test Health Scanner** — Static analysis engine that scans test files for
  anti-patterns, mock violations, code drift, and compliance issues.
- **Test Dependency Mapper** — Import and naming-convention analyzer that maps
  source files to their corresponding test files.
- **Scoped Test Runner** — Wrapper that uses dependency mappings to run only
  tests affected by code changes.
- **Test Isolation Layer** — Enhanced conftest.py fixtures that enforce proper
  mocking of DatabaseManager, Cognito, Google Drive, and environment variables.
- **Flaky Test Quarantine** — Detection and tracking system for intermittently
  failing tests.

All tools produce machine-readable JSON output and human-readable console or
Markdown summaries. Historical reports are stored in ``backend/tests/reports/``
for trend tracking.
"""
