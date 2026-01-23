# Authenticated API Usage Guide

This guide shows how to use the authenticated API service to make API calls with JWT tokens.

## Overview

All API calls should now use the `authenticatedRequest` functions from `apiService.ts`. These functions automatically:
- Add JWT tokens to the Authorization header
- Handle token expiration and refresh
- Provide consistent error handling

## Basic Usage

### GET Requests

```typescript
import { authenticatedGet } from '../services/apiService';

// Simple GET request
const response = await authenticatedGet('/api/invoices');
const data = await response.json();

// GET with query parameters
const params = new URLSearchParams({
  year: '2024',
  quarter: '1'
});
const response = await authenticatedGet(`/api/reports/btw?${params}`);
const data = await response.json();
```

### POST Requests

```typescript
import { authenticatedPost } from '../services/apiService';

// POST with JSON body
const response = await authenticatedPost('/api/invoices', {
  amount: 100,
  description: 'Test invoice'
});
const data = await response.json();
```

### PUT Requests

```typescript
import { authenticatedPut } from '../services/apiService';

// Update resource
const response = await authenticatedPut('/api/invoices/123', {
  amount: 150,
  description: 'Updated invoice'
});
const data = await response.json();
```

### DELETE Requests

```typescript
import { authenticatedDelete } from '../services/apiService';

// Delete resource
const response = await authenticatedDelete('/api/invoices/123');
```

### File Uploads (FormData)

```typescript
import { authenticatedFormData } from '../services/apiService';

// Upload file
const formData = new FormData();
formData.append('file', file);
formData.append('description', 'My file');

const response = await authenticatedFormData('/api/upload', formData);
const data = await response.json();
```

## Public Endpoints

Some endpoints don't require authentication (like `/api/status`). For these, use the `skipAuth` option:

```typescript
import { authenticatedGet } from '../services/apiService';

const response = await authenticatedGet('/api/status', { skipAuth: true });
const data = await response.json();
```

## Error Handling

The service automatically handles common errors:

```typescript
import { authenticatedGet } from '../services/apiService';

try {
  const response = await authenticatedGet('/api/invoices');
  
  if (!response.ok) {
    // Handle HTTP errors
    const error = await response.json();
    console.error('API error:', error);
    return;
  }
  
  const data = await response.json();
  // Process data
} catch (error) {
  // Handle network errors or authentication failures
  console.error('Request failed:', error);
  
  if (error.message === 'Authentication required') {
    // Redirect to login
    window.location.href = '/login';
  }
}
```

## Token Refresh

The service automatically attempts to refresh expired tokens:

1. If a request returns 401 Unauthorized
2. The service fetches fresh tokens from Amplify
3. The request is retried with the new token
4. If refresh fails, an error is thrown

## Migration Guide

### Before (Old Way)

```typescript
// ❌ Old way - no authentication
const response = await fetch('/api/invoices');
const data = await response.json();
```

### After (New Way)

```typescript
// ✅ New way - with authentication
import { authenticatedGet } from '../services/apiService';

const response = await authenticatedGet('/api/invoices');
const data = await response.json();
```

### Before (Old Way with FormData)

```typescript
// ❌ Old way - no authentication
const formData = new FormData();
formData.append('file', file);

const response = await fetch('/api/upload', {
  method: 'POST',
  body: formData
});
```

### After (New Way with FormData)

```typescript
// ✅ New way - with authentication
import { authenticatedFormData } from '../services/apiService';

const formData = new FormData();
formData.append('file', file);

const response = await authenticatedFormData('/api/upload', formData);
```

## Complete Example

Here's a complete example of a component using authenticated API calls:

```typescript
import React, { useState, useEffect } from 'react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';

function InvoiceList() {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadInvoices();
  }, []);

  const loadInvoices = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await authenticatedGet('/api/invoices');
      
      if (!response.ok) {
        throw new Error('Failed to load invoices');
      }
      
      const data = await response.json();
      setInvoices(data.invoices);
    } catch (err) {
      setError(err.message);
      console.error('Failed to load invoices:', err);
    } finally {
      setLoading(false);
    }
  };

  const createInvoice = async (invoiceData) => {
    try {
      const response = await authenticatedPost('/api/invoices', invoiceData);
      
      if (!response.ok) {
        throw new Error('Failed to create invoice');
      }
      
      const data = await response.json();
      setInvoices([...invoices, data.invoice]);
    } catch (err) {
      setError(err.message);
      console.error('Failed to create invoice:', err);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h1>Invoices</h1>
      <ul>
        {invoices.map(invoice => (
          <li key={invoice.id}>{invoice.description}</li>
        ))}
      </ul>
    </div>
  );
}

export default InvoiceList;
```

## Best Practices

1. **Always use authenticated functions** for protected endpoints
2. **Handle errors gracefully** - show user-friendly messages
3. **Use skipAuth** only for truly public endpoints
4. **Don't store tokens manually** - let the service handle it
5. **Check response.ok** before parsing JSON
6. **Provide loading states** for better UX

## Testing

When testing components that use authenticated API calls, you can mock the service:

```typescript
import { authenticatedGet } from '../services/apiService';

jest.mock('../services/apiService');

test('loads invoices', async () => {
  const mockResponse = {
    ok: true,
    json: async () => ({ invoices: [{ id: 1, description: 'Test' }] })
  };
  
  (authenticatedGet as jest.Mock).mockResolvedValue(mockResponse);
  
  // Test your component
});
```
