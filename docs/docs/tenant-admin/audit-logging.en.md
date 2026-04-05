# Audit Logging

> Track activities and generate compliance reports.

## Overview

myAdmin automatically maintains an audit log of all important actions. As Tenant Admin, you can view these logs to check who did what and when.

## What gets logged?

| Action                | What is recorded                              |
| --------------------- | --------------------------------------------- |
| Saving transactions   | User, timestamp, number of records, tenant    |
| Duplicate decisions   | Choice (continue/cancel), transaction details |
| Uploading invoices    | Filename, vendor, user                        |
| Importing bookings    | Platform, number of bookings, user            |
| Configuration changes | Key, old/new value, user                      |
| User management       | Creation, role changes, deletion              |
| Tax reports           | Generation, saving, exporting                 |

## What is stored per log entry?

| Field      | Description                                                      |
| ---------- | ---------------------------------------------------------------- |
| Timestamp  | Date and time of the action                                      |
| User       | Email address of the user                                        |
| Session ID | Unique session identifier                                        |
| Action     | Type of action (e.g., "save_transactions", "duplicate_decision") |
| Details    | Specific information about the action                            |
| Tenant     | Administration in which the action took place                    |

## Available reports

### User activity report

Shows all actions by a specific user over a given period. Useful for checking what a staff member has done.

### Compliance report

A comprehensive report with:

- Total number of actions per type
- Actions per user
- Timeline of activities
- Unusual patterns (many actions in a short time)

### Transaction audit trail

For a specific transaction, you can view the complete history:

- When created
- By whom
- What changes were made
- Duplicate decisions

## Log management

### Export logs

Audit logs can be exported as CSV for external analysis or archiving.

### Clean up old logs

Logs older than a configured period can be cleaned up to keep the database compact.

!!! warning
Keep audit logs for at least 7 years for tax purposes. Only clean up logs that fall outside the legal retention period.

## Tips

!!! tip
Check the audit log regularly, especially after importing large amounts of data. This helps you quickly spot errors.

- All duplicate decisions are logged — useful if you later want to check why a transaction was or wasn't imported
- The audit log is read-only — logs cannot be modified or deleted via the interface

## Troubleshooting

| Problem          | Cause                                       | Solution                            |
| ---------------- | ------------------------------------------- | ----------------------------------- |
| No logs visible  | No actions performed in the selected period | Adjust the date filters             |
| Logs load slowly | Large amount of logs                        | Limit the period or filter by user  |
| User not in logs | User hasn't performed any actions           | Normal if the user only viewed data |
