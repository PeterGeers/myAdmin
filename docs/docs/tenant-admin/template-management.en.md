# Template Management

> Upload, edit, download, and delete report templates for your organization.

## Overview

Template management lets you control how invoices and reports look. Each template type has a **default template** (built into the system) and can optionally have a **tenant-specific template** that you upload yourself.

When you haven't uploaded your own template, the system automatically uses the default template.

!!! info
Template management is available on the **Templates** tab in Tenant Administration.

## Available template types

| Template type         | Description                     |
| --------------------- | ------------------------------- |
| STR Invoice (Dutch)   | Short-term rental invoice (NL)  |
| STR Invoice (English) | Short-term rental invoice (EN)  |
| BTW Aangifte          | VAT declaration report          |
| Aangifte IB           | Income tax declaration report   |
| Toeristenbelasting    | Tourist tax report              |
| Financial Report      | General financial report        |
| ZZP Invoice           | ZZP freelancer invoice template |

## Uploading a template

1. **Select the template type** from the dropdown menu
2. The system shows whether an active template already exists
3. **Choose an HTML file** (max 5 MB)
4. Optional: configure field mappings (JSON) via **Advanced: Field Mappings**
5. Click **Upload & Preview Template** to validate

!!! tip
Use the **Format JSON** button to neatly format your field mappings.

## Downloading the default template

When no tenant-specific template exists for the selected type, a yellow notice appears with the **Download Default Template** button.

1. **Select the template type** from the dropdown menu
2. You'll see the message: _"No active template found for this type"_
3. Click **Download Default Template**
4. The default template is downloaded as `{type}_default.html`

!!! tip
Use the default template as a starting point for your customizations. Download it, edit it in an HTML editor, then upload it as a tenant-specific template.

## Managing an existing template

When an active tenant-specific template exists, the system shows a blue information block with:

- **Version number** and approval information
- **Download** — Download the current template
- **Load & Modify** — Load the template into the upload form to edit and re-upload it
- **Delete Template** — Remove the tenant-specific template

### Downloading the template

Click **Download** to download the current active template as an HTML file.

### Editing a template

1. Click **Load & Modify**
2. The current template is loaded into the upload form
3. Edit the file in an external HTML editor
4. Upload the modified file via **Upload & Preview Template**

### Deleting a template

!!! warning
After deleting a tenant-specific template, the system falls back to the default template.

1. Click **Delete Template** (red button)
2. A confirmation dialog appears
3. Click **Delete** to confirm, or **Cancel** to abort
4. After successful deletion, the system shows a message that no active template exists

The template is not permanently deleted but deactivated. Template history is preserved.

## Validation and approval

After uploading a template, it goes through the following steps:

1. **Preview** — See how the template looks
2. **Validate** — Check for errors in the HTML structure
3. **Approve** — Activate the template for use

If there are validation errors, use **AI Help** for automatic suggestions.

## Troubleshooting

| Problem                                      | Cause                                     | Solution                                    |
| -------------------------------------------- | ----------------------------------------- | ------------------------------------------- |
| "Tenant admin access required"               | You don't have the Tenant_Admin role      | Contact your SysAdmin                       |
| "Invalid template type"                      | Invalid template type specified           | Select a valid type from the dropdown menu  |
| "No default template available"              | No default template available             | Contact the administrator                   |
| "No active tenant template found"            | No active template to delete              | Select a type that has an existing template |
| File is rejected                             | File is not HTML or exceeds 5 MB          | Use an .html or .htm file, max 5 MB         |
| Download Default Template button not visible | A tenant-specific template already exists | Delete the existing template first          |
