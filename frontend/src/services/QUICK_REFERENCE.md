# Authenticated API Quick Reference

## Import

```typescript
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedDelete,
  authenticatedFormData,
} from "../services/apiService";
```

## GET Request

```typescript
const response = await authenticatedGet("/api/invoices");
const data = await response.json();
```

## POST Request

```typescript
const response = await authenticatedPost("/api/invoices", {
  amount: 100,
  description: "Invoice",
});
const data = await response.json();
```

## PUT Request

```typescript
const response = await authenticatedPut("/api/invoices/123", {
  amount: 150,
});
const data = await response.json();
```

## DELETE Request

```typescript
const response = await authenticatedDelete("/api/invoices/123");
```

## File Upload

```typescript
const formData = new FormData();
formData.append("file", file);

const response = await authenticatedFormData("/api/upload", formData);
const data = await response.json();
```

## Public Endpoint (No Auth)

```typescript
const response = await authenticatedGet("/api/status", { skipAuth: true });
const data = await response.json();
```

## With Query Parameters

```typescript
const params = new URLSearchParams({ year: "2024", quarter: "1" });
const response = await authenticatedGet(`/api/reports/btw?${params}`);
const data = await response.json();
```

## Error Handling

```typescript
try {
  const response = await authenticatedGet("/api/invoices");

  if (!response.ok) {
    const error = await response.json();
    console.error("API error:", error);
    return;
  }

  const data = await response.json();
  // Process data
} catch (error) {
  console.error("Request failed:", error);

  if (error.message === "Authentication required") {
    // Redirect to login
    window.location.href = "/login";
  }
}
```

## Features

✅ Automatic JWT token injection  
✅ Token refresh on expiration  
✅ Consistent error handling  
✅ FormData support for uploads  
✅ Public endpoint support

See **API_USAGE_GUIDE.md** for complete documentation.
