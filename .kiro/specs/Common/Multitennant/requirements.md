Question how do we implement Multitennants in myAdmin
REQ1. myAdmin should be able to support more (max 100) tennants without big problems
REQ2. Tennant definition should be implemented in Cognito
REQ3. A specific tennant should be available for SysAdmin
REQ4. Users can belong to multiple tenants (e.g., accountant for both GoodwinSolutions and PeterPrive)
REQ5. Users must select active tenant when they have access to multiple tenants
REQ6. All database queries must be filtered by tenant (except for SysAdmin and generic tables)
REQ7. Tenant switching should not require re-authentication
REQ8. All database identifiers (tables, columns, views) must use lowercase for PostgreSQL compatibility
REQ9. Audit logging must track which tenant data was accessed by which user
REQ10. API endpoints must validate user has access to requested tenant before returning data
REQ11. Frontend must display current active tenant to user
REQ12. SysAdmin role is isolated from tenant data access (separation of duties)
REQ12a. During development/testing, users may have combined roles (SysAdmin + Finance_CRUD + tenant assignments)
REQ12b. In production, SysAdmin should NOT have tenant assignments (security best practice)
REQ12c. Emergency tenant access (if needed) requires separate Emergency_Access role with audit trail
REQ13. Tenant isolation must be enforced at database query level (defense in depth)
REQ14. New tenants can be added without code changes (configuration only)
REQ15. Tenant data must remain isolated - no cross-tenant data leakage
REQ16. Each tenant must have a Tenant_Admin role to manage tenant-specific settings
REQ17. Tenant_Admin can configure tenant-specific integrations (Google Drive, S3, OneDrive, email, etc.)
REQ18. Tenant_Admin can manage users within their tenant (add/remove roles for their tenant only)
REQ19. Tenant secrets (API keys, credentials) must be encrypted and isolated per tenant
REQ20. Tenant_Admin cannot access other tenants' configurations or secrets

Question: What is the best approach, make a short architecture.md in this folder .kiro\specs\Common\Multitennant

Quick analysis / status of the potential use of the field Administration

- Tennant structuur ontbreekt nog!!!!!
- current tennants PeterPrive, InterimManagement, GoodwinSolutions
- Veld Administration in sql in tbl mutaties and rekeningschema is used for tennants
- Administration fied has to be in the following tables
  -- bnb field Administration content GoodwinSolutions
  -- bnbfuture field Administration content GoodwinSolutions
  -- bnblookup field Administration content GoodwinSolutions
  -- bnbplanned field Administration content GoodwinSolutions
  -- countries is a generic table can be used by anyone
  -- database_migrations is a generic table can only be used by SysAdmin
  -- duplicate_decision_log is a generic table can only be used by SysAdmin
  -- listings field Administration content GoodwinSolutions
  -- lookupbankaccounts_r is OK
  -- mutaties is OK
  -- pattern_analysis_metadata is OK but administration is lowercase and not Administration
  -- pattern_verb_patterns is OK but administration is lowercase and not Administration
  -- pricing_events field Administration content GoodwinSolutions
  -- pricing_recommendations field Administration content GoodwinSolutions
  -- rekeningschema is OK

- Administration fied has to be in the following views
  -- lookupbankaccounts_r is OK
  -- vw_beginbalans is OK
  -- vw_bnb_total field Administration to be added
  -- vw_creditmutaties is OK
  -- vw_debetmutaties is OK
  -- vw_mutaties is OK
  -- vw_readreferences is OK bur administration in stead of Administration
  -- vw_rekeningnummers is OK
  -- vw_rekeningschema is OK
  -- vw_reservationcode is OK
