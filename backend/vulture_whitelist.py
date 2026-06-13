"""Vulture whitelist — suppress false positives for Flask route handlers.

Flask blueprint route handlers are registered via @blueprint.route() decorators
and called by the WSGI server at runtime, not directly in Python code. Vulture
flags them as "unused" which is a false positive.

Usage:
    vulture backend/src/ backend/vulture_whitelist.py --min-confidence 60
"""

# =============================================================================
# routes/aangifte_ib_routes.py
# =============================================================================
aangifte_ib  # noqa
aangifte_ib_details  # noqa
aangifte_ib_export  # noqa
aangifte_ib_xlsx_download  # noqa
aangifte_ib_xlsx_export  # noqa
aangifte_ib_xlsx_export_stream  # noqa

# =============================================================================
# routes/asset_routes.py
# =============================================================================
asset_register_report  # noqa
create_asset  # noqa
delete_asset  # noqa
depreciation_schedule_report  # noqa
dispose_asset  # noqa
generate_depreciation  # noqa
get_asset  # noqa
list_assets  # noqa
update_asset  # noqa

# =============================================================================
# routes/auth_routes.py
# =============================================================================
confirm_reset_password  # noqa
forgot_password  # noqa
get_current_user_info  # noqa

# =============================================================================
# routes/banking_routes.py
# =============================================================================
banking_apply_patterns  # noqa
banking_check_accounts  # noqa
banking_check_revolut_balance  # noqa
banking_check_revolut_balance_debug  # noqa
banking_check_sequence  # noqa
banking_check_sequences  # noqa
banking_filter_options  # noqa
banking_insert_mutatie  # noqa
banking_lookups  # noqa
banking_migrate_revolut_ref2  # noqa
banking_mutaties  # noqa
banking_opening_balance_date  # noqa
banking_process_files  # noqa
banking_save_transactions  # noqa
banking_scan_files  # noqa
banking_update_mutatie  # noqa

# =============================================================================
# routes/cache_routes.py
# =============================================================================
bnb_cache_invalidate  # noqa
bnb_cache_refresh  # noqa
bnb_cache_status  # noqa
cache_invalidate_endpoint  # noqa
cache_refresh  # noqa
cache_status  # noqa
cache_warmup  # noqa

# =============================================================================
# routes/chart_of_accounts_routes.py
# =============================================================================
create_account  # noqa
delete_account  # noqa
export_accounts  # noqa
get_account  # noqa
import_accounts  # noqa
list_accounts  # noqa
lookup_accounts  # noqa
update_account  # noqa

# =============================================================================
# routes/config_routes.py
# =============================================================================
get_ledger_parameters  # noqa

# =============================================================================
# routes/contact_routes.py
# =============================================================================
create_contact  # noqa
delete_contact  # noqa
get_contact  # noqa
get_contact_types  # noqa
list_contacts  # noqa
update_contact  # noqa

# =============================================================================
# routes/duplicate_detection_routes.py
# =============================================================================
check_duplicate  # noqa
handle_duplicate_decision  # noqa
log_duplicate_decision  # noqa

# =============================================================================
# routes/email_log_routes.py
# =============================================================================
get_email_logs  # noqa
ses_notification_webhook  # noqa

# =============================================================================
# routes/financial_reporting_routes.py
# =============================================================================
get_balance_data  # noqa
get_reference_analysis  # noqa
get_trends_data  # noqa

# =============================================================================
# routes/folder_routes.py
# =============================================================================
create_folder  # noqa
get_folders  # noqa

# =============================================================================
# routes/invoice_routes.py
# =============================================================================
approve_transactions  # noqa
upload_file_wrapper  # noqa

# =============================================================================
# routes/missing_invoices_routes.py
# =============================================================================
get_transactions  # noqa
update_transaction_refs  # noqa
upload_receipt  # noqa

# =============================================================================
# routes/parameter_admin_routes.py
# =============================================================================
create_parameter  # noqa
delete_parameter  # noqa
get_parameter_default  # noqa
get_parameter_schema  # noqa
list_parameters  # noqa
update_parameter  # noqa

# =============================================================================
# routes/pdf_validation_routes.py
# =============================================================================
pdf_get_administrations  # noqa
pdf_update_record  # noqa
pdf_validate_single_url  # noqa
pdf_validate_urls  # noqa
pdf_validate_urls_stream  # noqa

# =============================================================================
# routes/pivot_routes.py
# =============================================================================
delete_model  # noqa
execute_pivot  # noqa
export_underlying  # noqa
get_available_columns  # noqa
get_registered_sources  # noqa
list_models  # noqa
load_model  # noqa
save_model  # noqa
update_model  # noqa

# =============================================================================
# routes/product_routes.py
# =============================================================================
create_product  # noqa
delete_product  # noqa
get_product  # noqa
get_product_types  # noqa
list_products  # noqa
update_product  # noqa

# =============================================================================
# routes/signup_routes.py
# =============================================================================
create_signup  # noqa
resend_verification  # noqa
verify_signup  # noqa

# =============================================================================
# routes/static_routes.py
# =============================================================================
serve_backend_static  # noqa
serve_config  # noqa
serve_favicon  # noqa
serve_index  # noqa
serve_jabaki_logo  # noqa
serve_logo192  # noqa
serve_logo512  # noqa
serve_manifest  # noqa
serve_static  # noqa

# =============================================================================
# routes/storage.py
# =============================================================================
get_presigned_url  # noqa
upload_logo  # noqa

# =============================================================================
# routes/str_routes.py
# =============================================================================
pricing_generate  # noqa
pricing_historical  # noqa
pricing_listings  # noqa
pricing_multipliers  # noqa
pricing_recommendations  # noqa
str_calculate_taxes  # noqa
str_future_trend  # noqa
str_import_payout_wrapper  # noqa
str_save  # noqa
str_summary  # noqa
str_upload_wrapper  # noqa
str_write_future  # noqa

# =============================================================================
# routes/sysadmin_health.py
# =============================================================================
get_system_health  # noqa

# =============================================================================
# routes/sysadmin_pivot_routes.py
# =============================================================================
list_datasources  # noqa
update_datasources  # noqa

# =============================================================================
# routes/sysadmin_provisioning.py
# =============================================================================
list_pending_signups  # noqa
provision_signup  # noqa

# =============================================================================
# routes/sysadmin_roles.py
# =============================================================================
create_role  # noqa
delete_role  # noqa
list_roles  # noqa
update_role  # noqa

# =============================================================================
# routes/sysadmin_tenants.py
# =============================================================================
create_tenant  # noqa
delete_tenant  # noqa
get_tenant  # noqa
get_tenant_modules  # noqa
list_tenants  # noqa
reprovision_tenant  # noqa
resend_invitation  # noqa
update_tenant  # noqa
update_tenant_modules  # noqa

# =============================================================================
# routes/sysadmin_test_tool.py
# =============================================================================
process_file  # noqa
rerun_prompt  # noqa
vendor_history  # noqa

# =============================================================================
# routes/system_health_routes.py
# =============================================================================
get_db_config  # noqa
get_status  # noqa
google_drive_token_health  # noqa
health  # noqa
str_test  # noqa
test  # noqa
test_db_connection  # noqa

# =============================================================================
# routes/tax_rate_admin_routes.py
# =============================================================================
create_tax_rate  # noqa
delete_tax_rate  # noqa
list_tax_rates  # noqa
update_tax_rate  # noqa

# =============================================================================
# routes/tax_routes.py
# =============================================================================
btw_generate_report  # noqa
btw_save_transaction  # noqa
btw_upload_report  # noqa
toeristenbelasting_available_years  # noqa
toeristenbelasting_generate_report  # noqa

# =============================================================================
# routes/tenant_admin_config.py
# =============================================================================
create_config  # noqa
delete_config  # noqa
delete_tenant_config_legacy  # noqa
get_tenant_config_legacy  # noqa
list_configs  # noqa
set_tenant_config_legacy  # noqa
update_config  # noqa

# =============================================================================
# routes/tenant_admin_credentials.py
# =============================================================================
get_credentials_status  # noqa
oauth_callback_public  # noqa
oauth_complete  # noqa
start_oauth_flow  # noqa
test_credentials  # noqa
upload_credentials  # noqa

# =============================================================================
# routes/tenant_admin_details.py
# =============================================================================
get_tenant_details  # noqa
update_tenant_details  # noqa

# =============================================================================
# routes/tenant_admin_email.py
# =============================================================================
list_email_templates  # noqa
resend_invitation  # noqa
send_email_to_user  # noqa

# =============================================================================
# routes/tenant_admin_settings.py
# =============================================================================
get_activity  # noqa
get_settings  # noqa
get_tenant_language_preference  # noqa
update_settings  # noqa
update_tenant_language_preference  # noqa

# =============================================================================
# routes/tenant_admin_storage.py
# =============================================================================
get_storage_config  # noqa
get_storage_usage  # noqa
list_folders  # noqa
test_folder_access  # noqa
update_storage_config  # noqa

# =============================================================================
# routes/tenant_admin_templates.py
# =============================================================================
ai_help_template_endpoint  # noqa
apply_ai_fixes_endpoint  # noqa
approve_template_endpoint  # noqa
delete_tenant_template_endpoint  # noqa
get_current_template_endpoint  # noqa
get_default_template_endpoint  # noqa
preview_template_endpoint  # noqa
reject_template_endpoint  # noqa
validate_template_endpoint  # noqa

# =============================================================================
# routes/tenant_admin_users.py
# =============================================================================
assign_tenant_role_legacy  # noqa
assign_user_group  # noqa
create_tenant_user  # noqa
delete_tenant_user  # noqa
get_available_roles  # noqa
get_tenant_users_legacy  # noqa
list_tenant_users  # noqa
remove_tenant_role_legacy  # noqa
remove_user_group  # noqa
update_tenant_user  # noqa

# =============================================================================
# routes/user_routes.py
# =============================================================================
get_user_language_preference  # noqa
update_user_language_preference  # noqa

# =============================================================================
# routes/verification_routes.py
# =============================================================================
get_verification_status  # noqa
resend_verification  # noqa
update_sender_email  # noqa

# =============================================================================
# routes/year_end_config_routes.py
# =============================================================================
configure_vat_netting  # noqa
get_balance_sheet_accounts  # noqa
get_tenant_available_accounts  # noqa
get_tenant_purposes  # noqa
get_vat_netting_config  # noqa
remove_vat_netting  # noqa
set_tenant_account_purpose  # noqa
validate_tenant_config  # noqa

# =============================================================================
# routes/year_end_routes.py
# =============================================================================
close_year  # noqa
get_available_years  # noqa
get_closed_years  # noqa
get_year_status  # noqa
reopen_year  # noqa
validate_year  # noqa

# =============================================================================
# routes/zzp_routes.py
# =============================================================================
copy_last_invoice  # noqa
create_credit_note  # noqa
create_invoice  # noqa
create_invoice_from_time_entries  # noqa
create_time_entry  # noqa
delete_time_entry  # noqa
get_aging  # noqa
get_field_config  # noqa
get_invoice  # noqa
get_invoice_ledger_accounts  # noqa
get_invoice_pdf  # noqa
get_payables  # noqa
get_payment_check_status  # noqa
get_receivables  # noqa
get_time_summary  # noqa
list_invoices  # noqa
list_time_entries  # noqa
mark_overdue_invoices  # noqa
preview_invoice_email  # noqa
preview_invoice_pdf  # noqa
run_payment_check  # noqa
send_invoice  # noqa
send_reminder  # noqa
update_field_config  # noqa
update_invoice  # noqa
update_time_entry  # noqa
upload_supporting_document  # noqa
validate_booking_param  # noqa

# =============================================================================
# src/actuals_routes.py
# =============================================================================
get_actuals_balance  # noqa
get_actuals_profitloss  # noqa

# =============================================================================
# src/admin_routes.py
# =============================================================================
add_user_to_group  # noqa
create_user  # noqa
delete_user  # noqa
disable_user  # noqa
enable_user  # noqa
list_groups  # noqa
list_users  # noqa
remove_user_from_group  # noqa
test_auth  # noqa
update_user_attributes  # noqa

# =============================================================================
# src/app.py
# =============================================================================
serve_docs  # noqa

# =============================================================================
# src/audit_routes.py
# =============================================================================
audit_health_check  # noqa
cleanup_old_logs  # noqa
export_logs_to_csv  # noqa
generate_compliance_report  # noqa
get_audit_log_count  # noqa
get_audit_logs  # noqa
get_transaction_audit_trail  # noqa
get_user_activity_report  # noqa

# =============================================================================
# src/bnb_routes.py
# =============================================================================
generate_country_report  # noqa
get_bnb_actuals  # noqa
get_bnb_channel_data  # noqa
get_bnb_filter_options  # noqa
get_bnb_guest_bookings  # noqa
get_bnb_listing_data  # noqa
get_bnb_returning_guests  # noqa
get_bnb_table  # noqa
get_bnb_violin_data  # noqa

# =============================================================================
# src/pattern_storage_routes.py
# =============================================================================
analyze_patterns_with_storage  # noqa
apply_patterns_from_storage  # noqa
get_incremental_update_stats  # noqa
get_pattern_storage_stats  # noqa
get_pattern_summary_from_storage  # noqa
get_performance_comparison  # noqa

# =============================================================================
# src/performance_optimizer.py
# =============================================================================
analyze_performance  # noqa
memory_check  # noqa
optimize_performance  # noqa
performance_status  # noqa

# =============================================================================
# src/reporting_routes.py
# =============================================================================
get_account_summary  # noqa
get_available_data  # noqa
get_available_years  # noqa
get_check_reference  # noqa
get_filter_options  # noqa
get_mutaties_table  # noqa
get_str_revenue  # noqa

# =============================================================================
# src/scalability_routes.py
# =============================================================================
get_scalability_alerts  # noqa
get_scalability_config  # noqa
optimize_scalability  # noqa
realtime_metrics  # noqa
run_load_test  # noqa
scalability_dashboard  # noqa
scalability_database_status  # noqa
scalability_performance  # noqa
scalability_status  # noqa

# =============================================================================
# src/security_audit.py
# =============================================================================
check_password_strength_endpoint  # noqa
check_sql_injection_endpoint  # noqa
check_xss_vulnerabilities_endpoint  # noqa
security_audit_endpoint  # noqa
validate_file_upload_endpoint  # noqa
validate_input_endpoint  # noqa

# =============================================================================
# src/str_channel_routes.py
# =============================================================================
calculate_str_channel_revenue  # noqa
preview_str_channel_data  # noqa
save_str_channel_transactions  # noqa

# =============================================================================
# src/str_invoice_routes.py
# =============================================================================
generate_invoice  # noqa
search_booking  # noqa
upload_template_to_drive  # noqa

# =============================================================================
# src/tenant_module_routes.py
# =============================================================================
get_all_tenant_modules  # noqa
get_tenant_modules  # noqa
update_tenant_module  # noqa

# =============================================================================
# gunicorn.conf.py — Gunicorn configuration variables (read by gunicorn server)
# =============================================================================
bind  # noqa
backlog  # noqa
workers  # noqa
worker_class  # noqa
threads  # noqa
worker_connections  # noqa
max_requests  # noqa
max_requests_jitter  # noqa
worker_tmp_dir  # noqa
timeout  # noqa
keepalive  # noqa
preload_app  # noqa
enable_stdio_inheritance  # noqa
reuse_port  # noqa
loglevel  # noqa
access_log_format  # noqa
accesslog  # noqa
errorlog  # noqa
limit_request_line  # noqa
limit_request_fields  # noqa
limit_request_field_size  # noqa
proc_name  # noqa
graceful_timeout  # noqa
raw_env  # noqa
on_starting  # noqa
on_reload  # noqa
worker_int  # noqa
on_exit  # noqa
