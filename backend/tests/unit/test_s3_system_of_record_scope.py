"""S3 / T8 — Ratify the system-of-record scope.

**Validates: Requirements R3.1, R3.2, R3.3**

T8 is a *ratification / confirmation* task (no production code change, no PBT). It pins
the two findings the task must settle, at a level the codebase can regress-test:

1. **MySQL is the system of record for ALL tenants (R3.1).** `tenants`,
   `tenant_modules`, and `user_tenant_roles` are authoritative for tenant governance —
   which tenants exist, which modules each has enabled, and which per-tenant roles each
   user holds — for every tenant, *including* tenants that will later enable SAM-backed
   modules (not only finance tenants). The DDL is keyed on the tenancy key
   `administration`, with no module-specific coupling, so a SAM-backed-module tenant is
   covered identically to a finance tenant.

2. **Authority does not move to the module plane / no writable copy (R3.3).** The
   SAM/Lambda module plane (`sam/`) never opens a MySQL connection and never owns a
   second, writable copy of the governance facts. A module's need for those facts is met
   only via the token (S4) or the read-only MySQL->DynamoDB projection (D3) — never a
   request-time MySQL query from a Lambda (S1 "Data ownership" seam). This is confirmed
   structurally: the module plane declares no MySQL client dependency and imports no
   MySQL client in any of its source files, so the invariant holds by construction.

This complements — and does not duplicate — the existing coverage:
  * `test_s3_per_tenant_role_source_of_record.py` (T5) — per-tenant roles resolve from
    MySQL, global roles from the token, no token-claim authoring (R1.3, R1.4).
  * `test_module_registry.py` — entitlement is backing-agnostic (reads `tenant_modules`).
  * `test_check_db_imports.py` — the `mysql.connector` import boundary for `backend/`.
T8 focuses narrowly on the *scope of authority* (the three tables) and the *module-plane
has no MySQL* guardrail (R3.3).

No real DB, no network, no imports of module-plane code — this inspects the repository
tree (DDL files) and parses `sam/` sources with the `ast` module only.
"""

import ast
from pathlib import Path

import pytest

# ------------------------------------------------------------------ #
# Repository layout (this file: backend/tests/unit/<here>).
# ------------------------------------------------------------------ #
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAM_DIR = _REPO_ROOT / "sam"

# The three tables that ARE the system of record (R3.1) and their DDL.
_SYSTEM_OF_RECORD_DDL = {
    "tenants": _REPO_ROOT / "backend" / "sql" / "create_tenants_table.sql",
    "tenant_modules": _REPO_ROOT / "backend" / "sql" / "phase5_tenant_modules.sql",
    "user_tenant_roles": (
        _REPO_ROOT / "backend" / "src" / "migrations" / "create_user_tenant_roles.sql"
    ),
}

# Import roots that indicate a MySQL client on the module plane. Any of these under
# `sam/` would mean the module plane can open a MySQL connection — forbidden (R3.3).
_MYSQL_CLIENT_ROOTS = ("mysql", "pymysql", "mysqlclient", "aiomysql", "MySQLdb")


def _iter_sam_py_files():
    """Yield every .py file under sam/, skipping caches."""
    skip = {"__pycache__", ".pytest_cache"}
    for path in sorted(_SAM_DIR.rglob("*.py")):
        if any(part in skip for part in path.parts):
            continue
        yield path


def _imported_roots(py_file: Path) -> set[str]:
    """Return the top-level module roots imported by a Python file (via AST)."""
    roots: set[str] = set()
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Ignore relative imports (node.level > 0); they can't be a MySQL client.
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


# ------------------------------------------------------------------ #
# R3.1 — the three tables are the system of record, keyed by tenant.
# ------------------------------------------------------------------ #


class TestSystemOfRecordTablesAreTenantKeyed:
    """`tenants` / `tenant_modules` / `user_tenant_roles` are authoritative, tenant-keyed."""

    @pytest.mark.parametrize("table", sorted(_SYSTEM_OF_RECORD_DDL))
    def test_system_of_record_ddl_exists(self, table):
        """Each system-of-record table has a DDL artifact in the repo (R3.1)."""
        assert _SYSTEM_OF_RECORD_DDL[table].is_file(), (
            f"DDL for system-of-record table {table!r} not found at "
            f"{_SYSTEM_OF_RECORD_DDL[table]}"
        )

    @pytest.mark.parametrize("table", sorted(_SYSTEM_OF_RECORD_DDL))
    def test_system_of_record_ddl_is_keyed_on_administration(self, table):
        """Authority is scoped by the tenancy key `administration` — not by module/backing.

        A table keyed on `administration` (with no module-specific coupling) covers a
        SAM-backed-module tenant identically to a finance tenant (R3.1).
        """
        ddl = _SYSTEM_OF_RECORD_DDL[table].read_text(encoding="utf-8")
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl
        assert "administration" in ddl
        # The scope key is the tenancy key, never a module name / backing kind literal.
        assert "backing" not in ddl.lower()


# ------------------------------------------------------------------ #
# R3.3 — authority does not move to the module plane / no writable copy.
# ------------------------------------------------------------------ #


class TestModulePlaneHasNoMySQLClient:
    """The `sam/` module plane cannot open a MySQL connection (no client dep / import)."""

    def test_sam_directory_exists(self):
        """Sanity: the module plane tree is present to inspect."""
        assert _SAM_DIR.is_dir(), f"module-plane dir not found at {_SAM_DIR}"

    def test_sam_requirements_declare_no_mysql_client(self):
        """`sam/shared/requirements.txt` pins no MySQL driver (R3.3)."""
        reqs = _SAM_DIR / "shared" / "requirements.txt"
        assert reqs.is_file()
        lines = [
            ln.strip().lower()
            for ln in reqs.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        for line in lines:
            # Take the dependency name before any version/extra specifier.
            name = line.split("==")[0].split(">=")[0].split("[")[0].strip()
            assert name not in {r.lower() for r in _MYSQL_CLIENT_ROOTS}, (
                f"module-plane requirements declare a MySQL client ({line!r}); the "
                f"module plane must never open a MySQL connection (R3.3)."
            )

    def test_no_sam_source_imports_a_mysql_client(self):
        """No file under `sam/` imports a MySQL client (AST-level scan) (R3.3).

        The Flask plane reads MySQL via `role_cache.py`; the module plane must not — it
        gets governance facts only via the token (S4) or the read-only projection (D3),
        never a request-time MySQL query from a Lambda.
        """
        offenders: list[str] = []
        for py_file in _iter_sam_py_files():
            roots = _imported_roots(py_file)
            hits = roots.intersection(_MYSQL_CLIENT_ROOTS)
            if hits:
                rel = py_file.relative_to(_REPO_ROOT).as_posix()
                offenders.append(f"{rel}: imports {sorted(hits)}")
        assert not offenders, (
            "module-plane source imports a MySQL client — authority must not move to "
            "the module plane and no module may own a writable copy (R3.3):\n  "
            + "\n  ".join(offenders)
        )

    def test_no_sam_source_reads_governance_tables_directly(self):
        """No `sam/` source names the governance tables as raw SQL reads (R3.3).

        Belt-and-suspenders on top of the import scan: even without a client, a raw
        governance-table SQL string under `sam/` would signal an attempt to treat the
        module plane as a reader/writer of the system of record.
        """
        offenders: list[str] = []
        for py_file in _iter_sam_py_files():
            text = py_file.read_text(encoding="utf-8")
            for table in ("user_tenant_roles", "tenant_modules"):
                if table in text:
                    rel = py_file.relative_to(_REPO_ROOT).as_posix()
                    offenders.append(f"{rel}: references {table!r}")
        assert not offenders, (
            "module-plane source references a governance table directly; those facts "
            "reach a module via the token (S4) or the read-only projection (D3), never "
            "a request-time MySQL read (R3.3):\n  " + "\n  ".join(offenders)
        )
