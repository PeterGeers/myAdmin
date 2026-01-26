# Authenticated API Usage Guide

This guide shows how to use the authenticated API service to make API calls with JWT tokens and tenant filtering.

## Overview

All API calls should now use the `authenticatedRequest` functions from `apiService.ts`. These functions automatically:

- Add JWT tokens to the Authorization header
- Handle token expiration and refresh
- Provide consistent error handling
- Support tenant filtering via X-Tenant header

## Tenant Filtering

Many API endpoints now require tenant filtering for multi-tenant data isolation. The system automatically handles tenant context, but you should be aware of the following:

### Tenant Header

Some endpoints require the `X-Tenant` header to specify which tenant's data to access:

```typescript
import { authenticatedGet } from "../services/apiService";

// Request with tenant context
const response = await authenticatedGet("/api/bnb/bnb-listing-data", {
  headers: {
    "X-Tenant": "PeterPrive",
  },
});
```

### Tenant Access Errors

Endpoints with tenant filtering may return 403 errors if you try to access unauthorized tenant data:

```typescript
try {
  const response = await authenticatedGet("/api/bnb/bnb-listing-data");

  if (response.status === 403) {
    const error = await response.json();
    console.error("Tenant access denied:", error.error);
    // Handle tenant access error - show user-friendly message
    showError("You do not have access to this data");
    return;
  }

  const data = await response.json();
  // Process data
} catch (error) {
  console.error("Request failed:", error);
}
```

### Multi-Tenant Users

Users with access to multiple tenants will see combined data from all their accessible tenants. The API automatically filters data based on the user's tenant permissions.

## Basic Usage

### GET Requests

```typescript
import { authenticatedGet } from "../services/apiService";

// Simple GET request
const response = await authenticatedGet("/api/invoices");
const data = await response.json();

// GET with query parameters
const params = new URLSearchParams({
  year: "2024",
  quarter: "1",
});
const response = await authenticatedGet(`/api/reports/btw?${params}`);
const data = await response.json();
```

### POST Requests

```typescript
import { authenticatedPost } from "../services/apiService";

// POST with JSON body
const response = await authenticatedPost("/api/invoices", {
  amount: 100,
  description: "Test invoice",
});
const data = await response.json();
```

### PUT Requests

```typescript
import { authenticatedPut } from "../services/apiService";

// Update resource
const response = await authenticatedPut("/api/invoices/123", {
  amount: 150,
  description: "Updated invoice",
});
const data = await response.json();
```

### DELETE Requests

```typescript
import { authenticatedDelete } from "../services/apiService";

// Delete resource
const response = await authenticatedDelete("/api/invoices/123");
```

### File Uploads (FormData)

```typescript
import { authenticatedFormData } from "../services/apiService";

// Upload file
const formData = new FormData();
formData.append("file", file);
formData.append("description", "My file");

const response = await authenticatedFormData("/api/upload", formData);
const data = await response.json();
```

## Public Endpoints

Some endpoints don't require authentication (like `/api/status`). For these, use the `skipAuth` option:

```typescript
import { authenticatedGet } from "../services/apiService";

const response = await authenticatedGet("/api/status", { skipAuth: true });
const data = await response.json();
```

## Error Handling

The service automatically handles common errors including tenant access violations:

```typescript
import { authenticatedGet } from "../services/apiService";

try {
  const response = await authenticatedGet("/api/bnb/bnb-listing-data");

  if (!response.ok) {
    // Handle HTTP errors
    const error = await response.json();

    if (response.status === 403) {
      // Tenant access denied
      console.error("Tenant access error:", error.error);
      showUserMessage("You do not have permission to access this data");
      return;
    }

    console.error("API error:", error);
    return;
  }

  const data = await response.json();
  // Process data
} catch (error) {
  // Handle network errors or authentication failures
  console.error("Request failed:", error);

  if (error.message === "Authentication required") {
    // Redirect to login
    window.location.href = "/login";
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
const response = await fetch("/api/invoices");
const data = await response.json();
```

### After (New Way)

```typescript
// ✅ New way - with authentication
import { authenticatedGet } from "../services/apiService";

const response = await authenticatedGet("/api/invoices");
const data = await response.json();
```

### Before (Old Way with FormData)

```typescript
// ❌ Old way - no authentication
const formData = new FormData();
formData.append("file", file);

const response = await fetch("/api/upload", {
  method: "POST",
  body: formData,
});
```

### After (New Way with FormData)

```typescript
// ✅ New way - with authentication
import { authenticatedFormData } from "../services/apiService";

const formData = new FormData();
formData.append("file", file);

const response = await authenticatedFormData("/api/upload", formData);
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

## BNB and STR Endpoints

The BNB (Bed & Breakfast) and STR (Short-Term Rental) endpoints have specific tenant filtering requirements:

### BNB Reporting Endpoints

All BNB endpoints automatically filter data based on the user's accessible tenants:

```typescript
import { authenticatedGet } from "../services/apiService";

// Get BNB listing data - automatically filtered by user's tenants
const response = await authenticatedGet("/api/bnb/bnb-listing-data", {
  params: {
    year: "2024",
    listing: "Child Friendly",
  },
});

const data = await response.json();
// data.data contains only listings from user's accessible tenants
```

### STR Transaction Endpoints

STR endpoints validate tenant access for write operations:

```typescript
import { authenticatedPost } from "../services/apiService";

// Save STR transactions - validates all transactions belong to accessible tenants
const response = await authenticatedPost("/api/str-channel/save", {
  transactions: [
    {
      Administration: "PeterPrive", // Must be in user's accessible tenants
      TransactionDate: "2024-06-15",
      Amount: 750.0,
      Description: "Airbnb booking payment",
    },
  ],
});

if (response.status === 403) {
  const error = await response.json();
  console.error("Tenant validation failed:", error.error);
  // Handle unauthorized tenant access
}
```

### Available BNB Endpoints

- `/api/bnb/bnb-listing-data` - Listing performance data
- `/api/bnb/bnb-channel-data` - Channel performance data
- `/api/bnb/bnb-table` - Table view data
- `/api/bnb/bnb-guest-bookings` - Guest booking data
- `/api/bnb/bnb-actuals` - Actual vs planned data
- `/api/bnb/bnb-filter-options` - Available filter options
- `/api/bnb/bnb-violin-data` - Violin plot data
- `/api/bnb/bnb-returning-guests` - Returning guests analysis

### Available STR Endpoints

- `/api/str-channel/save` - Save channel transactions
- `/api/str-invoice/generate-invoice` - Generate invoices
- `/api/str-invoice/upload-template` - Upload invoice templates

## Best Practices

1. **Always handle 403 errors** for tenant-filtered endpoints
2. **Show user-friendly messages** for tenant access violations
3. **Don't expose tenant names** in error messages to users
4. **Use consistent error handling** across all components
5. **Test with multiple tenant scenarios** during development

## Complete Example

Here's a complete example of a component using tenant-filtered BNB data:

```typescript
import React, { useState, useEffect } from 'react';
import { authenticatedGet } from '../services/apiService';

function BNBListingReport() {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadListings();
  }, []);

  const loadListings = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await authenticatedGet('/api/bnb/bnb-listing-data');

      if (response.status === 403) {
        setError('You do not have permission to view this data');
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to load listing data');
      }

      const data = await response.json();
      setListings(data.data);
    } catch (err) {
      setError('Failed to load data. Please try again.');
      console.error('Failed to load listings:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div>
      <h1>BNB Listings</h1>
      <table>
        <thead>
          <tr>
            <th>Listing</th>
            <th>Channel</th>
            <th>Revenue</th>
            <th>Administration</th>
          </tr>
        </thead>
        <tbody>
          {listings.map((listing, index) => (
            <tr key={index}>
              <td>{listing.listing}</td>
              <td>{listing.channel}</td>
              <td>€{listing.revenue}</td>
              <td>{listing.administration}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default BNBListingReport;
```

## Testing

When testing components that use authenticated API calls, you can mock the service:

```typescript
import { authenticatedGet } from "../services/apiService";

jest.mock("../services/apiService");

test("loads invoices", async () => {
  const mockResponse = {
    ok: true,
    json: async () => ({ invoices: [{ id: 1, description: "Test" }] }),
  };

  (authenticatedGet as jest.Mock).mockResolvedValue(mockResponse);

  // Test your component
});
```
