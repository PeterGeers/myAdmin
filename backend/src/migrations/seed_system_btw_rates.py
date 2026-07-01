"""
Seed script: Insert NL system default BTW rates into tax_rates table.

Seeds three system-level BTW rates:
  - zero  (0.000%, resolved ledger account)
  - low   (9.000%, resolved ledger account)
  - high  (21.000%, resolved ledger account)

Ledger accounts are resolved from the nl.json chart of accounts template
by matching accounts with $.vat_netting flag. Falls back to hardcoded
defaults with a deprecation warning if the template cannot be loaded.

Idempotent: skips rows that already exist (uses INSERT IGNORE).
Does NOT seed btw_accommodation or tourist_tax (tenant-specific).

Requirements: 2.8, 2.9
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import DatabaseManager

logger = logging.getLogger(__name__)

# Fallback values used only when nl.json template cannot be loaded.
# DEPRECATED: These will be removed once all environments have the
# updated nl.json template with proper parameters flags.
_FALLBACK_ACCOUNTS = {
    "zero": "2010",
    "low": "2021",
    "high": "2020",
}

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "templates", "chart_of_accounts", "nl.json"
)


def _resolve_vat_accounts_from_template(template_path=None):
    """
    Load the nl.json chart of accounts template and resolve VAT ledger
    accounts by matching the $.vat_netting flag.

    Mapping strategy:
      - 'Betaalde BTW' (paid VAT) -> zero rate account
      - 'Ontvangen BTW Hoog' (received VAT high) -> high rate account
      - 'Ontvangen BTW Laag' (received VAT low) -> low rate account

    Returns a dict mapping VAT code to account number, e.g.:
      {'zero': '2010', 'low': '2021', 'high': '2020'}

    Returns None if the template cannot be loaded or parsed.
    """
    path = template_path or TEMPLATE_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            accounts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Could not load nl.json template from %s: %s. "
            "Falling back to hardcoded VAT accounts (deprecated).",
            path,
            exc,
        )
        return None

    # Find all accounts with vat_netting flag
    vat_accounts = []
    for acct in accounts:
        params = acct.get("parameters")
        if not params or not isinstance(params, dict):
            continue
        if params.get("vat_netting"):
            vat_accounts.append(acct)

    if not vat_accounts:
        logger.warning(
            "No accounts with $.vat_netting flag found in template. "
            "Falling back to hardcoded VAT accounts (deprecated)."
        )
        return None

    # Map account names to VAT codes
    # The Dutch chart of accounts uses these standard names:
    #   - "Betaalde BTW" = paid VAT (used for zero-rate / input VAT)
    #   - "Ontvangen BTW Hoog" = received VAT high rate
    #   - "Ontvangen BTW Laag" = received VAT low rate
    resolved = {}
    for acct in vat_accounts:
        name = acct.get("AccountName", "").lower()
        account_number = acct.get("Account")
        if not account_number:
            continue

        if "betaalde" in name and "btw" in name:
            resolved["zero"] = account_number
        elif "ontvangen" in name and "hoog" in name:
            resolved["high"] = account_number
        elif "ontvangen" in name and "laag" in name:
            resolved["low"] = account_number

    expected_codes = {"zero", "low", "high"}
    missing = expected_codes - set(resolved.keys())
    if missing:
        logger.warning(
            "Could not resolve all VAT accounts from template. "
            "Missing codes: %s. Resolved so far: %s. "
            "Falling back to hardcoded VAT accounts (deprecated).",
            missing,
            resolved,
        )
        return None

    logger.info("Resolved VAT accounts from template: %s", resolved)
    return resolved


def _build_system_btw_rates(vat_accounts):
    """Build the seed data tuples using resolved VAT account numbers."""
    return [
        (
            "_system_",
            "btw",
            "zero",
            0.000,
            vat_accounts["zero"],
            "2000-01-01",
            "BTW 0% - Vrijgesteld",
        ),
        (
            "_system_",
            "btw",
            "low",
            9.000,
            vat_accounts["low"],
            "2000-01-01",
            "BTW Laag tarief",
        ),
        (
            "_system_",
            "btw",
            "high",
            21.000,
            vat_accounts["high"],
            "2000-01-01",
            "BTW Hoog tarief",
        ),
    ]


def run_seed(db=None, template_path=None):
    """Insert NL system default BTW rates. Skips duplicates."""
    if db is None:
        db = DatabaseManager()

    # Resolve VAT accounts from template; fall back to hardcoded if needed
    vat_accounts = _resolve_vat_accounts_from_template(template_path)
    if vat_accounts is None:
        logger.warning(
            "DEPRECATED: Using hardcoded VAT accounts %s. "
            "Update nl.json template with $.vat_netting flags to resolve this.",
            _FALLBACK_ACCOUNTS,
        )
        vat_accounts = dict(_FALLBACK_ACCOUNTS)

    rates = _build_system_btw_rates(vat_accounts)

    insert_sql = """
        INSERT IGNORE INTO tax_rates
            (administration, tax_type, tax_code, rate, ledger_account, effective_from, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    inserted = 0
    for row in rates:
        result = db.execute_query(insert_sql, row, fetch=False, commit=True)
        if result and result > 0:
            inserted += 1
            logger.info(
                "Inserted BTW rate: %s (%s) -> account %s", row[2], row[6], row[4]
            )
        else:
            logger.info("BTW rate '%s' already exists, skipped.", row[2])

    logger.info("Seed complete: %d of %d rates inserted.", inserted, len(rates))
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_seed()
