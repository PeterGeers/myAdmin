# Design — [Feature Name]

## Architecture Overview

[High-level description of how this feature fits into the system. Include data flow if helpful.]

## API Endpoints

### [Endpoint Name]

- **URL**: `/api/[module]/[action]`
- **Method**: GET | POST | PUT | DELETE
- **Auth**: `@cognito_required(required_permissions=['[module]_[action]'])` + `@tenant_required()`

**Request:**

```json
{
  "field": "value"
}
```

**Response (success):**

```json
{
  "success": true,
  "data": {}
}
```

**Response (error):**

```json
{
  "success": false,
  "error": "Description"
}
```

## Database Changes

### New Tables

```sql
CREATE TABLE [table_name] (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    -- [columns]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tenant (tenant_id)
);
```

### Modified Tables

- [Table]: [What changes and why]

## Backend Implementation

- **Route**: `backend/src/routes/[module]_routes.py`
- **Service**: `backend/src/services/[module]_service.py`
- **Pattern**: Blueprint + service layer, tenant-scoped queries

## Frontend Implementation

- **Page**: `frontend/src/pages/[PageName].tsx`
- **Components**: `frontend/src/components/[ComponentName].tsx`
- **Service**: `frontend/src/services/[module]Service.ts`

## Security Considerations

- [Auth requirements]
- [Tenant isolation approach]
- [Input validation]

## Error Handling

- [Expected error scenarios and how they're handled]

## Key Decisions

| Decision   | Options Considered | Chosen | Rationale |
| ---------- | ------------------ | ------ | --------- |
| [Decision] | [A, B, C]          | [B]    | [Why]     |
