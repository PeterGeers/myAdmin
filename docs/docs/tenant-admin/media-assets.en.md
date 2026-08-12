# Media Asset Management

> Manage all files (images, PDFs, videos) stored in S3 for your organization.

## Overview

The Media Assets feature gives you full visibility and control over all files stored in the cloud (S3) for your tenant. You can:

- View a summary of all stored assets
- Run a reconciliation scan to detect inconsistencies
- Approve orphaned files for deletion
- Import or delete unregistered S3 objects
- Configure retention periods per category
- Detect and merge duplicate files

## What you need

- `Tenant_Admin` role
- A selected tenant/administration

## The tabs

Media Asset Management is accessible via **Tenant Administration** → **Media Assets** and contains the following tabs:

| Tab          | Function                                               |
| ------------ | ------------------------------------------------------ |
| Dashboard    | Overview of counts, storage by category                |
| Scan         | Start a reconciliation scan and view results           |
| Deletion     | Approve deletion-eligible assets for permanent removal |
| Unregistered | S3 objects not tracked in the registry                 |
| Retention    | Configure retention periods per category               |
| Duplicates   | Detect and merge duplicate files                       |
| Storage      | Storage overview by category and orphaned assets       |

## Step by step

### Running a scan

1. Go to **Media Assets** → **Scan**
2. Click **Start Scan**
3. The scan automatically progresses through these phases:
   - Scanning S3 buckets
   - Comparing with the registry
   - Verifying references
   - Transitioning eligible assets
4. After completion you'll see the results:

| Result           | Meaning                                           |
| ---------------- | ------------------------------------------------- |
| Consistent       | Assets that are correctly registered              |
| Unregistered     | S3 objects without a registry entry               |
| Missing          | Registry entries for which the S3 file is missing |
| Stale References | References to entities that no longer exist       |
| Newly Eligible   | Assets that just passed their retention period    |

### Importing unregistered objects

1. Go to **Media Assets** → **Unregistered**
2. You'll see a list of S3 objects not in the registry
3. Select the objects you want to import (checkboxes)
4. Click **Import to Registry**
5. The objects are added to the asset registry with status ACTIVE

!!! tip "Tip"
After importing, run a scan to verify everything is consistent.

### Deleting unregistered objects

1. Select the objects you want to remove
2. Click **Delete from S3**
3. Confirm in the dialog

!!! warning "Warning"
Deletion from S3 is permanent and cannot be undone.

### Approving deletion-eligible assets

1. Go to **Media Assets** → **Deletion**
2. You'll see assets that are orphaned and past their retention period
3. Select the assets you want to delete
4. Click **Approve Deletion**
5. Confirm in the dialog

!!! warning "Compliance"
For invoice-related assets, an extra warning is shown. Verify that the legal retention period (7 years) has elapsed.

### Adjusting retention periods

1. Go to **Media Assets** → **Retention**
2. You'll see the current setting per category and its source (system default or tenant override)
3. Adjust the value in the input field
4. Click **Save Changes**

Default retention periods:

| Category      | Default (days) | Notes                        |
| ------------- | -------------- | ---------------------------- |
| Invoices      | 2555 (7 years) | Legal retention requirement  |
| Branding      | 30             | Logos and brand assets       |
| Templates     | 90             | Invoice and report templates |
| Landing Pages | 7              | Published web pages          |

### Merging duplicates

1. Go to **Media Assets** → **Duplicates**
2. You'll see groups of files with identical content (same hash)
3. Select which file to keep per group (defaults to the one with the most references)
4. Click **Merge**
5. References are transferred to the kept file, duplicates are deleted

## FAQ

**What is an "orphaned" asset?**
An asset that is no longer referenced by any invoice, landing page, or other entity. It exists in S3 but isn't used anywhere.

**Are files automatically deleted?**
No. The system detects and marks assets as deletion-eligible, but the tenant admin must explicitly approve every deletion.

**What if I accidentally delete something?**
Deletion from S3 is permanent. Make sure you select the correct assets. When in doubt: import them into the registry first and attach them to the correct entity.

## Troubleshooting

| Problem                       | Solution                                                    |
| ----------------------------- | ----------------------------------------------------------- |
| Scan shows no results         | Verify that assets exist in S3 for your tenant              |
| "Connection lost" during scan | Reload the page and try again                               |
| Import failed                 | Check that the file is a supported type (image, PDF, video) |
| Retention save failed         | Value must be a positive number                             |
