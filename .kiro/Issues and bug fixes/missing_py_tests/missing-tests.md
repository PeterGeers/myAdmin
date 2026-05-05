# Untested Sources — Action Plan

## Overview

Analysis of 62 source files flagged as having no corresponding tests. After classification:

- **1 file** deleted (dead code)
- **11 files** need no tests (scripts/config)
- **50 files** need tests across 3 priority tiers

---

## ❌ DELETED (Dead Code)

| File                                     | Action                                   |
| ---------------------------------------- | ---------------------------------------- |
| `services/credential_service_example.py` | ✅ Deleted — zero references in codebase |

---

## 🚫 NO TESTS NEEDED (Scripts/Config)

| File                                                | Reason                      |
| --------------------------------------------------- | --------------------------- |
| `migrations/apply_tenant_isolation.py`              | One-time migration script   |
| `migrations/cleanup_invalid_params.py`              | One-time migration script   |
| `migrations/create_parameters_table.py`             | One-time migration script   |
| `migrations/create_tax_rates_table.py`              | One-time migration script   |
| `migrations/migrate_tenant_config_to_parameters.py` | One-time migration script   |
| `migrations/seed_goodwin_str_rates.py`              | One-time migration script   |
| `migrations/seed_tenant_parameters.py`              | One-time migration script   |
| `validate_pattern/pattern_analyzer_test.py`         | Standalone test harness     |
| `validate_pattern/run_test.py`                      | Standalone test runner      |
| `gunicorn.conf.py`                                  | Production config, no logic |
| `wsgi.py`                                           | WSGI entry point, trivial   |

---

## 🔴 TIER 1 — High Priority (Business Logic, Unit + Integration Tests)

**Target coverage: 80%+**

These files contain core business logic (calculations, transformations, decisions) and require comprehensive unit testing with mocked dependencies.

| File                              | Lines | Action                 | What to Test                                                                                    |
| --------------------------------- | ----- | ---------------------- | ----------------------------------------------------------------------------------------------- |
| `business_pricing_model.py`       | 280   | **Unit tests**         | 7-factor price calculation, each multiplier function, base rate weekday/weekend, BTW adjustment |
| `hybrid_pricing_optimizer.py`     | 746   | **Unit + Integration** | Pricing strategy generation, seasonal multipliers, event uplifts, AI insight parsing            |
| `btw_processor.py`                | 520   | **Unit tests**         | VAT account resolution, balance calculations, quarter aggregation, report data preparation      |
| `toeristenbelasting_processor.py` | 150   | **Unit tests**         | Tourist tax calculation, report data preparation, template rendering                            |
| `ai_extractor.py`                 | 180   | **Unit tests**         | Date validation, JSON parsing, fallback model logic, data cleaning                              |
| `security_audit.py`               | 813   | **Unit tests**         | Input validation rules, SQL injection detection, XSS checks, security scoring                   |
| `country_detector.py`             | 80    | **Unit tests**         | Phone number parsing, country code extraction, edge cases                                       |
| `bnb_cache.py`                    | 120   | **Unit tests**         | Cache TTL logic, refresh triggers, data filtering                                               |
| `database_migrations.py`          | 200   | **Unit tests**         | Migration tracking, version ordering, schema state                                              |
| `performance_optimizer.py`        | 150   | **Unit tests**         | Profiling decorator, memory tracking, query analysis                                            |
| `i18n.py`                         | 43    | **Unit tests**         | Locale detection from header, fallback locale                                                   |

### Testing Approach

```python
@pytest.mark.unit
def test_pricing_multiplier():
    """Test each multiplier in isolation with mocked DB."""
    model = BusinessPricingModel(test_mode=True)
    # Mock database calls
    result = model._get_historical_multiplier(listing, date)
    assert 0.5 <= result <= 2.0
```

---

## 🟠 TIER 2 — Medium Priority (Services & Processors, Integration/API Tests)

**Target coverage: 60%+**

These files contain service logic, external integrations, or route handlers with non-trivial logic beyond simple delegation.

| File                                  | Lines | Action          | What to Test                                            |
| ------------------------------------- | ----- | --------------- | ------------------------------------------------------- |
| `services/country_report_service.py`  | 100   | **Integration** | Report data aggregation, HTML rendering                 |
| `services/email_log_service.py`       | 120   | **Integration** | Email logging, delivery status updates, query filtering |
| `services/tenant_language_service.py` | 80    | **Integration** | Language preference CRUD, validation                    |
| `services/tenant_settings_service.py` | 150   | **Integration** | Settings JSON management, activity logging              |
| `services/user_language_service.py`   | 100   | **Integration** | Cognito attribute updates, language validation          |
| `aws_notifications.py`                | 150   | **Integration** | SNS publish, error handling, message formatting         |
| `route_validator.py`                  | 50    | **Unit tests**  | Route conflict detection logic                          |
| `admin_routes.py`                     | 200   | **API tests**   | User/role management endpoints, permission checks       |
| `audit_routes.py`                     | 150   | **API tests**   | Audit log query, filtering, report generation           |
| `scalability_routes.py`               | 100   | **API tests**   | Monitoring endpoints, metrics                           |
| `tenant_module_routes.py`             | 80    | **API tests**   | Module access control                                   |
| `migrate_revolut_ref2.py`             | 80    | **Integration** | Data transformation, reference format migration         |
| `utils/frontend_url.py`               | 50    | **Unit tests**  | URL resolution, environment-based config                |

### Testing Approach

```python
@pytest.mark.integration
def test_email_log_service_tracks_delivery():
    """Test email delivery status tracking."""
    service = EmailLogService(test_mode=True)
    service.log_email(tenant, recipient, subject, status='sent')
    logs = service.get_logs(tenant, limit=1)
    assert logs[0]['status'] == 'sent'
```

---

## 🟡 TIER 3 — Lower Priority (Route Delegation, API/Smoke Tests)

**Target coverage: 40%+**

These files are primarily route handlers that delegate to service layers. They need API-level tests to verify endpoint registration, authentication, and basic request/response flow.

| File                                   | Lines | Action         | What to Test                                         |
| -------------------------------------- | ----- | -------------- | ---------------------------------------------------- |
| `routes/tax_routes.py`                 | 280   | **API tests**  | BTW/tourist tax endpoints, report generation flow    |
| `routes/invoice_routes.py`             | 180   | **API tests**  | Upload flow, duplicate detection, approval           |
| `routes/auth_routes.py`                | 280   | **API tests**  | Forgot-password flow, code validation, rate limiting |
| `routes/chart_of_accounts_routes.py`   | 80    | **API tests**  | CRUD endpoints                                       |
| `routes/config_routes.py`              | 60    | **Smoke**      | Config loads and serves                              |
| `routes/duplicate_detection_routes.py` | 100   | **API tests**  | Detection endpoints                                  |
| `routes/email_log_routes.py`           | 80    | **API tests**  | Query endpoints, webhook                             |
| `routes/folder_routes.py`              | 80    | **API tests**  | Google Drive folder operations                       |
| `routes/migration_routes.py`           | 60    | **Smoke**      | Endpoints register                                   |
| `routes/missing_invoices_routes.py`    | 80    | **API tests**  | Transaction retrieval                                |
| `routes/pdf_validation_routes.py`      | 80    | **API tests**  | Validation endpoints                                 |
| `routes/static_routes.py`              | 50    | **Smoke**      | Static files serve                                   |
| `routes/sysadmin_health.py`            | 100   | **API tests**  | Health check endpoints                               |
| `routes/sysadmin_helpers.py`           | 80    | **Unit tests** | Helper functions                                     |
| `routes/sysadmin_roles.py`             | 100   | **API tests**  | Role management                                      |
| `routes/system_health_routes.py`       | 80    | **API tests**  | Health/monitoring                                    |
| `routes/tenant_admin_config.py`        | 80    | **API tests**  | Config CRUD                                          |
| `routes/tenant_admin_credentials.py`   | 100   | **API tests**  | Credential operations                                |
| `routes/tenant_admin_details.py`       | 80    | **API tests**  | Tenant details CRUD                                  |
| `routes/tenant_admin_email.py`         | 80    | **API tests**  | Email sending                                        |
| `routes/tenant_admin_settings.py`      | 80    | **API tests**  | Settings CRUD                                        |
| `routes/tenant_admin_storage.py`       | 80    | **API tests**  | Storage config                                       |
| `routes/user_routes.py`                | 80    | **API tests**  | User preferences                                     |
| `routes/year_end_config_routes.py`     | 80    | **API tests**  | Year-end config                                      |
| `routes/asset_routes.py`               | 80    | **API tests**  | Asset CRUD                                           |
| `api_schemas.py`                       | 100   | **Smoke**      | Schema validation works                              |

### Testing Approach

```python
@pytest.mark.api
def test_tax_routes_btw_generate(client, mock_auth):
    """Test BTW report generation endpoint."""
    response = client.post('/api/btw/generate-report', json={
        'administration': 'TestTenant',
        'year': 2025,
        'quarter': 1
    }, headers=mock_auth)
    assert response.status_code == 200
    assert response.json['success'] is True
```

---

## Summary

| Category                 | Count  | Action                          |
| ------------------------ | ------ | ------------------------------- |
| Dead code                | 1      | ✅ Deleted                      |
| No tests needed          | 11     | Skip (scripts/config)           |
| Tier 1 — Unit tests      | 11     | Business logic, 80%+ coverage   |
| Tier 2 — Integration/API | 13     | Service layer, 60%+ coverage    |
| Tier 3 — API/Smoke       | 26     | Route delegation, 40%+ coverage |
| **Total**                | **62** |                                 |

---

## Recommended Execution Order

1. **Start with Tier 1 pure logic** — `country_detector.py`, `i18n.py`, `route_validator.py` (small, no DB needed)
2. **Tier 1 with mocked DB** — `business_pricing_model.py`, `btw_processor.py`, `bnb_cache.py`
3. **Tier 1 complex** — `security_audit.py`, `ai_extractor.py`, `hybrid_pricing_optimizer.py`
4. **Tier 2 services** — All 5 service files
5. **Tier 2 utilities** — `aws_notifications.py`, `utils/frontend_url.py`, `admin_routes.py`
6. **Tier 3 routes** — Batch by module (tax, invoices, auth, sysadmin, tenant_admin)

### Fixtures Needed

- `mock_db` — Mocked `DatabaseManager` (already exists in `tests/unit/conftest.py`)
- `mock_cognito` — Mocked Cognito client for auth tests
- `mock_sns` — Mocked AWS SNS for notification tests
- `mock_google_drive` — Mocked Google Drive service
- `client` — Flask test client with app context
- `mock_auth` — Authentication headers for API tests
