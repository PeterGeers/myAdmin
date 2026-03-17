# Bug Report: JaBaKi Logo Missing in STR Invoices

**Date**: 2026-02-16 21:22
**Status**: ✅ RESOLVED
**Reporter**: User
**Module**: STR Invoice Generator

## Issue Description

The Jabaki logo was not displaying in generated STR invoices after the Railway migration.

## Root Cause

The invoice templates are stored in tenant-specific Google Drive folders. The logo image URL was using a format that doesn't work for direct embedding in HTML:

- ❌ `https://drive.google.com/uc?export=view&id=FILE_ID` - Shows preview page, not raw image
- ❌ `/jabaki-logo.png` - Tried to load from backend, but templates are in Google Drive

## Solution

Updated the templates in Google Drive to use Google's CDN URL format:

```html
<img
  src="https://lh3.googleusercontent.com/d/1EJ1wo3qCWUzdUOoW5AYhZM1Fhz0vGJyW"
  alt="Jabaki Logo"
  class="logo"
/>
```

## Templates Updated

- **STR Invoice NL**: File ID `1uHuj9F1IeUMmfAvw4Dz-rLWC0Y-k6DIa`
- **STR Invoice EN**: File ID `1-4XGkuae6WhGBvD1KPLuZ9q24n1Miz5Q`

## Logo Details

- **Logo File ID**: `1EJ1wo3qCWUzdUOoW5AYhZM1Fhz0vGJyW`
- **CDN URL**: `https://lh3.googleusercontent.com/d/1EJ1wo3qCWUzdUOoW5AYhZM1Fhz0vGJyW`
- **Location**: Tenant's Google Drive Templates folder
- **Sharing**: Public (Anyone with link can view)

## Key Learnings

1. Templates are tenant-specific and stored in Google Drive
2. Each tenant can have their own logo
3. Use `https://lh3.googleusercontent.com/d/FILE_ID` format for embedding Google Drive images
4. Logo must be publicly shared for embedding to work

## Testing

- ✅ Logo displays correctly in STR invoices
- ✅ Template management function tested in tenant admin module

## Related Changes

- Removed `templates/` from `.dockerignore` (commit 5e0c7fa)
- Updated backend static route for logo serving (commit 2fc759e)
- Fixed frontend logo path for GitHub Pages (commit 5ce3278)
