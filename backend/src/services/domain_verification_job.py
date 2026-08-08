"""
Domain Verification Background Job

Periodically checks ACM certificate status for pending custom domains
and auto-activates them when certificates are issued.

Designed to run daily via a scheduler (e.g., cron, APScheduler, or
triggered by a sysadmin endpoint).
"""

import logging
import os

from database import DatabaseManager
from services.cloudfront_domain_service import CloudFrontDomainService

logger = logging.getLogger(__name__)


def run_domain_verification_check(db=None, cf_service=None):
    """
    Check all pending custom domains and auto-activate those with issued certificates.

    For each domain with verification_status IN ('pending_dns', 'validating'):
    - Calls describe_certificate to check ACM status
    - If ISSUED: activates the domain (add to CloudFront distribution, update KVS, update DB)
    - If FAILED: updates status to 'failed' and logs a warning
    - If still PENDING: logs info and skips

    Args:
        db: Optional DatabaseManager instance (for testing). If None, creates one.
        cf_service: Optional CloudFrontDomainService instance (for testing). If None, creates one.

    Returns:
        Dict with counts of processed, activated, failed, and still-pending domains.
    """
    if db is None:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

    if cf_service is None:
        cf_service = CloudFrontDomainService()

    # Query all pending domains
    query = """
        SELECT id, administration, slug, domain, acm_certificate_arn, verification_status
        FROM tenant_custom_domains
        WHERE verification_status IN ('pending_dns', 'validating')
    """
    pending = db.execute_query(query)

    if not pending:
        logger.info("Domain verification check: no pending domains found.")
        return {"processed": 0, "activated": 0, "failed": 0, "pending": 0}

    activated = 0
    failed = 0
    still_pending = 0

    for row in pending:
        domain_id = row["id"]
        domain = row["domain"]
        slug = row["slug"]
        cert_arn = row["acm_certificate_arn"]
        administration = row["administration"]

        try:
            cert_result = cf_service.describe_certificate(cert_arn)

            if not cert_result.get("success"):
                logger.warning(
                    f"Domain verification job: failed to describe certificate "
                    f"for {domain} (tenant: {administration}): "
                    f"{cert_result.get('error', 'unknown error')}"
                )
                failed += 1
                _update_status(db, domain_id, administration, "failed")
                continue

            status = cert_result["status"]

            if status == "ISSUED":
                # Activate the domain: add to CloudFront + KVS + update DB
                success = _activate_domain(
                    db, cf_service, domain_id, domain, slug,
                    cert_arn, administration
                )
                if success:
                    activated += 1
                    logger.info(
                        f"Domain verification job: auto-activated {domain} "
                        f"(tenant: {administration})"
                    )
                else:
                    failed += 1
                    logger.warning(
                        f"Domain verification job: activation failed for "
                        f"{domain} (tenant: {administration})"
                    )

            elif status == "FAILED":
                failed += 1
                _update_status(db, domain_id, administration, "failed")
                logger.warning(
                    f"Domain verification job: certificate FAILED for "
                    f"{domain} (tenant: {administration})"
                )

            else:
                # Still PENDING_VALIDATION or other non-terminal status
                still_pending += 1
                logger.info(
                    f"Domain verification job: {domain} still pending "
                    f"(status: {status}, tenant: {administration})"
                )

        except Exception as e:
            failed += 1
            logger.error(
                f"Domain verification job: unexpected error processing "
                f"{domain} (tenant: {administration}): {e}"
            )

    result = {
        "processed": len(pending),
        "activated": activated,
        "failed": failed,
        "pending": still_pending,
    }

    logger.info(
        f"Domain verification check complete: {result['processed']} processed, "
        f"{result['activated']} activated, {result['failed']} failed, "
        f"{result['pending']} still pending"
    )

    return result


def _activate_domain(db, cf_service, domain_id, domain, slug, cert_arn, administration):
    """
    Activate a domain by adding it to CloudFront, updating KVS, and updating DB.

    Same activation logic as DomainService.verify_custom_domain.

    Args:
        db: DatabaseManager instance
        cf_service: CloudFrontDomainService instance
        domain_id: Database record ID
        domain: The custom domain
        slug: Tenant slug
        cert_arn: ACM certificate ARN
        administration: Tenant administration identifier

    Returns:
        True if activation succeeded, False otherwise
    """
    # Add domain to CloudFront distribution
    add_success = cf_service.add_domain_to_distribution(domain, cert_arn)
    if not add_success:
        logger.error(
            f"Domain verification job: failed to add {domain} to CloudFront"
        )
        return False

    # Update KVS mapping
    kvs_success = cf_service.put_kvs_mapping(domain, slug)
    if not kvs_success:
        logger.error(
            f"Domain verification job: failed to update KVS for {domain}"
        )
        return False

    # Update database: mark as active
    update_query = """
        UPDATE tenant_custom_domains
        SET verification_status = 'issued',
            is_active = TRUE,
            activated_at = NOW()
        WHERE id = %s AND administration = %s
    """
    db.execute_query(
        update_query, (domain_id, administration), fetch=False, commit=True
    )

    return True


def _update_status(db, domain_id, administration, status):
    """
    Update the verification_status for a domain record.

    Args:
        db: DatabaseManager instance
        domain_id: Database record ID
        administration: Tenant administration identifier
        status: New verification status value
    """
    update_query = """
        UPDATE tenant_custom_domains
        SET verification_status = %s
        WHERE id = %s AND administration = %s
    """
    db.execute_query(
        update_query, (status, domain_id, administration), fetch=False, commit=True
    )
