# Year-End Configuration UI Integration Guide

Quick guide for integrating the Year-End Settings screen into your application.

## Adding to Navigation

### Option 1: Tenant Admin Menu

Add to your tenant admin navigation menu:

```typescript
// In your TenantAdmin navigation component
import YearEndSettings from "./components/TenantAdmin/YearEndSettings";

const menuItems = [
  { label: "Chart of Accounts", component: ChartOfAccounts },
  { label: "Year-End Settings", component: YearEndSettings }, // Add this
  { label: "Users", component: Users },
  // ... other items
];
```

### Option 2: Direct Route

Add as a route in your router:

```typescript
import YearEndSettings from './components/TenantAdmin/YearEndSettings';

<Route
  path="/tenant-admin/year-end-settings"
  element={<YearEndSettings tenant={currentTenant} />}
/>
```

## Required Props

The `YearEndSettings` component requires one prop:

```typescript
interface YearEndSettingsProps {
  tenant: string; // Current tenant administration name
}
```

## Usage Example

```typescript
import YearEndSettings from './components/TenantAdmin/YearEndSettings';

function TenantAdminPanel() {
  const currentTenant = 'GoodwinSolutions';

  return (
    <YearEndSettings tenant={currentTenant} />
  );
}
```

## Permissions

The component calls API endpoints that require:

- `tenant_admin` permission
- FIN module enabled for tenant

Ensure your authentication wrapper provides these permissions.

## API Client Configuration

The component uses `apiClient` from `services/apiClient`. Ensure your API client is configured with:

```typescript
// services/apiClient.ts
import axios from "axios";

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL || "http://localhost:5000",
  headers: {
    "Content-Type": "application/json",
  },
});

// Add auth interceptor
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("authToken");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default apiClient;
```

## Testing the Integration

### 1. Start Backend

```bash
cd backend
python src/app.py
```

### 2. Start Frontend

```bash
cd frontend
npm start
```

### 3. Navigate to Settings

Go to: `http://localhost:3000/tenant-admin/year-end-settings`

### 4. Configure Accounts

1. Select an account for each role
2. Click "Save Configuration"
3. Verify success message appears
4. Check Chart of Accounts to see role badges

## Troubleshooting

### "Error loading configuration"

**Cause**: Backend not running or API endpoint not accessible

**Solution**:

- Check backend is running on correct port
- Verify `REACT_APP_API_URL` environment variable
- Check browser console for CORS errors

### "FIN module not enabled"

**Cause**: Tenant doesn't have FIN module active

**Solution**:

```sql
UPDATE tenant_modules
SET is_active = 1
WHERE administration = 'YourTenant'
AND module_name = 'FIN';
```

### "Tenant admin access required"

**Cause**: User doesn't have tenant_admin permission

**Solution**: Ensure JWT token includes tenant_admin role for the current tenant

### Dropdowns are empty

**Cause**: No accounts in chart of accounts or wrong VW classification

**Solution**:

- Verify accounts exist: `SELECT * FROM rekeningschema WHERE administration = 'YourTenant'`
- Check VW values are 'Y' or 'N'
- Ensure at least one account with VW='N' and one with VW='Y'

## Styling Customization

The component uses Chakra UI with dark theme. To customize:

```typescript
// Wrap in custom theme provider
import { ChakraProvider, extendTheme } from '@chakra-ui/react';

const customTheme = extendTheme({
  colors: {
    // Your custom colors
  }
});

<ChakraProvider theme={customTheme}>
  <YearEndSettings tenant={tenant} />
</ChakraProvider>
```

## Related Components

- `ChartOfAccounts.tsx` - Shows role column
- `AccountModal.tsx` - Account editing (future: add role dropdown)
- `YearEndClosure.tsx` - Year closure wizard (Phase 2)

## Next Steps

After integrating the UI:

1. Run database migration: `python scripts/database/create_year_closure_tables.py`
2. Configure accounts for your tenant
3. Validate configuration is complete
4. Wait for Phase 2 to actually close years

## Support

For issues or questions:

- Check `.kiro/specs/FIN/Year end closure/` for detailed specs
- Review `backend/docs/guides/YEAR_END_CONFIGURATION.md` for configuration details
- See `PHASE1_UI_COMPLETE.md` for implementation details
