# Tasks: Invoice Lines & Contact Emails Tenant Isolation

## Phase 1: Database Migration (REQ1, REQ2, REQ5, REQ6)

- [x] 1.1 Create migration file `backend/src/migrations/20260502120000_tenant_isolation_child_tables.json` with up/down SQL statements per design.md (~30 min)
- [x] 1.2 Update DDL reference `backend/sql/phase_zzp_tables.sql` — add `administration` column to `invoice_lines` and `contact_emails` table definitions, update `vw_invoice_vat_summary` view definition (~15 min)

## Phase 2: ZZPInvoiceService Query Updates (REQ3, REQ5, REQ7)

- [x] 2.1 Update `_save_lines` — add `administration` to INSERT column list and values tuple, using `tenant` parameter (~10 min)
- [x] 2.2 Update `_update_totals` — change signature to accept `tenant: str`, add `AND administration = %s` to VAT summary SELECT (~10 min)
- [x] 2.3 Update all `_update_totals` callers — pass `tenant` in `create_invoice`, `update_invoice`, `create_credit_note` (~10 min)
- [x] 2.4 Update `update_invoice` — add `AND administration = %s` to DELETE FROM invoice_lines WHERE clause (~5 min)
- [x] 2.5 Update `get_invoice` — add `AND administration = %s` to invoice_lines SELECT and vw_invoice_vat_summary SELECT (~10 min)
- [x] 2.6 Update `copy_last_invoice` — add `AND administration = %s` to invoice_lines SELECT (~5 min)

## Phase 3: ContactService Query Updates (REQ4, REQ7)

- [x] 3.1 Update `_save_emails` — change signature to accept `tenant: str`, add `administration` to INSERT (~10 min)
- [x] 3.2 Update `_get_emails` — change signature to accept `tenant: str`, add `AND administration = %s` to SELECT (~5 min)
- [x] 3.3 Update `_replace_emails` — change signature to accept `tenant: str`, add `AND administration = %s` to DELETE, pass `tenant` to `_save_emails` (~10 min)
- [x] 3.4 Update `get_invoice_email` — add `AND administration = %s` to SELECT (~5 min)
- [x] 3.5 Update all callers of `_get_emails`, `_save_emails`, `_replace_emails` — pass `tenant` in `create_contact`, `update_contact`, `get_contact`, `get_contact_by_client_id` (~15 min)

## Phase 4: ProductService Query Update (REQ3)

- [x] 4.1 Update `_check_product_in_use` — replace JOIN query with direct `WHERE product_id = %s AND administration = %s` on invoice_lines (~5 min)

## Phase 5: Unit Test Updates

- [x] 5.1 Update ZZPInvoiceService unit tests — adjust mock expectations for new `administration` parameter in INSERT tuples, DELETE tuples, SELECT queries, and `_update_totals` signature change (~30 min)
- [x] 5.2 Update ContactService unit tests — adjust mock expectations for new `tenant` parameter in `_save_emails`, `_get_emails`, `_replace_emails` signatures and query parameter tuples (~30 min)
- [x] 5.3 Update ProductService unit tests — adjust mock expectation for `_check_product_in_use` query change (no JOIN) (~10 min)
- [x] 5.4 Run full unit test suite and fix any remaining failures (~15 min)
