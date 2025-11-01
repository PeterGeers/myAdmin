# API URL Policy

## CRITICAL: Always Use Relative URLs

**DO NOT use hardcoded localhost URLs like `http://localhost:5000/api/...`**

**ALWAYS use relative URLs like `/api/...`**

## Why?

- In development: React proxy forwards `/api/*` to Flask server
- In production: React app served by Flask, relative URLs go to same server
- Hardcoded localhost URLs break production deployment

## Examples

❌ **WRONG:**
```javascript
fetch('http://localhost:5000/api/reports/data')
```

✅ **CORRECT:**
```javascript
fetch('/api/reports/data')
```

## For Amazon Q Users

When Amazon Q suggests fixes, **NEVER** accept changes that convert relative URLs to hardcoded localhost URLs. Always keep the relative URL format.

Look for these comment guards in the code:
```javascript
// IMPORTANT: Always use relative URLs - DO NOT change to localhost
```