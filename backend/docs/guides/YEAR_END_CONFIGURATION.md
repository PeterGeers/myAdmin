# Year-End Closure Configuration Guide

This guide explains how to configure accounts for the year-end closure feature.

## Overview

Year-end closure requires three account roles to be configured per tenant:

1. **Equity Result Account** - Where net P&L result is recorded
2. **P&L Closing Account** - Used in year-end closure transaction
3. **Interim Opening Balance Account** - Balancing account for opening balances

## Account Role Requirements

### 1. Equity Result Account

- **Role**: `equity_result`
- **Purpose**: Records the net profit or loss for the year
- **VW Classification**: Must be 'N' (Balance Sheet)
- **Example**: Account 3080 (Equity)
- **Usage**: Receives credit for profit, debit for loss

### 2. P&L Closing Account

- **Role**: `pl_closing`
- **Purpose**: Used to close P&L accounts to equity
- **VW Classification**: Must be 'Y' (P&L)
- **Example**: Account 8099 (P&L Closing)
- **Usage**: Receives debit for profit, credit for loss

### 3. Interim Opening Balance Account

- **Role**: `interim_opening_balance`
- **Purpose**: Balancing account for opening balance transactions
- **VW Classification**: Must be 'N' (Balance Sheet)
- **Example**: Account 2001 (Interim Account)
- **Usage**: Balances all opening balance entries

## Configuration Methods

### Method 1: Using Python Script

```python
from services.year_end_config import YearEndConfigService

# Initialize service
config = YearEndConfigService()

# Set account roles
config.set_account_role('GoodwinSolutions', '3080', 'equity_result')
config.set_account_role('GoodwinSolutions', '8099', 'pl_closing')
config.set_account_role('GoodwinSolutions', '2001', 'interim_opening_balance')

# Validate configuration
validation = config.validate_configuration('GoodwinSolutions')
if validation['valid']:
    print("✅ Configuration is valid")
else:
    print("❌ Configuration errors:")
    for error in validation['errors']:
        print(f"  - {error}")
```

### Method 2: Direct SQL

```sql
-- Set equity result account
UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.role', 'equity_result')
WHERE administration = 'GoodwinSolutions'
AND Reknum = '3080';

-- Set P&L closing account
UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.role', 'pl_closing')
WHERE administration = 'GoodwinSolutions'
AND Reknum = '8099';

-- Set interim opening balance account
UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.role', 'interim_opening_balance')
WHERE administration = 'GoodwinSolutions'
AND Reknum = '2001';
```

### Method 3: Using API (Future)

Once the API endpoints are implemented:

```bash
# Set equity result account
curl -X POST /api/tenant-admin/year-end-config/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "role": "equity_result",
    "account_code": "3080"
  }'
```

## Validation

### Check Configuration Status

```python
from services.year_end_config import YearEndConfigService

config = YearEndConfigService()
validation = config.validate_configuration('GoodwinSolutions')

print(f"Valid: {validation['valid']}")
print(f"Errors: {validation['errors']}")
print(f"Configured roles: {validation['configured_roles']}")
```

### Validation Rules

The system validates:

1. **All required roles are configured** - Must have all 3 roles
2. **Correct VW classification** - Each role must use correct account type
3. **No duplicate roles** - Each role assigned to only one account
4. **Accounts exist** - All configured accounts must exist in chart of accounts

### Common Validation Errors

**Missing required role**:
```
Missing required role 'equity_result': Equity result account (where net P&L is recorded) (example: 3080)
```
**Solution**: Assign the missing role to an appropriate account

**Wrong VW classification**:
```
Account 3080 for role 'pl_closing' has VW='N' but should be VW='Y'
```
**Solution**: Use an account with the correct VW classification

**Role already assigned**:
```
Role 'equity_result' is already assigned to account 3080. Remove it first or use update_account_role().
```
**Solution**: Remove the existing role assignment first

## Viewing Configuration

### Get All Configured Roles

```python
config = YearEndConfigService()
roles = config.get_all_configured_roles('GoodwinSolutions')

for role, info in roles.items():
    print(f"{role}: {info['account_code']} - {info['account_name']}")
```

### Get Specific Role

```python
config = YearEndConfigService()
account = config.get_account_by_role('GoodwinSolutions', 'equity_result')

if account:
    print(f"Equity result account: {account['Reknum']} - {account['AccountName']}")
else:
    print("Equity result account not configured")
```

### Get Available Accounts

```python
config = YearEndConfigService()

# Get all balance sheet accounts (for equity_result and interim_opening_balance)
bs_accounts = config.get_available_accounts('GoodwinSolutions', vw_filter='N')

# Get all P&L accounts (for pl_closing)
pl_accounts = config.get_available_accounts('GoodwinSolutions', vw_filter='Y')
```

## Modifying Configuration

### Change Account Role

```python
config = YearEndConfigService()

# Remove old role
config.remove_account_role('GoodwinSolutions', '3080')

# Assign to new account
config.set_account_role('GoodwinSolutions', '3090', 'equity_result')
```

### Remove Account Role

```python
config = YearEndConfigService()
config.remove_account_role('GoodwinSolutions', '3080')
```

## Database Schema

### parameters Column Structure

The `parameters` column in `rekeningschema` stores JSON data:

```json
{
  "role": "equity_result"
}
```

### Example Query

```sql
-- Find all accounts with roles
SELECT 
    Reknum,
    AccountName,
    VW,
    JSON_EXTRACT(parameters, '$.role') as role
FROM rekeningschema
WHERE administration = 'GoodwinSolutions'
AND JSON_EXTRACT(parameters, '$.role') IS NOT NULL;
```

## Troubleshooting

### Issue: Cannot set role

**Error**: `Account 3080 not found for administration GoodwinSolutions`

**Solution**: Verify the account exists in the chart of accounts:
```sql
SELECT * FROM rekeningschema 
WHERE administration = 'GoodwinSolutions' 
AND Reknum = '3080';
```

### Issue: Wrong VW classification

**Error**: `Account 3080 has VW='Y' but role 'equity_result' requires VW='N'`

**Solution**: Use an account with the correct VW classification. Equity and interim accounts must be balance sheet (VW='N'), P&L closing must be P&L account (VW='Y').

### Issue: Role already assigned

**Error**: `Role 'equity_result' is already assigned to account 3080`

**Solution**: Remove the existing assignment first:
```python
config.remove_account_role('GoodwinSolutions', '3080')
```

## Best Practices

1. **Configure before closing years** - Set up roles before attempting year-end closure
2. **Use standard accounts** - Follow accounting conventions for account selection
3. **Document choices** - Record why specific accounts were chosen
4. **Test in test mode** - Validate configuration in test database first
5. **Validate regularly** - Check configuration status periodically

## Example: Complete Setup

```python
from services.year_end_config import YearEndConfigService

# Initialize
config = YearEndConfigService()
admin = 'GoodwinSolutions'

# Configure all roles
config.set_account_role(admin, '3080', 'equity_result')
config.set_account_role(admin, '8099', 'pl_closing')
config.set_account_role(admin, '2001', 'interim_opening_balance')

# Validate
validation = config.validate_configuration(admin)

if validation['valid']:
    print("✅ Year-end closure configuration complete!")
    print("\nConfigured accounts:")
    for role, info in validation['configured_roles'].items():
        print(f"  {role}: {info['account_code']} - {info['account_name']}")
else:
    print("❌ Configuration incomplete:")
    for error in validation['errors']:
        print(f"  - {error}")
```

## Related Documentation

- [Year-End Closure Design](.kiro/specs/FIN/Year end closure/design-closure.md)
- [Year-End Closure Requirements](.kiro/specs/FIN/Year end closure/requirements.md)
- [FIN Module Overview](.kiro/specs/FIN/README.md)
