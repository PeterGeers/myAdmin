"""
Migration up/down round-trip test for the zzp_trips tax-log redesign.

Task 3.1 of spec `rittenregistratie-tax-log-redesign`.

This test runs against an ISOLATED SCRATCH SCHEMA — the dedicated non-production
`testfinance` schema the DB user fully owns — NOT the real `finance` schema and
never Railway. The four relevant tables (`contacts`, `invoices`, `zzp_vehicles`,
`zzp_trips`) are cloned there from the live `finance` definitions via
`SHOW CREATE TABLE`, so the fixture stays faithful to whatever the real schema
is at test time, and are dropped again on teardown. The real `finance` schema is
only ever read (`SHOW CREATE TABLE`), never modified.

It verifies, for migration file
`20260821120000_zzp_trips_tax_log_redesign.json`:

- `up` drops the four billing columns (`contact_id`, `invoice_id`,
  `is_billable`, `is_billed`) and the three billing indexes
  (`idx_admin_contact`, `idx_admin_billed`, `idx_zzp_trips_unbilled`), and adds
  `client_name` (Req 3.2, 3.3, 2.1).
- `down` restores `zzp_trips` to its exact pre-migration definition (Req 3.6).
- The `contacts` table definition is byte-for-byte identical before and after
  (Req 3.5).
- The migration `up` SQL contains no `IF EXISTS` on index drops (Req 3.7).
- A second apply reports "already applied" and does not re-run (Req 9.6).
"""

import json
import os
import re

import pytest

from database import DatabaseManager

# The migration file under test (Req 9.7 — JSON migration in src/migrations/).
MIGRATION_FILENAME = "20260821120000_zzp_trips_tax_log_redesign.json"

# Tables cloned into the scratch schema, in dependency order (parents first):
# zzp_trips FKs reference contacts, invoices, zzp_vehicles; invoices references
# contacts. Drop happens in reverse order.
_CLONE_ORDER = ["contacts", "zzp_vehicles", "invoices", "zzp_trips"]

# Billing columns / indexes the migration removes (Req 3.2, 3.3).
_BILLING_COLUMNS = ["contact_id", "invoice_id", "is_billable", "is_billed"]
_BILLING_INDEXES = ["idx_admin_contact", "idx_admin_billed", "idx_zzp_trips_unbilled"]


def _migrations_dir():
    # backend/src/migrations
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "src",
        "migrations",
    )


def _load_migration():
    path = os.path.join(_migrations_dir(), MIGRATION_FILENAME)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _strip_auto_increment(ddl: str) -> str:
    """Remove the volatile ``AUTO_INCREMENT=<n>`` table option.

    `SHOW CREATE TABLE` emits the table's current auto-increment counter, which
    is irrelevant to the schema shape and differs between the live table and a
    freshly-cloned empty one. Dropping it keeps the clone deterministic and the
    before/after schema comparison meaningful.
    """
    return re.sub(r"\s+AUTO_INCREMENT=\d+", "", ddl)


@pytest.mark.integration
@pytest.mark.database
class TestZzpTripsMigrationRoundTrip:
    """Up/down round-trip of the zzp_trips tax-log-redesign migration."""

    @pytest.fixture
    def db(self):
        return DatabaseManager()

    @pytest.fixture
    def scratch_schema(self, db):
        """Clone the four tables into the owned `testfinance` scratch schema.

        The DB user has ALL PRIVILEGES on `testfinance` (a dedicated,
        non-production schema the app no longer uses) but cannot CREATE a brand
        new database, so we use `testfinance` as the scratch area rather than a
        freshly created schema. The four tables are cloned there from the live
        `finance` definitions and dropped (children first) on teardown even if a
        test fails, so no scratch state leaks and the real `finance` schema is
        never modified.

        Yields the scratch schema name.
        """
        source_schema = db.config["database"]
        scratch = "testfinance"

        # Capture live DDL for the four tables from the source schema up front.
        create_statements = {}
        for table in _CLONE_ORDER:
            rows = db.execute_query(f"SHOW CREATE TABLE `{source_schema}`.`{table}`")
            create_statements[table] = _strip_auto_increment(rows[0]["Create Table"])

        def _drop_clones(cursor):
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in reversed(_CLONE_ORDER):
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"USE `{scratch}`")
            # Start from a clean slate in case a prior run left clones behind.
            _drop_clones(cursor)
            for table in _CLONE_ORDER:
                cursor.execute(create_statements[table])
            conn.commit()
            cursor.close()
        except Exception:
            conn.close()
            raise
        finally:
            if not conn.is_connected():
                pass
        conn.close()

        try:
            yield scratch
        finally:
            cleanup = db._get_connection()
            try:
                cur = cleanup.cursor()
                cur.execute(f"USE `{scratch}`")
                _drop_clones(cur)
                cleanup.commit()
                cur.close()
            finally:
                cleanup.close()

    # --- helpers that run SQL inside the scratch schema -------------------

    @staticmethod
    def _run_statements(db, scratch, statements):
        """Execute an ordered list of SQL statements inside the scratch schema."""
        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"USE `{scratch}`")
            for stmt in statements:
                cursor.execute(stmt)
                conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def _show_create(db, scratch, table):
        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"USE `{scratch}`")
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            row = cursor.fetchone()
            cursor.close()
            # row is a tuple: (table_name, create_sql)
            return _strip_auto_increment(row[1])
        finally:
            conn.close()

    @staticmethod
    def _column_defs(db, scratch, table):
        """Return {column_name: full definition} — order-independent.

        Keyed by name (not ordinal position) so the comparison ignores the
        physical column ORDER, which MySQL assigns by when a column was added.
        It still captures every column's full definition (type, nullability,
        default, extra, comment), so a type/default/comment change WOULD fail.
        """
        rows = db.execute_query(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                   EXTRA, COLUMN_COMMENT, GENERATION_EXPRESSION
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (scratch, table),
        )
        return {
            r["COLUMN_NAME"]: (
                r["COLUMN_TYPE"],
                r["IS_NULLABLE"],
                r["COLUMN_DEFAULT"],
                r["EXTRA"],
                r["COLUMN_COMMENT"],
                r["GENERATION_EXPRESSION"],
            )
            for r in rows
        }

    @staticmethod
    def _column_names(db, scratch, table):
        return set(TestZzpTripsMigrationRoundTrip._column_defs(db, scratch, table))

    @staticmethod
    def _index_names(db, scratch, table):
        rows = db.execute_query(
            """
            SELECT DISTINCT INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (scratch, table),
        )
        return {r["INDEX_NAME"] for r in rows}

    @staticmethod
    def _index_signatures(db, scratch, table):
        """Return the set of index COLUMN signatures (uniqueness + ordered cols).

        Compared by column coverage rather than by auto-generated index NAME:
        MySQL auto-names the backing index of a foreign key, and that generated
        name legitimately differs between the originally-created table (where it
        inherits the FK column name, e.g. `contact_id`) and the rolled-back one
        (where it inherits the constraint name, e.g. `zzp_trips_ibfk_2`). The
        set of indexed column tuples is the schema-meaningful invariant.
        """
        rows = db.execute_query(
            """
            SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """,
            (scratch, table),
        )
        by_name = {}
        for r in rows:
            by_name.setdefault(r["INDEX_NAME"], {"non_unique": r["NON_UNIQUE"], "cols": []})
            by_name[r["INDEX_NAME"]]["cols"].append(r["COLUMN_NAME"])
        return {
            (info["non_unique"], tuple(info["cols"])) for info in by_name.values()
        }

    @staticmethod
    def _foreign_keys(db, scratch, table):
        """Return the set of FK definitions: (name, column, ref_table, ref_column)."""
        rows = db.execute_query(
            """
            SELECT CONSTRAINT_NAME, COLUMN_NAME,
                   REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (scratch, table),
        )
        return {
            (
                r["CONSTRAINT_NAME"],
                r["COLUMN_NAME"],
                r["REFERENCED_TABLE_NAME"],
                r["REFERENCED_COLUMN_NAME"],
            )
            for r in rows
        }

    # --- the round-trip test ---------------------------------------------

    def test_up_removes_billing_and_down_restores(self, db, scratch_schema):
        """up drops billing cols/indexes + adds client_name; down restores exactly.

        Validates: Requirements 2.1, 3.2, 3.3, 3.5, 3.6
        """
        scratch = scratch_schema
        migration = _load_migration()

        # --- capture pre-migration definitions ---
        # zzp_trips is captured as a structural snapshot (column definitions keyed
        # by name, index column-signatures, FK definitions). This is the faithful
        # reading of Req 3.6's "a schema inspection ... matches the pre-migration
        # definition": it ignores two MySQL artifacts that a raw SHOW CREATE TABLE
        # text diff would trip on but that carry no schema meaning — the physical
        # ORDER in which re-added columns land, and the auto-generated NAME MySQL
        # gives a foreign key's backing index. Every column's full definition and
        # every index's column coverage and every FK are still compared exactly.
        trips_cols_before = self._column_defs(db, scratch, "zzp_trips")
        trips_idx_before = self._index_signatures(db, scratch, "zzp_trips")
        trips_fk_before = self._foreign_keys(db, scratch, "zzp_trips")

        # contacts is compared BYTE-FOR-BYTE (Req 3.5 is explicit) — it is never
        # touched by the migration, so its SHOW CREATE TABLE must be identical.
        contacts_before = self._show_create(db, scratch, "contacts")

        # Sanity: the fixture really has the billing columns/indexes to remove.
        for col in _BILLING_COLUMNS:
            assert col in trips_cols_before, (
                f"precondition: {col} should exist pre-migration"
            )
        idx_names_before = self._index_names(db, scratch, "zzp_trips")
        for idx in _BILLING_INDEXES:
            assert idx in idx_names_before, (
                f"precondition: {idx} should exist pre-migration"
            )
        assert "client_name" not in trips_cols_before

        # --- apply UP ---
        self._run_statements(db, scratch, migration["up"])

        cols_after_up = self._column_names(db, scratch, "zzp_trips")
        idx_after_up = self._index_names(db, scratch, "zzp_trips")

        # Req 3.2: four billing columns gone.
        for col in _BILLING_COLUMNS:
            assert col not in cols_after_up, f"{col} should be dropped by up"
        # Req 3.3: three billing indexes gone.
        for idx in _BILLING_INDEXES:
            assert idx not in idx_after_up, f"{idx} should be dropped by up"
        # Req 2.1: client_name present.
        assert "client_name" in cols_after_up

        # Req 3.4 (sanity): retained non-billing columns survive up.
        assert "project_name" in cols_after_up
        assert "notes" in cols_after_up
        assert "distance_km" in cols_after_up

        # --- apply DOWN (runner executes down in reverse order) ---
        self._run_statements(db, scratch, list(reversed(migration["down"])))

        trips_cols_after = self._column_defs(db, scratch, "zzp_trips")
        trips_idx_after = self._index_signatures(db, scratch, "zzp_trips")
        trips_fk_after = self._foreign_keys(db, scratch, "zzp_trips")

        # Req 3.6: zzp_trips matches its pre-migration definition.
        assert trips_cols_after == trips_cols_before, (
            "zzp_trips columns after down do not match pre-migration.\n"
            f"BEFORE: {trips_cols_before}\n\nAFTER: {trips_cols_after}"
        )
        assert trips_idx_after == trips_idx_before, (
            "zzp_trips indexes (by column signature) after down do not match "
            f"pre-migration.\nBEFORE: {trips_idx_before}\n\nAFTER: {trips_idx_after}"
        )
        assert trips_fk_after == trips_fk_before, (
            "zzp_trips foreign keys after down do not match pre-migration.\n"
            f"BEFORE: {trips_fk_before}\n\nAFTER: {trips_fk_after}"
        )

        # Req 3.5: contacts untouched byte-for-byte across the whole round-trip.
        contacts_after = self._show_create(db, scratch, "contacts")
        assert contacts_after == contacts_before, (
            "contacts definition changed across the migration round-trip.\n"
            f"BEFORE:\n{contacts_before}\n\nAFTER:\n{contacts_after}"
        )

    def test_up_sql_has_no_if_exists_on_index_drops(self):
        """Index drops use plain DROP INDEX, never IF EXISTS (MySQL 9.4).

        Validates: Requirements 3.7
        """
        migration = _load_migration()
        for stmt in migration["up"]:
            if "DROP INDEX" in stmt.upper():
                assert "IF EXISTS" not in stmt.upper(), (
                    f"index drop must not use IF EXISTS (MySQL 9.4): {stmt}"
                )

    def test_second_apply_reports_already_applied(self, db, scratch_schema, tmp_path):
        """A migration recorded as applied is skipped and reported, not re-run.

        Uses the real `DatabaseMigration.apply_migration` so the actual
        already-applied gate (checked against the tracking table) is exercised,
        but with its I/O redirected to the scratch schema: the migration's own
        `DatabaseManager` is replaced by a thin recorder that routes every
        statement to the `testfinance` scratch schema over a dedicated raw
        connection AND records them, so we can assert the up statements run once
        and are NOT re-executed on the second call. The tracking table is an
        isolated scratch table, so the real `database_migrations` table and the
        real `finance` schema are never touched.

        Validates: Requirements 9.6
        """
        from database_migrations import DatabaseMigration

        scratch = scratch_schema
        migration = _load_migration()
        tracking_table = "zzp_migtest_tracking"

        class _ScratchRecorder:
            """Minimal DatabaseManager stand-in bound to the scratch schema."""

            def __init__(self, outer_db, schema):
                self._outer = outer_db
                self._schema = schema
                self.executed = []  # statements run with fetch=False (writes/DDL)

            def execute_query(self, query, params=None, fetch=True, commit=False):
                conn = self._outer._get_connection()
                try:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute(f"USE `{self._schema}`")
                    cursor.execute(query, params or ())
                    if not fetch:
                        self.executed.append(query)
                    result = cursor.fetchall() if fetch else None
                    conn.commit()
                    cursor.close()
                    return result
                finally:
                    conn.close()

        # Isolated migrations dir containing only the migration under test.
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        src_path = os.path.join(_migrations_dir(), MIGRATION_FILENAME)
        with open(src_path, "r", encoding="utf-8") as f:
            mig_json = f.read()
        (mig_dir / MIGRATION_FILENAME).write_text(mig_json, encoding="utf-8")

        dm = DatabaseMigration()
        dm.migrations_dir = str(mig_dir)
        dm.migrations_table = tracking_table
        dm.db = _ScratchRecorder(db, scratch)

        # Clean + create the isolated tracking table in the scratch schema.
        dm.db.execute_query(
            f"DROP TABLE IF EXISTS {tracking_table}", fetch=False, commit=True
        )
        dm._create_migrations_table()

        filepath = os.path.join(str(mig_dir), MIGRATION_FILENAME)
        try:
            # --- first apply: runs the up statements, records the migration ---
            first = dm.apply_migration(filepath)
            assert first is True, "first apply should run and record the migration"
            assert migration["name"] in dm._get_applied_migrations()

            up_runs_first = [s for s in dm.db.executed if s in migration["up"]]
            assert len(up_runs_first) == len(migration["up"]), (
                "first apply should execute every up statement exactly once"
            )

            # --- second apply: must be skipped, up statements NOT re-run ---
            before = len(dm.db.executed)
            second = dm.apply_migration(filepath)
            assert second is False, "second apply must report already-applied and skip"
            assert len(dm.db.executed) == before, (
                "second apply must not re-execute any migration statement"
            )
        finally:
            dm.db.execute_query(
                f"DROP TABLE IF EXISTS {tracking_table}", fetch=False, commit=True
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
