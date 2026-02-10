# Feature Toggling - Requirements

**Status**: Draft
**Created**: February 10, 2026
**Last Updated**: February 10, 2026

---

## Executive Summary

Implement a granular feature toggle system that allows System Administrators to define toggleable features per module, and Tenant Administrators to enable/disable these features for their users. This provides fine-grained control beyond module-level access, enabling progressive rollout, A/B testing, and customized feature sets per tenant.

---

## Problem Statement

### Current Situation

- **Module-level control only**: Tenants can enable/disable entire modules (FIN, STR, TENADMIN)
- **All-or-nothing access**: When a module is enabled, all features within it are available
- **No progressive rollout**: Cannot gradually introduce new features to specific tenants
- **No feature customization**: Cannot tailor feature sets to different tenant needs
- **No A/B testing capability**: Cannot test new features with subset of tenants

### Business Impact

- **Limited flexibility**: Cannot offer different pricing tiers based on feature access
- **Risk in deployments**: New features must be released to all tenants simultaneously
- **Support burden**: Cannot disable problematic features for specific tenants
- **Competitive disadvantage**: Cannot offer customized solutions per tenant

---

## Goals and Objectives

### Primary Goals

1. **Granular Control**: Enable feature-level toggles within each module
2. **Two-tier Management**: SysAdmin defines features, TenantAdmin enables them
3. **Backward Compatibility**: Existing module system continues to work
4. **Performance**: Minimal impact on application performance
5. **User Experience**: Clear UI for managing feature toggles

### Success Criteria

- ✅ SysAdmin can define and manage feature toggles per module
- ✅ TenantAdmin can enable/disable features for their tenant
- ✅ Features are hidden/disabled in UI when toggled off
- ✅ API endpoints respect feature toggle state
- ✅ No breaking changes to existing module system
- ✅ Feature toggle checks add < 5ms to request processing
- ✅ Clear audit trail of feature toggle changes

---

## User Stories

### US-1: SysAdmin Defines Feature Toggles

**As a** System Administrator  
**I want to** define which features within each module can be toggled  
**So that** I can control feature availability across all tenants

**Acceptance Criteria**:

- [ ] Can create new feature toggle definitions
- [ ] Can specify module (FIN, STR, TENADMIN)
- [ ] Can provide feature key (unique identifier)
- [ ] Can provide display name and description
- [ ] Can set default state (enabled/disabled)
- [ ] Can mark features as beta/experimental
- [ ] Can set feature dependencies (requires other features)
- [ ] Can view list of all defined features
- [ ] Can edit feature definitions
- [ ] Can deprecate features (soft delete)

### US-2: SysAdmin Sets Global Feature State

**As a** System Administrator  
**I want to** enable or disable features globally  
**So that** I can control rollout across all tenants

**Acceptance Criteria**:

- [ ] Can enable feature for all tenants
- [ ] Can disable feature for all tenants
- [ ] Can enable feature for specific tenants (whitelist)
- [ ] Can disable feature for specific tenants (blacklist)
- [ ] Can see which tenants have feature enabled
- [ ] Can override tenant-level settings
- [ ] Changes take effect immediately

### US-3: TenantAdmin Views Available Features

**As a** Tenant Administrator  
**I want to** see which features are available for my tenant  
**So that** I can understand what functionality I can enable

**Acceptance Criteria**:

- [ ] Can view features grouped by module
- [ ] Can see feature descriptions
- [ ] Can see which features are enabled/disabled
- [ ] Can see which features are locked by SysAdmin
- [ ] Can see beta/experimental badges
- [ ] Can see feature dependencies
- [ ] Can filter by module
- [ ] Can search features by name

### US-4: TenantAdmin Toggles Features

**As a** Tenant Administrator  
**I want to** enable or disable features for my users  
**So that** I can customize the application to my needs

**Acceptance Criteria**:

- [ ] Can toggle features on/off (if not locked by SysAdmin)
- [ ] See confirmation dialog before disabling
- [ ] See warning if feature has dependencies
- [ ] Changes take effect immediately for all users
- [ ] Can see audit log of toggle changes
- [ ] Cannot enable features if module is disabled
- [ ] Cannot enable features if dependencies not met

### US-5: End User Sees Only Enabled Features

**As an** End User  
**I want to** see only features that are enabled for my tenant  
**So that** I'm not confused by unavailable functionality

**Acceptance Criteria**:

- [ ] Disabled features are hidden from UI
- [ ] Disabled features return 403 from API
- [ ] No broken UI elements from hidden features
- [ ] Clear error message if accessing disabled feature
- [ ] Navigation menus reflect enabled features
- [ ] Dashboard widgets respect feature toggles

---

## Functional Requirements

### FR-1: Feature Toggle Data Model

**Priority**: High

**Description**: Database schema to store feature toggle definitions and states

**Requirements**:

- Feature definitions table (system-wide)
  - `feature_key` (unique identifier, e.g., "fin_import_banking_str_revenue")
  - `module` (FIN, STR, TENADMIN)
  - `display_name` (human-readable name)
  - `description` (detailed explanation)
  - `default_enabled` (boolean)
  - `is_beta` (boolean)
  - `depends_on` (JSON array of feature keys)
  - `created_at`, `updated_at`
  - `deprecated_at` (nullable)
- Tenant feature states table (per-tenant overrides)
  - `administration` (tenant identifier)
  - `feature_key` (foreign key)
  - `enabled` (boolean)
  - `locked_by_sysadmin` (boolean)
  - `updated_by` (user email)
  - `updated_at`
- Audit log for feature toggle changes

### FR-2: SysAdmin Feature Management API

**Priority**: High

**Description**: API endpoints for SysAdmin to manage feature definitions

**Endpoints**:

- `GET /api/sysadmin/features` - List all feature definitions
- `POST /api/sysadmin/features` - Create new feature definition
- `PUT /api/sysadmin/features/{feature_key}` - Update feature definition
- `DELETE /api/sysadmin/features/{feature_key}` - Deprecate feature
- `GET /api/sysadmin/features/{feature_key}/tenants` - List tenant states
- `PUT /api/sysadmin/features/{feature_key}/global` - Set global state
- `PUT /api/sysadmin/features/{feature_key}/tenants/{tenant}` - Override tenant state

**Authorization**: Requires `SysAdmin` role

### FR-3: TenantAdmin Feature Management API

**Priority**: High

**Description**: API endpoints for TenantAdmin to manage tenant features

**Endpoints**:

- `GET /api/tenant-admin/features` - List available features for tenant
- `PUT /api/tenant-admin/features/{feature_key}` - Toggle feature for tenant
- `GET /api/tenant-admin/features/audit` - View feature toggle audit log

**Authorization**: Requires `Tenant_Admin` role

### FR-4: Feature Toggle Check Service

**Priority**: High

**Description**: Service to check if feature is enabled for tenant

**Requirements**:

- `is_feature_enabled(tenant, feature_key)` method
- Caching layer for performance (Redis or in-memory)
- Cache invalidation on toggle changes
- Fallback to database if cache miss
- Handles feature dependencies
- Returns boolean result

### FR-5: API Endpoint Protection

**Priority**: High

**Description**: Decorator to protect API endpoints with feature toggles

**Requirements**:

- `@feature_required(feature_key)` decorator
- Checks if feature enabled for tenant
- Returns 403 Forbidden if disabled
- Works with existing `@cognito_required` decorator
- Logs access attempts to disabled features
- Clear error message in response

### FR-6: Frontend Feature Toggle Integration

**Priority**: High

**Description**: React hooks and components for feature toggles

**Requirements**:

- `useFeatureToggle(featureKey)` hook
- `<FeatureToggle feature="key">` component
- `isFeatureEnabled(featureKey)` utility function
- Context provider for feature state
- Automatic UI hiding for disabled features
- Loading state handling

### FR-7: SysAdmin UI

**Priority**: Medium

**Description**: UI for SysAdmin to manage features

**Requirements**:

- Feature list with search and filter
- Create/edit feature form
- Global enable/disable controls
- Tenant override management
- Feature usage statistics
- Deprecation workflow

### FR-8: TenantAdmin UI

**Priority**: Medium

**Description**: UI for TenantAdmin to manage features

**Requirements**:

- Feature list grouped by module
- Toggle switches for each feature
- Feature descriptions and help text
- Beta/experimental badges
- Dependency warnings
- Audit log viewer

---

## Non-Functional Requirements

### NFR-1: Performance

- Feature toggle checks must complete in < 5ms
- Cache hit rate must be > 95%
- No impact on page load times
- Database queries must use indexes

### NFR-2: Scalability

- Support 1000+ feature definitions
- Support 100+ tenants
- Handle 10,000+ toggle checks per second
- Efficient cache invalidation

### NFR-3: Security

- Feature toggles respect module access
- Cannot enable feature if module disabled
- Audit log for all toggle changes
- SysAdmin overrides cannot be bypassed

### NFR-4: Reliability

- Feature toggle failures default to safe state (disabled)
- Graceful degradation if cache unavailable
- No single point of failure
- Automatic cache recovery

### NFR-5: Maintainability

- Clear naming conventions for feature keys
- Comprehensive documentation
- Easy to add new features
- Migration path for existing features

### NFR-6: Usability

- Intuitive UI for both SysAdmin and TenantAdmin
- Clear error messages
- Helpful tooltips and descriptions
- Responsive design

---

## Initial Feature List

### FIN Module Features

| Feature Key                              | Display Name                       | Description                                      | Default |
| ---------------------------------------- | ---------------------------------- | ------------------------------------------------ | ------- |
| `fin_import_banking_str_revenue`         | STR Channel Revenue Calculation    | Calculate STR revenue when importing bank data   | true    |
| `fin_import_invoices_generate_receipt`   | Generate Receipt on Invoice Import | Auto-generate receipts for imported invoices     | true    |
| `fin_import_invoices_missing_generation` | Generate Missing Invoices          | Auto-generate invoices for transactions w/o docs | false   |
| `fin_duplicate_detection`                | Duplicate Invoice Detection        | AI-powered duplicate detection                   | true    |
| `fin_ai_extraction`                      | AI Invoice Extraction              | Use OpenRouter AI for invoice parsing            | true    |
| `fin_excel_export`                       | Excel Export                       | Export financial reports to Excel                | true    |
| `fin_aangifte_ib`                        | Aangifte IB (Income Tax)           | Generate income tax declarations                 | true    |
| `fin_btw_processor`                      | BTW (VAT) Processing               | Process VAT transactions                         | true    |
| `fin_toeristenbelasting`                 | Tourist Tax Processing             | Process tourist tax calculations                 | true    |

### STR Module Features

| Feature Key                    | Display Name             | Description                                | Default |
| ------------------------------ | ------------------------ | ------------------------------------------ | ------- |
| `str_pricing_optimizer`        | AI Pricing Optimizer     | AI-powered pricing recommendations         | false   |
| `str_channel_management`       | Channel Management       | Manage Airbnb/Booking.com channels         | true    |
| `str_revenue_analytics`        | Revenue Analytics        | Advanced revenue analytics and forecasting | true    |
| `str_booking_import`           | Booking Import           | Import bookings from STR platforms         | true    |
| `str_invoice_generation`       | STR Invoice Generation   | Generate invoices for STR bookings         | true    |
| `str_future_revenue_summaries` | Future Revenue Summaries | Calculate future revenue projections       | true    |
| `str_event_based_pricing`      | Event-Based Pricing      | Pricing uplifts for events                 | false   |

### TENADMIN Module Features

| Feature Key                       | Display Name              | Description                           | Default |
| --------------------------------- | ------------------------- | ------------------------------------- | ------- |
| `tenadmin_user_management`        | User Management           | Create and manage tenant users        | true    |
| `tenadmin_credentials_management` | Credentials Management    | Manage Google Drive credentials       | true    |
| `tenadmin_storage_configuration`  | Storage Configuration     | Configure Google Drive folders        | true    |
| `tenadmin_tenant_details`         | Tenant Details            | View and edit tenant information      | true    |
| `tenadmin_feature_toggles`        | Feature Toggle Management | Manage feature toggles (this feature) | false   |
| `tenadmin_audit_logs`             | Audit Logs                | View tenant activity audit logs       | false   |

---

## Feature Toggle vs Module Management

### Key Differences

| Aspect           | Module Management          | Feature Toggles                   |
| ---------------- | -------------------------- | --------------------------------- |
| **Granularity**  | Coarse (entire module)     | Fine (individual features)        |
| **Control**      | TenantAdmin only           | SysAdmin + TenantAdmin            |
| **Purpose**      | Access control & licensing | Feature rollout & customization   |
| **Scope**        | All features in module     | Specific functionality            |
| **Pricing**      | Tied to subscription tiers | Optional add-ons                  |
| **Dependencies** | None (modules independent) | Features can depend on each other |
| **Override**     | Cannot be overridden       | SysAdmin can override             |

### Relationship

- **Module is prerequisite**: Feature toggle only works if module is enabled
- **Module disables all features**: Disabling module disables all its features
- **Feature toggles are optional**: Can use modules without feature toggles
- **Independent systems**: Module and feature toggle tables are separate

### Example Scenarios

**Scenario 1: Beta Feature Rollout**

- Module: FIN (enabled for all tenants)
- Feature: `fin_ai_extraction` (enabled for 10 beta tenants only)
- Result: Only beta tenants see AI extraction option

**Scenario 2: Premium Feature**

- Module: STR (enabled for all tenants)
- Feature: `str_pricing_optimizer` (enabled for premium tier only)
- Result: Premium tenants get pricing optimizer

**Scenario 3: Problematic Feature**

- Module: FIN (enabled)
- Feature: `fin_duplicate_detection` (disabled for Tenant A due to bug)
- Result: Tenant A doesn't see duplicate detection while bug is fixed

---

## Implementation Complexity Analysis

### Complexity: Medium

**Estimated Effort**: 3-4 days

### Impact on Existing Codebase

**Low to Medium Impact**:

1. **Database Changes** (Low Impact)
   - Add 2 new tables (feature_definitions, tenant_feature_states)
   - No changes to existing tables
   - Backward compatible

2. **Backend Changes** (Medium Impact)
   - New FeatureToggleService (new file)
   - New decorator `@feature_required` (new file)
   - Update ~20 API endpoints with decorator
   - New SysAdmin routes (new file)
   - Update TenantAdmin routes (minor changes)

3. **Frontend Changes** (Medium Impact)
   - New FeatureToggleContext (new file)
   - New useFeatureToggle hook (new file)
   - New FeatureToggle component (new file)
   - Update ~15 components to use feature toggles
   - New SysAdmin feature management UI (new file)
   - New TenantAdmin feature management UI (new file)

4. **Testing Changes** (Medium Impact)
   - Unit tests for FeatureToggleService (~15 tests)
   - Integration tests for feature toggle flow (~10 tests)
   - Frontend tests for hooks/components (~20 tests)
   - E2E tests for feature toggle UI (~5 tests)

### Risk Assessment

**Low Risk**:

- ✅ Additive changes (no breaking changes)
- ✅ Can be rolled out gradually
- ✅ Easy to disable if issues arise
- ✅ Well-defined scope
- ✅ Similar to existing module system

**Mitigation Strategies**:

- Feature toggles themselves can be feature-toggled
- Comprehensive testing before rollout
- Gradual rollout to internal tenants first
- Monitoring and alerting for toggle failures
- Rollback plan (disable feature toggle system)

---

## Out of Scope

The following are explicitly **not** included in this phase:

- ❌ User-level feature toggles (only tenant-level)
- ❌ Time-based feature toggles (scheduled enable/disable)
- ❌ Percentage-based rollouts (enable for X% of users)
- ❌ A/B testing analytics integration
- ❌ Feature usage tracking and analytics
- ❌ Automatic feature deprecation workflow
- ❌ Feature toggle API for external integrations
- ❌ Multi-region feature toggle synchronization
- ❌ Feature toggle versioning and history

These may be considered for future phases.

---

## Dependencies

### Technical Dependencies

- ✅ Existing module system (tenant_modules table)
- ✅ Authentication system (Cognito)
- ✅ Authorization system (role-based access)
- ✅ Database (MySQL)
- ✅ Caching layer (can use in-memory or Redis)

### Feature Dependencies

- Must complete Phase 4 (Tenant Admin Module) first
- SysAdmin UI requires SysAdmin role implementation
- Audit logging requires audit_log table

---

## Acceptance Testing Scenarios

### Scenario 1: SysAdmin Creates Feature

**Given**: I am logged in as SysAdmin  
**When**: I create a new feature "fin_test_feature"  
**Then**: Feature appears in feature list  
**And**: Feature is available to all tenants by default

### Scenario 2: TenantAdmin Enables Feature

**Given**: I am logged in as TenantAdmin  
**And**: Feature "str_pricing_optimizer" exists and is disabled  
**When**: I enable the feature  
**Then**: Feature becomes available to my users  
**And**: Change is logged in audit trail

### Scenario 3: Feature Dependency Check

**Given**: Feature A depends on Feature B  
**And**: Feature B is disabled  
**When**: I try to enable Feature A  
**Then**: I see warning about dependency  
**And**: Feature A remains disabled

### Scenario 4: Module Disabled Blocks Features

**Given**: FIN module is disabled for my tenant  
**When**: I try to enable "fin_ai_extraction"  
**Then**: I see error message  
**And**: Feature remains disabled

### Scenario 5: SysAdmin Override

**Given**: TenantAdmin has enabled a feature  
**When**: SysAdmin disables feature globally  
**Then**: Feature is disabled for all tenants  
**And**: TenantAdmin cannot re-enable it

### Scenario 6: API Endpoint Protection

**Given**: Feature "fin_ai_extraction" is disabled  
**When**: User calls `/api/invoices/extract-ai`  
**Then**: API returns 403 Forbidden  
**And**: Error message explains feature is disabled

### Scenario 7: UI Element Hiding

**Given**: Feature "str_pricing_optimizer" is disabled  
**When**: User views STR dashboard  
**Then**: Pricing optimizer button is not visible  
**And**: No broken UI elements

---

## Open Questions

1. **Caching Strategy**: Use Redis or in-memory cache? (Recommendation: Start with in-memory, add Redis later)
2. **Cache TTL**: How long to cache feature states? (Recommendation: 5 minutes with manual invalidation)
3. **Feature Key Naming**: Enforce naming convention? (Recommendation: Yes, `{module}_{feature_name}`)
4. **Beta Features**: How to handle beta feature feedback? (Recommendation: Add feedback form link)
5. **Feature Metrics**: Track feature usage from day 1? (Recommendation: Yes, simple counter)
6. **Rollback**: How to handle feature rollback? (Recommendation: Disable feature, keep data)
7. **Migration**: Migrate existing functionality to feature toggles? (Recommendation: Gradually, starting with new features)

---

## Next Steps

1. **Review & Approval**: Get stakeholder approval on requirements
2. **Design Phase**: Create technical design document
3. **Database Schema**: Design and review database schema
4. **API Design**: Design API endpoints and contracts
5. **UI Mockups**: Create wireframes for SysAdmin and TenantAdmin UIs
6. **Implementation Plan**: Break down into tasks with estimates
7. **Testing Strategy**: Define comprehensive test plan

---

## References

- Existing Module System: `backend/sql/phase5_tenant_modules.sql`
- Tenant Admin Module: `.kiro/specs/Common/TenantAdmin-Module/`
- Authentication: `backend/src/auth/cognito_utils.py`
- Authorization: `backend/src/auth/tenant_context.py`

---

**Document Version**: 1.0
**Status**: Draft - Ready for Review
**Next Review Date**: TBD
