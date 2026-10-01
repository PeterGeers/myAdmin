"""
Bug condition exploration test (defense-in-depth / SECONDARY site) for the
banking-import-iban-account-resolution bugfix.

Property 1: Bug Condition — Account-Scoped Save-Path Gate Saves Cross-Account Rows
Validates: Requirements 2.4

GOAL
----
Surface the counterexample demonstrating that the authoritative duplicate gate in
``BankingProcessor.save_approved_transactions`` —

    SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1

is ACCOUNT-BLIND: it matches on ``Ref2`` scoped only by ``administration`` (tenant),
omitting ``Ref1`` (the bank-account IBAN). Rabobank's ``Volgnr`` (mapped to ``Ref2``)
restarts at 1 for every account, so a genuinely new row for account B whose ``Volgnr``
collides with an EXISTING row of account A under the SAME tenant is wrongly skipped as a
"duplicate (Ref2 match)".

CRITICAL BUGFIX SEMANTICS
-------------------------
This is a bug-condition EXPLORATION test. It MUST FAIL on the current (unfixed) gate.
The failure CONFIRMS the account-blindness. DO NOT fix the test or the production code
at this stage — the test failing is the SUCCESS outcome for this task. Once the SECONDARY
fix (Task 5.1) scopes the gate by ``Ref1``, this same test will pass unchanged.

The universal shape asserted (scoped to the concrete reproducible case):

    for all rows where a matching Ref2 exists under the same tenant for a DIFFERENT Ref1
    but NO record exists for the row's own (administration, Ref1, Ref2),
    the row is saved as new.

Runs against the ``testfinance`` schema with ``test_mode=True`` (seeded
``rekeningschema`` + ``mutaties`` fixtures, cleaned up afterwards). No production data is
touched.
"""

import os
import uuid

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from banking_processor import BankingProcessor
from database import DatabaseManager


# ---------------------------------------------------------------------------
# This is a REAL-DB test (testfinance). The unit-package connection guard
# (tests/unit/conftest.py) patches mysql.connector.connect to raise. Override
# that autouse fixture locally so this module may open a genuine connection to
# the Docker MySQL `testfinance` schema, as the task requires.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def block_real_connections():
    """Override the unit-package guard: allow real connections for this module."""
    yield


pytestmark = pytest.mark.integration


# IBANs from the reported case (kimgeers): account 1002 already has rows,
# account 1003 (spaar) has none and collides on the low Volgnr range.
EXISTING_IBAN = "NL98RABO0174003390"   # account A — already seeded, Ref2 = 1..5
NEW_IBAN = "NL60RABO1101699949"        # account B — ZERO rows, imports Ref2 = 1..5
NON_CLOSED_YEAR = 2025                  # kept clear of year_closure_status

# GL account codes used on the mutaties rows. mutaties.(Debet, administration) and
# (Credit, administration) are FK-constrained to rekeningschema.(Account, administration),
# so BOTH sides of every row must reference a seeded account for the tenant.
ACCOUNT_A_CODE = "1002"   # Lopende rekening (NL98)
ACCOUNT_B_CODE = "1003"   # Spaar rekening (NL60)
COUNTER_CODE = "8000"     # generic counter account for the other leg


def _unique_tenant():
    """Isolated tenant per test run so seeded rows never collide with real data."""
    return "T2BugAcct_" + uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db():
    """DatabaseManager bound to the testfinance schema.

    The repo-root .env sets DB_HOST=mysql (the Docker-internal hostname used by
    the backend container). From WSL that name does not resolve, so point at the
    published port on 127.0.0.1 when we see the container hostname. Skip the whole
    module if the test database is unreachable.
    """
    if os.environ.get("DB_HOST") in (None, "", "mysql"):
        os.environ["DB_HOST"] = "127.0.0.1"
    os.environ["TEST_MODE"] = "true"

    try:
        manager = DatabaseManager(test_mode=True)
        # Fail fast / skip if the schema is not reachable.
        manager.execute_query("SELECT 1", None, fetch=True)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"testfinance database not reachable: {exc}")
    return manager


@pytest.fixture
def processor(db):
    """BankingProcessor wired to the testfinance DatabaseManager."""
    proc = BankingProcessor(test_mode=True)
    proc.db = db
    return proc


def _seed_account(db, tenant, iban, account_code, account_name):
    """Seed one rekeningschema account for the tenant (AccountID auto-increments)."""
    db.execute_query(
        """INSERT INTO rekeningschema (Account, AccountLookup, AccountName, administration)
           VALUES (%s, %s, %s, %s)""",
        (account_code, iban, account_name, tenant),
        fetch=False,
        commit=True,
    )


def _seed_existing_mutaties(db, tenant, iban, ref2_values):
    """Seed existing mutaties rows for account A (the 'already imported' side)."""
    for seq in ref2_values:
        db.execute_query(
            """INSERT INTO mutaties
                   (TransactionNumber, TransactionDate, TransactionDescription,
                    TransactionAmount, Debet, Credit, ReferenceNumber,
                    Ref1, Ref2, Ref3, Ref4, administration)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                f"Rabo {NON_CLOSED_YEAR}-01-{seq:02d}",
                f"{NON_CLOSED_YEAR}-01-{seq:02d}",
                f"Existing A row {seq}",
                100.00 + seq,
                ACCOUNT_A_CODE,   # Debet leg (bank account A)
                COUNTER_CODE,     # Credit leg (counter account) — both FK-valid
                iban,
                iban,
                str(seq),
                "",
                "",
                tenant,
            ),
            fetch=False,
            commit=True,
        )


def _make_new_rows(tenant, iban, ref2_values, account_code=ACCOUNT_B_CODE):
    """Build approved-transaction dicts for the NEW account (B).

    Both the Debet (bank account B) and Credit (counter account) legs reference
    seeded rekeningschema accounts so the mutaties FK constraints are satisfied —
    the only thing under test is the Ref2/Ref1 duplicate gate.
    """
    rows = []
    for seq in ref2_values:
        rows.append(
            {
                "row_id": seq,
                "TransactionNumber": f"Rabo {NON_CLOSED_YEAR}-02-{seq:02d}",
                "TransactionDate": f"{NON_CLOSED_YEAR}-02-{seq:02d}",
                "TransactionDescription": f"New B row {seq}",
                "TransactionAmount": 200.00 + seq,
                "Debet": account_code,   # bank account B
                "Credit": COUNTER_CODE,  # counter account
                "ReferenceNumber": iban,
                "Ref1": iban,
                "Ref2": str(seq),
                "Ref3": "",
                "Ref4": "",
                "administration": tenant,
            }
        )
    return rows


def _cleanup(db, tenant):
    """Remove all rows this test seeded for the isolated tenant."""
    db.execute_query(
        "DELETE FROM mutaties WHERE administration = %s", (tenant,),
        fetch=False, commit=True,
    )
    db.execute_query(
        "DELETE FROM rekeningschema WHERE administration = %s", (tenant,),
        fetch=False, commit=True,
    )


class TestBugConditionAccountScopedSave:
    """Property 1 (Bug Condition): the save-path gate must save cross-account rows."""

    def test_cross_account_collision_saved(self, db, processor):
        """Cross-account Volgnr collision — all 5 NL60 rows must be saved as new.

        Scoped reproducible case: tenant has account A (NL98) with Ref2 = 1..5 and
        account B (NL60) with ZERO rows. Importing 5 NL60 rows carrying Ref2 = 1..5
        (same tenant) MUST save all 5 — none is a duplicate for its OWN account.

        EXPECTED ON UNFIXED CODE: FAILS. The account-blind gate matches NL98's Ref2
        1..5 under the same tenant and skips every NL60 row as
        "Skipping duplicate (Ref2 match)" → saved_count == 0.
        """
        tenant = _unique_tenant()
        try:
            _seed_account(db, tenant, EXISTING_IBAN, ACCOUNT_A_CODE, "Lopende rekening")
            _seed_account(db, tenant, NEW_IBAN, ACCOUNT_B_CODE, "Spaar rekening")
            _seed_account(db, tenant, "", COUNTER_CODE, "Counter account")
            _seed_existing_mutaties(db, tenant, EXISTING_IBAN, range(1, 6))

            # Sanity: account B genuinely has no rows yet.
            pre = db.execute_query(
                "SELECT COUNT(*) c FROM mutaties WHERE administration = %s AND Ref1 = %s",
                (tenant, NEW_IBAN),
                fetch=True,
            )
            assert pre[0]["c"] == 0

            new_rows = _make_new_rows(tenant, NEW_IBAN, range(1, 6))
            saved_count = processor.save_approved_transactions(new_rows)

            assert saved_count == 5, (
                "Account-blind gate dropped cross-account rows: expected all 5 NL60 "
                f"rows saved, got saved_count={saved_count}. The authoritative gate "
                "(WHERE Ref2 = %s AND administration = %s) matched NL98's existing "
                "Ref2 1..5 under the same tenant and skipped the NL60 rows as "
                "'duplicate (Ref2 match)'."
            )

            # And they must physically exist for account B.
            post = db.execute_query(
                "SELECT COUNT(*) c FROM mutaties WHERE administration = %s AND Ref1 = %s",
                (tenant, NEW_IBAN),
                fetch=True,
            )
            assert post[0]["c"] == 5
        finally:
            _cleanup(db, tenant)

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(seqs=st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=5, unique=True))
    def test_property_cross_account_rows_saved_as_new(self, db, processor, seqs):
        """PROPERTY (scoped): for all rows whose only matching Ref2 belongs to a
        DIFFERENT account under the same tenant — and for which NO record exists for
        the row's own (administration, Ref1, Ref2) — the row is saved as new.

        We generate the overlapping Volgnr subset the colliding (NL60) account carries
        (always a subset of the existing NL98 1..5 set, so every row is a cross-account
        collision), and assert all are saved.

        Validates: Requirements 2.4

        EXPECTED ON UNFIXED CODE: FAILS (saved_count < len(seqs); rows skipped as
        'duplicate (Ref2 match)').
        """
        tenant = _unique_tenant()
        try:
            _seed_account(db, tenant, EXISTING_IBAN, ACCOUNT_A_CODE, "Lopende rekening")
            _seed_account(db, tenant, NEW_IBAN, ACCOUNT_B_CODE, "Spaar rekening")
            _seed_account(db, tenant, "", COUNTER_CODE, "Counter account")
            # Account A always owns 1..5 so each generated seq collides cross-account.
            _seed_existing_mutaties(db, tenant, EXISTING_IBAN, range(1, 6))

            new_rows = _make_new_rows(tenant, NEW_IBAN, sorted(seqs))
            saved_count = processor.save_approved_transactions(new_rows)

            assert saved_count == len(seqs), (
                "Account-blind gate skipped genuinely-new cross-account rows: "
                f"Ref2={sorted(seqs)} for {NEW_IBAN}; expected {len(seqs)} saved, "
                f"got {saved_count}."
            )
        finally:
            _cleanup(db, tenant)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
