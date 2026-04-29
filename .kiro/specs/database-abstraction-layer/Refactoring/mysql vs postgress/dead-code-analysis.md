# Dead Code Analysis — myAdmin

**Date:** 2026-04-29
**Status:** Analysis complete, cleanup pending
**Author:** Kiro (AI-assisted analysis)

---

## Summary

| Category                                   | Files          | Lines | Size  |
| ------------------------------------------ | -------------- | ----- | ----- |
| Backup files in `backend/src/`             | 9              | —     | 405KB |
| Unused modules in `backend/src/`           | 10             | ~500  | ~37KB |
| One-off scripts in `backend/` root         | 46             | 5,893 | 195KB |
| One-off scripts in project root            | 4              | 138   | 5KB   |
| Unused imports (confirmed, 90% confidence) | 14 occurrences | —     | —     |
| Unused methods (needs manual review)       | ~35            | —     | —     |
| Broken files (syntax errors)               | 1              | —     | 0.8KB |

---

## 1. Backup Files — DELETE (5 minutes, 405KB freed)

These are version-controlled in git, so keeping `.backup` copies in the source tree is just noise.

| File                                               | Size  |
| -------------------------------------------------- | ----- |
| `backend/src/app.py.backup`                        | 140KB |
| `backend/src/pattern_analyzer_original_backup.py`  | 83KB  |
| `backend/src/openapi_spec.yaml.backup`             | 77KB  |
| `backend/src/routes/sysadmin_routes_old.py`        | 34KB  |
| `backend/src/bnb_routes.py.backup`                 | 17KB  |
| `backend/src/str_invoice_routes.py.backup`         | 16KB  |
| `backend/src/database.py.backup`                   | 13KB  |
| `backend/src/database.py.pre_consolidation_backup` | 13KB  |
| `backend/src/str_channel_routes.py.backup`         | 11KB  |

**Action:** Delete all. Git has the history.

---

## 2. Broken File — DELETE (1 minute)

`backend/src/check_revolut.py` has a syntax error (indentation broke the try/except block at line 16). It's a one-off debug script that doesn't belong in `src/` anyway.

**Action:** Delete.

---

## 3. Unused Modules in `backend/src/` — DELETE after verification (30 minutes)

These 10 files are never imported by any other source file in `backend/src/`:

| File                              | Size  | What it is                                       | Verify before deleting                 |
| --------------------------------- | ----- | ------------------------------------------------ | -------------------------------------- |
| `duplicate_performance_routes.py` | 15KB  | Performance monitoring routes — never registered | Check `app.py` blueprint registrations |
| `google_drive_oauth_routes.py`    | 7KB   | OAuth routes                                     | Check if registered in `app.py`        |
| `notification_integration.py`     | 5KB   | Notification wrapper — never used                | Check `app.py`                         |
| `invoice_generator.py`            | 5KB   | Invoice generation — possibly superseded         | Check if any route or service uses it  |
| `events_config.py`                | 1KB   | Event uplift config — never imported             | Check `hybrid_pricing_optimizer.py`    |
| `test_api_response.py`            | 1KB   | Test script accidentally in `src/`               | Safe to delete                         |
| `test_server.py`                  | 1KB   | Test script accidentally in `src/`               | Safe to delete                         |
| `debug_routes.py`                 | 0.5KB | Debug routes                                     | Check `app.py`                         |
| `check_revolut.py`                | 0.8KB | Broken debug script (syntax error)               | Safe to delete                         |
| `wsgi.py`                         | 0.2KB | WSGI entry point                                 | Check Dockerfile / Railway config      |

**Action:** Verify `google_drive_oauth_routes.py`, `wsgi.py`, and `duplicate_performance_routes.py` against `app.py` and deployment configs before deleting. The rest are safe to remove.

---

## 4. One-Off Scripts — REORGANIZE (1 hour)

### 4.1 Backend root (46 files, 5,893 lines, 195KB)

These scripts clutter the backend directory. They are not part of the running application.

| Category   | Count | Files                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `check_*`  | 11    | `check_2025_data.py`, `check_account_1022.py`, `check_cache_resultaat.py`, `check_field_mappings.py`, `check_gdrive_templates.py`, `check_google_token_health.py`, `check_hoogvliet.py`, `check_missing_patterns.py`, `check_myadmin_module.py`, `check_resultaat.py`, `check_resultaat_logic.py`                                                                                                                                                                     |
| `test_*`   | 17    | `test_aangifte_ib_e2e.py`, `test_cognito_auth.py`, `test_country_query.py`, `test_direct_booking_dates.py`, `test_email_templates.py`, `test_integration_workflows.py`, `test_invitation_flow.py`, `test_pattern_loading.py`, `test_prediction.py`, `test_railway_connection.py`, `test_resultaat_calc.py`, `test_role_checks.py`, `test_sns_email.py`, `test_sysadmin_auth.py`, `test_template_validation.py`, `test_tenant_isolation.py`, `test_verb_extraction.py` |
| `fix_*`    | 2     | `fix_checkout_dates.py`, `fix_future_booking_status.py`                                                                                                                                                                                                                                                                                                                                                                                                               |
| `debug_*`  | 2     | `debug_invoice_generation.py`, `debug_row_diff.py`                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `verify_*` | 2     | `verify_aangifte_ib_format.py`, `verify_cognito_setup.py`                                                                                                                                                                                                                                                                                                                                                                                                             |
| Other      | 12    | `add_fin_module.py`, `add_tenadmin_module.py`, `add_tenants_to_user.py`, `cleanup_corrupted_patterns.py`, `compare_outputs.py`, `diagnose_google_token.py`, `query_templates.py`, `refresh_google_token.py`, `start_railway.py`, `update_admin_roles.py`, `update_admin_tenant.py`, `validate_env.py`                                                                                                                                                                 |

**Recommended action:**

- Move `test_*` scripts (17 files) → `backend/tests/manual/` or delete if they were one-time checks
- Move `check_*` scripts (11 files) → `backend/scripts/diagnostics/`
- Move `fix_*`, `debug_*`, `verify_*` → `backend/scripts/maintenance/`
- Keep only `start_railway.py` and `validate_env.py` in backend root (operational scripts)

### 4.2 Project root (4 files, 138 lines, 5KB)

| File                        | Purpose                |
| --------------------------- | ---------------------- |
| `add_tenant_logo_config.py` | One-time config script |
| `check_tenant_config.py`    | Diagnostic script      |
| `convert_logo_to_base64.py` | Utility script         |
| `get_template_info.py`      | Diagnostic script      |

**Action:** Move to `scripts/utilities/` or delete if no longer needed.

---

## 5. Unused Imports — CLEAN UP (15 minutes)

These 14 imports are confirmed dead at 90% confidence — safe to remove:

| File                                                     | Unused Import              |
| -------------------------------------------------------- | -------------------------- |
| `backend/src/aws_notifications.py`                       | `BotoCoreError`            |
| `backend/src/bnb_routes.py`                              | `np` (numpy)               |
| `backend/src/duplicate_query_optimizer.py`               | `lru_cache`                |
| `backend/src/file_cleanup_manager.py`                    | `parse_qs`                 |
| `backend/src/google_drive_service.py`                    | `InstalledAppFlow`         |
| `backend/src/pattern_cache.py`                           | `pickle`                   |
| `backend/src/validate_pattern/pattern_cache.py`          | `pickle`                   |
| `backend/src/report_generators/aangifte_ib_generator.py` | `get_css_class_for_amount` |
| `backend/src/routes/signup_routes.py`                    | `current_app`              |
| `backend/src/scalability_manager.py`                     | `asyncio`                  |
| `backend/src/session_manager.py`                         | `Set`                      |
| `backend/src/str_invoice_routes.py`                      | `render_template_string`   |

**Action:** Remove all. These are confirmed unused.

---

## 6. Unused Methods — INVESTIGATE LATER (needs manual review)

Vulture flagged ~35 methods at 60% confidence. These need manual review because some may be called dynamically or through patterns vulture can't detect.

### Likely real dead code (higher confidence)

| File                               | Method                                                                                   | Reason                                  |
| ---------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------- |
| `database.py`                      | `_get_db_config()`                                                                       | Never called                            |
| `database.py`                      | `execute_async_query()`                                                                  | Async wrapper never used                |
| `database.py`                      | `create_tables()`                                                                        | Legacy table creation                   |
| `database.py`                      | `insert_transactions()`                                                                  | Superseded by `insert_transaction()`    |
| `database.py`                      | `clear_query_cache()`                                                                    | Cache method never called               |
| `database.py`                      | `shutdown_scalability_manager()`                                                         | Shutdown hook never wired               |
| `database_migrations.py`           | `create_migration()`, `rollback_migration()`                                             | Migration framework never used          |
| `performance_optimizer.py`         | `BatchProcessor` class + 6 methods                                                       | Entire class appears unused             |
| `notification_integration.py`      | All 8 methods                                                                            | Entire module is unused (see section 3) |
| `hybrid_pricing_optimizer.py`      | `_calculate_monthly_multipliers()`, `_calculate_seasonal_multipliers()`, `_get_season()` | Internal methods never called           |
| `duplicate_performance_monitor.py` | `monitor_file_cleanup()`, `monitor_decision_log()`, `monitor_database_query()`           | Monitor methods never wired             |
| `file_cleanup_manager.py`          | `get_cleanup_health_status()`                                                            | Health check never called               |
| `pattern_cache.py`                 | `clear_all_cache()`                                                                      | Never called                            |

### False positives (skip these)

The ~80 "unused functions" vulture flagged in route files (`banking_routes.py`, `bnb_routes.py`, `reporting_routes.py`, etc.) are **false positives**. Flask route handlers are called by the framework via `@route` decorators, not by direct import. These are fine.

Similarly, `gunicorn.conf.py` variables are read by Gunicorn at startup — not dead code.

---

## 7. Other Infrastructure Dead Code

| Item                  | Location          | Notes                                                                                                       |
| --------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------- |
| `ec2.tf.disabled`     | `infrastructure/` | Disabled Terraform file for EC2. Keep if planning to re-enable, delete if EC2 is permanently off the table. |
| `_dead_code_check.py` | Project root      | Temporary analysis script created during this review. Delete after cleanup.                                 |

---

## 8. Recommended Cleanup Order

| Priority  | Action                                                                                                          | Effort   | Risk                               |
| --------- | --------------------------------------------------------------------------------------------------------------- | -------- | ---------------------------------- |
| **P1**    | ~~Delete 9 backup files~~ ✅ Done 2026-04-29                                                                    | 5 min    | None (git has history)             |
| **P2**    | ~~Delete broken `check_revolut.py`~~ ✅ Done 2026-04-29                                                         | 1 min    | None                               |
| **P3**    | ~~Remove 14 unused imports~~ ✅ Done 2026-04-29                                                                 | 15 min   | None                               |
| **P4**    | ~~Delete confirmed unused modules (test/debug scripts in `src/`)~~ ✅ Done 2026-04-29                           | 10 min   | None                               |
| **P5**    | ~~Verify and delete remaining unused modules~~ ✅ Done 2026-04-29 (8 deleted, `wsgi.py` kept — used by Railway) | 30 min   | Low (verify `app.py` first)        |
| **P6**    | ~~Reorganize one-off scripts~~ ✅ Done 2026-04-29                                                               | 1 hour   | Low                                |
| **P7**    | Review and remove unused methods                                                                                | 2 hours  | Medium (needs manual verification) |
| **Total** |                                                                                                                 | ~4 hours |                                    |

---

## 9. Tooling Used

- **Vulture** (`python -m vulture backend/src --min-confidence 60`) — Python dead code detection
- **Custom script** (`_dead_code_check.py`) — Module import analysis, backup file detection, syntax error checking
- **PowerShell** — File counting and categorization
- **Manual review** — Cross-referencing `app.py` blueprint registrations
