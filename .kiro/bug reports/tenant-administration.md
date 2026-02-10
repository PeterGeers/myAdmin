### 4.2.5 TenantSettings Component

This is a summary what is needed

1. Tenant details
The tenant administrator should be able to edit/update its own tenant details that are not protected
  - display_name
  - Contact email
  - Phone number
  - Address (Street, City, Zipcode and Country)
  - Bank details (must be added to the tenant trable)


2. Feature toggling  (Do we need a requirements, design and tasks)
- Create `FeatureToggles.tsx` component
  - Feature list with toggles
  - Feature descriptions
  - Confirmation for disabling

3. Activity Dashboard (Do we need a requirements, design and tasks)
- Create `ActivityDashboard.tsx` component
  - Display activity metrics
  - Display charts (Recharts)
  - Date range selector
  - Export button


. Feature Toggles (Needs requirements/design)
Questions to clarify:

What features can be toggled? (e.g., AI invoice extraction, STR pricing optimizer, etc.)
Where are feature flags stored? (tenant_config table or tenant_modules table?)
Who decides which features are available? (SysAdmin sets available features, TenantAdmin enables/disables?)
Are features tied to pricing/subscription tiers?
Recommendation: Create a small spec for this (requirements + design)

3. Activity Dashboard (Needs requirements/design)
Questions to clarify:

What activities to track? (user logins, API calls, data changes, report generations?)
Data source? (audit_log table?)
What metrics to display? (daily active users, API usage, storage usage?)
What charts? (line charts for trends, bar charts for comparisons?)
Export format? (CSV, PDF, Excel?)
Recommendation: Create a small spec for this (requirements + design)

My suggestion:

Start with Tenant Details (clear scope, can implement now)
Create mini-specs for Feature Toggles and Activity Dashboard (clarify requirements first)