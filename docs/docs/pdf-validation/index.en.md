# PDF Validation

> Check and fix Google Drive links in your transactions.

## Overview

The PDF Validation module checks whether Google Drive links in your transactions still work. Every invoice you upload is stored in Google Drive, and the link is saved in the Ref3 field of the transaction. Over time, links can break due to moved or deleted files.

## What can you do here?

| Task                                            | Description                                            |
| ----------------------------------------------- | ------------------------------------------------------ |
| [Check and fix links](checking-fixing-links.md) | Validate all Google Drive links and repair broken ones |

## How does it work?

The system scans all transactions with a Google Drive URL in the Ref3 field and checks for each record:

| URL type   | Check                                      | Automatic action                                       |
| ---------- | ------------------------------------------ | ------------------------------------------------------ |
| File URL   | Does the file still exist in Google Drive? | None — only reports the status                         |
| Folder URL | Is the document in the folder?             | Yes — replaces the folder URL with the direct file URL |
| Gmail URL  | Cannot be checked automatically            | None — flags for manual verification                   |

## Possible statuses

| Status         | Color     | Meaning                                         |
| -------------- | --------- | ----------------------------------------------- |
| OK             | 🟢 Green  | Link works, file is accessible                  |
| Updated        | 🔵 Blue   | Folder URL automatically replaced with file URL |
| File not found | 🔴 Red    | File no longer exists in Google Drive           |
| Not in folder  | 🔴 Red    | Document not found in the specified folder      |
| Gmail (manual) | 🟡 Yellow | Gmail link requires manual verification         |
| Error          | 🔴 Red    | An error occurred during validation             |

## When to use?

- After a large import of transactions
- Periodically (monthly or quarterly) as a maintenance task
- When you notice links in transactions no longer work
- Before generating the Aangifte IB XLSX export (which contains Google Drive links)

!!! tip
Run validation per year and per administration to keep it manageable. Checking all years at once can take a long time.
